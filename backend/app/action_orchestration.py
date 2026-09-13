"""Deterministic LangGraph workflow for evidence-backed preparation actions.

The graph never decides that a patient needs care. It receives actions already
identified from approved source records and lets specialist nodes prepare options
for the patient to review.
"""

from datetime import date, timedelta
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph


class ActionRequest(TypedDict):
    task_id: str
    action_type: str
    documented_date: str | None
    documented_time: str | None
    documented_service: str | None
    order_reference: str | None
    source_version_ids: list[str]


class ActionProposal(TypedDict):
    task_id: str
    action_type: str
    payload: dict
    source_version_ids: list[str]


class ActionState(TypedDict, total=False):
    requests: list[ActionRequest]
    clinic_date: str | None
    proposals: Annotated[list[ActionProposal], operator.add]


def _relative_date(clinic_date: str | None, days: int) -> str:
    if not clinic_date:
        return ""
    try:
        return (date.fromisoformat(clinic_date) - timedelta(days=days)).isoformat()
    except ValueError:
        return ""


def _normalize(state: ActionState):
    visit_date = next(
        (
            item["documented_date"]
            for item in state["requests"]
            if item["action_type"] == "clinic_appointment"
            and item["documented_date"]
        ),
        None,
    )
    return {"clinic_date": visit_date}


def _appointment_agent(state: ActionState):
    proposals: list[ActionProposal] = []
    for item in state["requests"]:
        if item["action_type"] != "clinic_appointment":
            continue
        proposals.append(
            {
                "task_id": item["task_id"],
                "action_type": "appointment",
                "payload": {
                    "clinic": item["documented_service"] or "Clinic",
                    "date": item["documented_date"] or "",
                    "time": item.get("documented_time") or "",
                    "timezone": "America/New_York",
                    "appointment_type": "Follow-up",
                    "schedule_origin": "Provider availability on the documented date",
                },
                "source_version_ids": item["source_version_ids"],
            }
        )
    return {"proposals": proposals}


def _ordered_care_agent(state: ActionState, *, imaging: bool):
    expected = "imaging" if imaging else "laboratory"
    action_type = "imaging" if imaging else "lab"
    days_before = 7 if imaging else 3
    facility = "Fieldstone Imaging" if imaging else "Fieldstone Lab"
    default_service = "Imaging" if imaging else "Laboratory work"
    default_time = "11:00" if imaging else "08:30"
    proposals: list[ActionProposal] = []
    for item in state["requests"]:
        if item["action_type"] != expected:
            continue
        proposals.append(
            {
                "task_id": item["task_id"],
                "action_type": action_type,
                "payload": {
                    "order_id": item["order_reference"] or "",
                    "facility": facility,
                    "date": item["documented_date"]
                    or _relative_date(state.get("clinic_date"), days_before),
                    "time": default_time,
                    "timezone": "America/New_York",
                    "service": item["documented_service"] or default_service,
                    "schedule_origin": "Agent-proposed before next visit",
                    "order_verification": "Order verification required",
                },
                "source_version_ids": item["source_version_ids"],
            }
        )
    return {"proposals": proposals}


def _lab_agent(state: ActionState):
    return _ordered_care_agent(state, imaging=False)


def _imaging_agent(state: ActionState):
    return _ordered_care_agent(state, imaging=True)


def _travel_agent(state: ActionState):
    proposals: list[ActionProposal] = []
    for item in state["requests"]:
        if item["action_type"] != "travel":
            continue
        proposals.append(
            {
                "task_id": item["task_id"],
                "action_type": "travel",
                "payload": {
                    "provider": "CareBridge Transport",
                    "pickup": "",
                    "destination": item["documented_service"] or "Clinic",
                    "date": item["documented_date"] or "",
                    "time": item.get("documented_time") or "09:00",
                    "passengers": 1,
                    "cost": "Pending route details",
                },
                "source_version_ids": item["source_version_ids"],
            }
        )
    return {"proposals": proposals}


def build_action_orchestration_graph():
    graph = StateGraph(ActionState)
    graph.add_node("route_actions", _normalize)
    graph.add_node("appointment_agent", _appointment_agent)
    graph.add_node("laboratory_agent", _lab_agent)
    graph.add_node("imaging_agent", _imaging_agent)
    graph.add_node("travel_agent", _travel_agent)
    graph.add_edge(START, "route_actions")
    graph.add_edge("route_actions", "appointment_agent")
    graph.add_edge("route_actions", "laboratory_agent")
    graph.add_edge("route_actions", "imaging_agent")
    graph.add_edge("route_actions", "travel_agent")
    graph.add_edge("appointment_agent", END)
    graph.add_edge("laboratory_agent", END)
    graph.add_edge("imaging_agent", END)
    graph.add_edge("travel_agent", END)
    return graph.compile()


def propose_preparation_actions(requests: list[ActionRequest]):
    result = build_action_orchestration_graph().invoke(
        {"requests": requests, "proposals": []},
        config={
            "run_name": "carebridge-action-orchestrator",
            "tags": ["carebridge", "actions"],
            "metadata": {
                "content_redacted": True,
                "request_count": len(requests),
            },
        },
    )
    return result.get("proposals", [])
