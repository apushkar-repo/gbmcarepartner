"""Versioned evaluation runner for preparation planning and action routing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .action_orchestration import propose_preparation_actions
from .preparation import generate_preparation


DATASET_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "preparation_action_v1.jsonl"
)


@dataclass(frozen=True)
class PreparationEvaluationCase:
    case_id: str
    dataset_version: str
    title: str
    context: dict[str, Any]
    expected_action_types: list[str]
    expected_fields: dict[str, dict[str, str]]
    expected_blocked_action_types: list[str]
    forbidden_action_types: list[str]
    max_items: int
    tags: list[str]


def load_preparation_cases(
    path: Path = DATASET_PATH,
) -> list[PreparationEvaluationCase]:
    cases: list[PreparationEvaluationCase] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cases.append(PreparationEvaluationCase(**json.loads(line)))
    if not cases:
        raise ValueError("The preparation evaluation dataset is empty.")
    if len({case.dataset_version for case in cases}) != 1:
        raise ValueError("The preparation evaluation dataset mixes versions.")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Preparation evaluation case IDs must be unique.")
    return cases


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def score_preparation_result(
    case: PreparationEvaluationCase, result: dict[str, Any]
) -> dict[str, float | bool]:
    items = result.get("items", [])
    actions = [item for item in items if item.get("action_type", "none") != "none"]
    actual_types = Counter(item["action_type"] for item in actions)
    expected_types = Counter(case.expected_action_types)
    true_positive = sum((actual_types & expected_types).values())
    action_precision = _ratio(true_positive, sum(actual_types.values()))
    action_recall = _ratio(true_positive, sum(expected_types.values()))
    available_versions = {
        item["version_id"] for item in case.context.get("summaries", [])
    }
    available_questions = {
        item["question_id"] for item in case.context.get("questions", [])
    }
    source_valid = all(
        bool(item.get("source_version_ids") or item.get("source_question_ids"))
        and set(item.get("source_version_ids", [])).issubset(available_versions)
        and set(item.get("source_question_ids", [])).issubset(available_questions)
        for item in items
    )
    prohibited_action_free = not any(
        item["action_type"] in case.forbidden_action_types for item in actions
    )
    fields_correct = True
    for action_type, expected in case.expected_fields.items():
        candidates = [item for item in actions if item["action_type"] == action_type]
        if not candidates or not all(
            any(str(candidate.get(field, "")).casefold() == value.casefold() for candidate in candidates)
            for field, value in expected.items()
        ):
            fields_correct = False
    blocked_types = {
        item["action_type"] for item in actions if item.get("blocked_reason")
    }
    blocked_prerequisites_correct = set(case.expected_blocked_action_types).issubset(
        blocked_types
    )
    bounded = len(items) <= case.max_items
    verified = bool(result.get("verified"))
    passed = all(
        (
            verified,
            action_precision == 1.0,
            action_recall == 1.0,
            source_valid,
            prohibited_action_free,
            fields_correct,
            blocked_prerequisites_correct,
            bounded,
        )
    )
    return {
        "action_precision": action_precision,
        "action_recall": action_recall,
        "source_valid": source_valid,
        "prohibited_action_free": prohibited_action_free,
        "fields_correct": fields_correct,
        "blocked_prerequisites_correct": blocked_prerequisites_correct,
        "bounded": bounded,
        "verified": verified,
        "passed": passed,
    }


Generator = Callable[[Callable[[], dict[str, Any]]], dict[str, Any]]


def run_preparation_evaluation_case(
    case: PreparationEvaluationCase,
    generator: Generator = generate_preparation,
) -> dict[str, Any]:
    result = generator(lambda: case.context)
    scores = score_preparation_result(case, result)
    routing_requests = [
        {
            "task_id": f"{case.case_id}-{position}",
            "action_type": item["action_type"],
            "documented_date": item.get("documented_date"),
            "documented_time": item.get("documented_time"),
            "documented_service": item.get("documented_service"),
            "order_reference": item.get("order_reference"),
            "source_version_ids": item.get("source_version_ids", []),
        }
        for position, item in enumerate(result.get("items", []))
        if item.get("action_type", "none") != "none"
    ]
    proposals = propose_preparation_actions(routing_requests) if routing_requests else []
    expected_specialists = Counter(
        {"clinic_appointment": "appointment", "laboratory": "lab"}.get(item, item)
        for item in case.expected_action_types
    )
    actual_specialists = Counter(item["action_type"] for item in proposals)
    routing_correct = expected_specialists == actual_specialists
    scores["routing_correct"] = routing_correct
    scores["passed"] = bool(scores["passed"] and routing_correct)
    return {
        "case_id": case.case_id,
        "title": case.title,
        "expected_action_types": case.expected_action_types,
        "actual_action_types": [item["action_type"] for item in routing_requests],
        "specialist_proposals": [item["action_type"] for item in proposals],
        "scores": scores,
        "tags": case.tags,
    }


def run_preparation_evaluation_suite(
    generator: Generator = generate_preparation,
) -> list[dict[str, Any]]:
    return [run_preparation_evaluation_case(case, generator) for case in load_preparation_cases()]
