from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import uuid4
import hashlib
import hmac
import json
import logging
import sqlite3
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
    os.environ["LANGSMITH_HIDE_INPUTS"] = "true"
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = "true"

from .action_orchestration import propose_preparation_actions
from .answering import AnswerUnavailable, answer_question
from .evaluations import EvaluationUnavailable, load_cases, run_evaluation_case
from .mock_scheduler import (
    MockReminderScheduler,
    MockSchedulerConflict,
    MockSchedulerTimeout,
)
from .ocr import LlamaParseAdapter, OcrUnavailable
from .preparation import PreparationUnavailable, generate_preparation
from .preparation_evaluations import (
    load_preparation_cases,
    run_preparation_evaluation_case,
)
from .retrieval import (
    SemanticUnavailable,
    index_semantically,
    reciprocal_rank_fusion,
    search_semantically,
    semantic_configured,
)

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "carebridge.db"
STORAGE_PATH = Path(__file__).resolve().parent.parent / "storage"
STORAGE_PATH.mkdir(exist_ok=True)
MAX_BYTES = 10 * 1024 * 1024
ALLOWED = {"application/pdf", "image/jpeg", "image/png"}

app = FastAPI(title="CareBridge API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["GET", "POST", "PATCH"], allow_headers=["*"])

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, filename TEXT NOT NULL, content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS extraction_jobs (id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), status TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS extraction_results (job_id TEXT PRIMARY KEY REFERENCES extraction_jobs(id), text TEXT NOT NULL, pages INTEGER NOT NULL, provider TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS transcript_versions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES extraction_jobs(id), text TEXT NOT NULL, version INTEGER NOT NULL, actor_id TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS document_versions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES extraction_jobs(id), payload TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, approved_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS patients (id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, phone TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS patient_documents (patient_id TEXT NOT NULL REFERENCES patients(id), document_id TEXT NOT NULL REFERENCES documents(id), PRIMARY KEY(patient_id, document_id));
CREATE TABLE IF NOT EXISTS care_partner_grants (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), partner_email TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(patient_id, partner_email));
CREATE TABLE IF NOT EXISTS care_partner_permissions (grant_id TEXT PRIMARY KEY REFERENCES care_partner_grants(id), can_view_records INTEGER NOT NULL, can_manage_questions INTEGER NOT NULL, can_approve_actions INTEGER NOT NULL, version INTEGER NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS care_questions (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), text TEXT NOT NULL, original_text TEXT NOT NULL, source_label TEXT NOT NULL, source_version_ids TEXT NOT NULL, status TEXT NOT NULL, created_by_role TEXT NOT NULL, created_by_id TEXT NOT NULL, clinician_response TEXT, responded_by TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS care_question_events (id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES care_questions(id), action TEXT NOT NULL, actor_role TEXT NOT NULL, actor_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preparation_plans (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), status TEXT NOT NULL, summary TEXT NOT NULL, message TEXT NOT NULL, verified INTEGER NOT NULL, model TEXT, created_by_role TEXT NOT NULL, created_by_id TEXT NOT NULL, created_at TEXT NOT NULL, approved_by TEXT, approved_at TEXT);
CREATE TABLE IF NOT EXISTS preparation_tasks (id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES preparation_plans(id), patient_id TEXT NOT NULL REFERENCES patients(id), title TEXT NOT NULL, description TEXT NOT NULL, origin_type TEXT NOT NULL, source_version_ids TEXT NOT NULL, source_question_ids TEXT NOT NULL, blocked_reason TEXT, status TEXT NOT NULL, position INTEGER NOT NULL, completed_by TEXT, completed_at TEXT);
CREATE TABLE IF NOT EXISTS preparation_task_actions (task_id TEXT PRIMARY KEY REFERENCES preparation_tasks(id), action_type TEXT NOT NULL, documented_date TEXT, documented_time TEXT, documented_service TEXT, order_reference TEXT, specialist_status TEXT NOT NULL, arrangement_id TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS preparation_events (id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES preparation_plans(id), task_id TEXT, action TEXT NOT NULL, actor_role TEXT NOT NULL, actor_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reminders (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), task_id TEXT NOT NULL REFERENCES preparation_tasks(id), current_version INTEGER NOT NULL, status TEXT NOT NULL, idempotency_key TEXT, provider_receipt TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reminder_versions (reminder_id TEXT NOT NULL REFERENCES reminders(id), version INTEGER NOT NULL, text TEXT NOT NULL, channel TEXT NOT NULL, recipient TEXT NOT NULL, recipient_label TEXT NOT NULL, local_date TEXT NOT NULL, local_time TEXT NOT NULL, timezone TEXT NOT NULL, utc_schedule TEXT NOT NULL, source_version_ids TEXT NOT NULL, source_question_ids TEXT NOT NULL, approval_hash TEXT, approved_by TEXT, approved_at TEXT, consent_version TEXT NOT NULL, PRIMARY KEY(reminder_id, version));
CREATE TABLE IF NOT EXISTS reminder_events (id TEXT PRIMARY KEY, reminder_id TEXT NOT NULL REFERENCES reminders(id), version INTEGER NOT NULL, action TEXT NOT NULL, actor_role TEXT NOT NULL, actor_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mock_reminder_operations (idempotency_key TEXT PRIMARY KEY, reminder_id TEXT NOT NULL, payload_hash TEXT NOT NULL, status TEXT NOT NULL, receipt_id TEXT NOT NULL, provider TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reminder_consents (patient_id TEXT PRIMARY KEY REFERENCES patients(id), enabled INTEGER NOT NULL, version INTEGER NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mock_callback_events (event_id TEXT PRIMARY KEY, receipt_id TEXT NOT NULL, status TEXT NOT NULL, received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_runs (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), workflow TEXT NOT NULL, status TEXT NOT NULL, model TEXT, input_count INTEGER NOT NULL, result_count INTEGER, stop_reason TEXT, created_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE IF NOT EXISTS eval_runs (id TEXT PRIMARY KEY, dataset_name TEXT NOT NULL, dataset_version TEXT NOT NULL, status TEXT NOT NULL, include_ragas INTEGER NOT NULL, model TEXT, total_cases INTEGER NOT NULL, completed_cases INTEGER NOT NULL, passed_cases INTEGER NOT NULL, aggregate_metrics TEXT NOT NULL, error TEXT, started_by TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE IF NOT EXISTS eval_case_results (id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES eval_runs(id), case_id TEXT NOT NULL, status TEXT NOT NULL, passed INTEGER NOT NULL, result TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL, UNIQUE(run_id, case_id));
CREATE TABLE IF NOT EXISTS arrangements (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL REFERENCES patients(id), action_type TEXT NOT NULL, current_version INTEGER NOT NULL, status TEXT NOT NULL, idempotency_key TEXT, provider_receipt TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS arrangement_versions (arrangement_id TEXT NOT NULL REFERENCES arrangements(id), version INTEGER NOT NULL, payload TEXT NOT NULL, source_version_ids TEXT NOT NULL, approval_hash TEXT, approved_by TEXT, approved_at TEXT, PRIMARY KEY(arrangement_id,version));
CREATE TABLE IF NOT EXISTS arrangement_events (id TEXT PRIMARY KEY, arrangement_id TEXT NOT NULL REFERENCES arrangements(id), version INTEGER NOT NULL, action TEXT NOT NULL, actor_role TEXT NOT NULL, actor_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox_events (id TEXT PRIMARY KEY, event_type TEXT NOT NULL, aggregate_id TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL, last_error TEXT, created_at TEXT NOT NULL, processed_at TEXT, UNIQUE(event_type,aggregate_id));
CREATE VIRTUAL TABLE IF NOT EXISTS summary_fts USING fts5(version_id UNINDEXED, patient_id UNINDEXED, content);
"""

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    action_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(preparation_task_actions)").fetchall()
    }
    if "documented_time" not in action_columns:
        conn.execute(
            "ALTER TABLE preparation_task_actions ADD COLUMN documented_time TEXT"
        )
    return conn

@app.on_event("startup")
def init_db():
    conn = db()
    conn.commit(); conn.close()

class DocumentOut(BaseModel):
    id: str; filename: str; content_type: str; size_bytes: int; status: str; extraction_job_id: str

class TranscriptCorrection(BaseModel):
    text: str
    actor_id: str = "demo-user"

class PublishRequest(BaseModel):
    text: str
    audience: str
    approval: bool
    actor_id: str = "demo-user"

class PatientCreate(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    actor_id: str = "demo-clinician"

class CarePartnerGrant(BaseModel):
    partner_email: str

class CarePartnerPermissionUpdate(BaseModel):
    status: str | None = None
    can_view_records: bool | None = None
    can_manage_questions: bool | None = None
    can_approve_actions: bool | None = None
    expected_version: int

class QuestionRequest(BaseModel):
    question: str

class CareQuestionCreate(BaseModel):
    text: str
    original_text: str = ""
    source_label: str = "Added by you"
    source_version_ids: list[str] = Field(default_factory=list)

class CareQuestionUpdate(BaseModel):
    text: str | None = None
    status: str | None = None

class ClinicianQuestionResponse(BaseModel):
    response: str
    status: str = "discussed"

class PreparationApproval(BaseModel):
    approval: bool

class PreparationTaskUpdate(BaseModel):
    complete: bool

class ReminderDraftRequest(BaseModel):
    task_id: str
    text: str
    local_date: str
    local_time: str
    timezone: str
    channel: str
    expected_version: int | None = None

class ReminderApproval(BaseModel):
    approval: bool
    expected_version: int

class ReminderConsentUpdate(BaseModel):
    enabled: bool

class DeliverySimulationRequest(BaseModel):
    outcome: str
    expected_version: int

class MockDeliveryCallback(BaseModel):
    event_id: str
    receipt_id: str
    status: str

class EvaluationRunRequest(BaseModel):
    include_ragas: bool = False

class ArrangementDraft(BaseModel):
    action_type: str
    payload: dict
    source_version_ids: list[str] = Field(default_factory=list)

class ArrangementApproval(BaseModel):
    approval: bool
    expected_version: int

QUESTION_STATUSES = {"open", "discussed", "follow_up_needed", "resolved"}
REMINDER_CHANNELS = {"in_app", "email", "sms"}
mock_reminder_scheduler = MockReminderScheduler()

def authorize_patient(conn: sqlite3.Connection, patient_id: str, actor_role: str, actor_id: str):
    allowed = actor_role == "clinician" or (actor_role == "patient" and actor_id == patient_id)
    if actor_role == "partner":
        allowed = conn.execute("""SELECT 1 FROM care_partner_grants g LEFT JOIN care_partner_permissions p ON p.grant_id=g.id
            WHERE g.patient_id=? AND lower(g.partner_email)=lower(?) AND g.status='active'
            AND COALESCE(p.can_view_records,1)=1""", (patient_id, actor_id)).fetchone() is not None
    if not allowed: raise HTTPException(403, "You do not have access to this patient workspace.")

def require_clinician(actor_role: str, actor_id: str):
    if actor_role != "clinician" or not actor_id:
        raise HTTPException(403, "Clinician access is required.")

def serialize_care_question(row: sqlite3.Row):
    item = dict(row)
    item["source_version_ids"] = json.loads(item["source_version_ids"])
    return item

def record_question_event(
    conn: sqlite3.Connection,
    question_id: str,
    action: str,
    actor_role: str,
    actor_id: str,
    payload: dict,
):
    conn.execute(
        "INSERT INTO care_question_events VALUES (?,?,?,?,?,?,?)",
        (
            str(uuid4()),
            question_id,
            action,
            actor_role,
            actor_id,
            json.dumps(payload, sort_keys=True),
            datetime.now(timezone.utc).isoformat(),
        ),
    )

def serialize_preparation_plan(conn: sqlite3.Connection, row: sqlite3.Row):
    plan = dict(row)
    plan["verified"] = bool(plan["verified"])
    tasks = conn.execute(
        "SELECT * FROM preparation_tasks WHERE plan_id=? ORDER BY position",
        (row["id"],),
    ).fetchall()
    plan["items"] = []
    for task_row in tasks:
        task = dict(task_row)
        task["source_version_ids"] = json.loads(task["source_version_ids"])
        task["source_question_ids"] = json.loads(task["source_question_ids"])
        action = conn.execute("SELECT * FROM preparation_task_actions WHERE task_id=?", (task["id"],)).fetchone()
        task["action"] = dict(action) if action else {"action_type":"none","specialist_status":"not_applicable"}
        labels = []
        for version_id in task["source_version_ids"]:
            source = conn.execute("""
              SELECT d.filename,dv.version FROM document_versions dv
              JOIN extraction_jobs j ON j.id=dv.job_id
              JOIN documents d ON d.id=j.document_id WHERE dv.id=?
            """, (version_id,)).fetchone()
            if source:
                labels.append(f'{source["filename"]} · Version {source["version"]}')
        for question_id in task["source_question_ids"]:
            source = conn.execute(
                "SELECT text FROM care_questions WHERE id=?", (question_id,)
            ).fetchone()
            if source:
                labels.append(f'Question: {source["text"]}')
        task["source_labels"] = labels
        plan["items"].append(task)
    return plan

def record_preparation_event(
    conn: sqlite3.Connection,
    plan_id: str,
    task_id: str | None,
    action: str,
    actor_role: str,
    actor_id: str,
    payload: dict,
):
    conn.execute(
        "INSERT INTO preparation_events VALUES (?,?,?,?,?,?,?,?)",
        (
            str(uuid4()),
            plan_id,
            task_id,
            action,
            actor_role,
            actor_id,
            json.dumps(payload, sort_keys=True),
            datetime.now(timezone.utc).isoformat(),
        ),
    )

def validate_reminder_schedule(local_date: str, local_time: str, timezone_name: str):
    try:
        local_value = datetime.fromisoformat(f"{local_date}T{local_time}")
    except ValueError as exc:
        raise HTTPException(400, "Enter a valid local date and time.") from exc
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(400, "Select a valid IANA timezone.") from exc
    candidates = []
    for fold in (0, 1):
        aware = local_value.replace(tzinfo=zone, fold=fold)
        utc_value = aware.astimezone(timezone.utc)
        round_trip = utc_value.astimezone(zone)
        if round_trip.replace(tzinfo=None) == local_value and round_trip.fold == fold:
            candidates.append(utc_value)
    unique_candidates = {candidate.isoformat(): candidate for candidate in candidates}
    if not unique_candidates:
        raise HTTPException(
            400, "That local time does not exist because of a daylight-saving change."
        )
    if len(unique_candidates) > 1:
        raise HTTPException(
            400, "That local time occurs twice because of a daylight-saving change. Choose another time."
        )
    utc_value = next(iter(unique_candidates.values()))
    if utc_value <= datetime.now(timezone.utc):
        raise HTTPException(400, "The reminder time must be in the future.")
    return utc_value.isoformat()

def reminder_recipient(patient: sqlite3.Row, channel: str):
    if channel == "in_app":
        return patient["id"], patient["name"]
    if channel == "email" and patient["email"]:
        return patient["email"], patient["email"]
    if channel == "sms" and patient["phone"]:
        return patient["phone"], patient["phone"]
    raise HTTPException(400, f"The patient has no contact information for {channel}.")

def reminder_payload(row: sqlite3.Row):
    return {
        "reminder_id": row["reminder_id"],
        "patient_id": row["patient_id"],
        "task_id": row["task_id"],
        "version": row["version"],
        "text": row["text"],
        "channel": row["channel"],
        "recipient": row["recipient"],
        "local_date": row["local_date"],
        "local_time": row["local_time"],
        "timezone": row["timezone"],
        "utc_schedule": row["utc_schedule"],
        "source_version_ids": json.loads(row["source_version_ids"]),
        "source_question_ids": json.loads(row["source_question_ids"]),
        "consent_version": row["consent_version"],
    }

def serialize_reminder(conn: sqlite3.Connection, reminder_id: str):
    row = conn.execute("""
      SELECT r.id AS reminder_id,r.patient_id,r.task_id,r.current_version,
             r.status,r.idempotency_key,r.provider_receipt,r.created_at,r.updated_at,
             rv.version,rv.text,rv.channel,rv.recipient,rv.recipient_label,
             rv.local_date,rv.local_time,rv.timezone,rv.utc_schedule,
             rv.source_version_ids,rv.source_question_ids,rv.approval_hash,
             rv.approved_by,rv.approved_at,rv.consent_version,t.title AS task_title
      FROM reminders r
      JOIN reminder_versions rv ON rv.reminder_id=r.id AND rv.version=r.current_version
      JOIN preparation_tasks t ON t.id=r.task_id
      WHERE r.id=?
    """, (reminder_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["source_version_ids"] = json.loads(result["source_version_ids"])
    result["source_question_ids"] = json.loads(result["source_question_ids"])
    latest_event = conn.execute(
        """SELECT action,payload FROM reminder_events WHERE reminder_id=?
           ORDER BY created_at DESC,rowid DESC LIMIT 1""",
        (reminder_id,),
    ).fetchone()
    event_payload = json.loads(latest_event["payload"]) if latest_event else {}
    result["status_reason"] = event_payload.get("reason")
    result["simulation"] = True
    return result

def record_reminder_event(
    conn: sqlite3.Connection,
    reminder_id: str,
    version: int,
    action: str,
    actor_role: str,
    actor_id: str,
    payload: dict,
):
    conn.execute(
        "INSERT INTO reminder_events VALUES (?,?,?,?,?,?,?,?)",
        (
            str(uuid4()), reminder_id, version, action, actor_role, actor_id,
            json.dumps(payload, sort_keys=True), datetime.now(timezone.utc).isoformat(),
        ),
    )

def start_workflow_run(
    patient_id: str, workflow: str, model: str | None, input_count: int
):
    run_id = str(uuid4())
    conn = db()
    conn.execute(
        """INSERT INTO workflow_runs
           (id,patient_id,workflow,status,model,input_count,result_count,
            stop_reason,created_at,completed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id, patient_id, workflow, "running", model, input_count,
            None, None, datetime.now(timezone.utc).isoformat(), None,
        ),
    )
    conn.commit()
    conn.close()
    return run_id

def finish_workflow_run(
    run_id: str, status: str, result_count: int, stop_reason: str | None = None
):
    conn = db()
    conn.execute(
        """UPDATE workflow_runs SET status=?,result_count=?,stop_reason=?,
           completed_at=? WHERE id=?""",
        (
            status, result_count, stop_reason,
            datetime.now(timezone.utc).isoformat(), run_id,
        ),
    )
    conn.commit()
    conn.close()

def pause_affected_reminders(
    conn: sqlite3.Connection,
    *,
    reason: str,
    actor_role: str,
    actor_id: str,
    version_ids: set[str] | None = None,
    question_ids: set[str] | None = None,
    task_ids: set[str] | None = None,
    patient_ids: set[str] | None = None,
):
    version_ids = version_ids or set()
    question_ids = question_ids or set()
    task_ids = task_ids or set()
    patient_ids = patient_ids or set()
    rows = conn.execute("""
      SELECT r.*,rv.source_version_ids,rv.source_question_ids
      FROM reminders r JOIN reminder_versions rv
        ON rv.reminder_id=r.id AND rv.version=r.current_version
      WHERE r.status IN ('awaiting_approval','awaiting_reapproval','scheduled')
    """).fetchall()
    paused = []
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        matches = (
            row["patient_id"] in patient_ids
            or row["task_id"] in task_ids
            or bool(set(json.loads(row["source_version_ids"])) & version_ids)
            or bool(set(json.loads(row["source_question_ids"])) & question_ids)
        )
        if not matches:
            continue
        if row["idempotency_key"]:
            mock_reminder_scheduler.cancel(
                conn, idempotency_key=row["idempotency_key"], now=now
            )
        conn.execute(
            "UPDATE reminders SET status='paused',updated_at=? WHERE id=?",
            (now, row["id"]),
        )
        record_reminder_event(
            conn,
            row["id"],
            row["current_version"],
            "paused_by_dependency_change",
            actor_role,
            actor_id,
            {"reason": reason},
        )
        paused.append(row["id"])
    return paused

def invalidate_preparation_sources(
    conn: sqlite3.Connection,
    *,
    version_ids: set[str],
    reason: str,
    actor_role: str,
    actor_id: str,
):
    affected_plan_ids = set()
    affected_task_ids = set()
    rows = conn.execute("""
      SELECT t.id,t.plan_id,t.source_version_ids FROM preparation_tasks t
      JOIN preparation_plans p ON p.id=t.plan_id
      WHERE p.status='approved'
    """).fetchall()
    for row in rows:
        if set(json.loads(row["source_version_ids"])) & version_ids:
            affected_plan_ids.add(row["plan_id"])
            affected_task_ids.add(row["id"])
    for plan_id in affected_plan_ids:
        conn.execute(
            """UPDATE preparation_plans SET status='needs_review',message=?
               WHERE id=?""",
            (reason, plan_id),
        )
        record_preparation_event(
            conn,
            plan_id,
            None,
            "sources_invalidated",
            actor_role,
            actor_id,
            {"reason": reason, "source_version_ids": sorted(version_ids)},
        )
    if affected_task_ids:
        pause_affected_reminders(
            conn,
            reason=reason,
            actor_role=actor_role,
            actor_id=actor_id,
            task_ids=affected_task_ids,
            version_ids=version_ids,
        )
    return affected_plan_ids

def current_reminder_consent(conn: sqlite3.Connection, patient_id: str):
    row = conn.execute(
        "SELECT * FROM reminder_consents WHERE patient_id=?", (patient_id,)
    ).fetchone()
    if row:
        return {
            "patient_id": patient_id,
            "enabled": bool(row["enabled"]),
            "version": row["version"],
            "consent_version": f'reminder-consent-v{row["version"]}',
            "updated_at": row["updated_at"],
        }
    return {
        "patient_id": patient_id,
        "enabled": True,
        "version": 1,
        "consent_version": "reminder-consent-v1",
        "updated_at": None,
    }

def invalidate_preparation_questions(
    conn: sqlite3.Connection,
    *,
    question_ids: set[str],
    reason: str,
    actor_role: str,
    actor_id: str,
):
    affected_plan_ids = set()
    affected_task_ids = set()
    rows = conn.execute("""
      SELECT t.id,t.plan_id,t.source_question_ids FROM preparation_tasks t
      JOIN preparation_plans p ON p.id=t.plan_id
      WHERE p.status='approved'
    """).fetchall()
    for row in rows:
        if set(json.loads(row["source_question_ids"])) & question_ids:
            affected_plan_ids.add(row["plan_id"])
            affected_task_ids.add(row["id"])
    for plan_id in affected_plan_ids:
        conn.execute(
            "UPDATE preparation_plans SET status='needs_review',message=? WHERE id=?",
            (reason, plan_id),
        )
        record_preparation_event(
            conn,
            plan_id,
            None,
            "question_sources_invalidated",
            actor_role,
            actor_id,
            {"reason": reason, "source_question_ids": sorted(question_ids)},
        )
    if affected_task_ids:
        pause_affected_reminders(
            conn,
            reason=reason,
            actor_role=actor_role,
            actor_id=actor_id,
            task_ids=affected_task_ids,
            question_ids=question_ids,
        )
    return affected_plan_ids

@app.get("/api/v1/patients")
def list_patients(actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    conn = db(); rows = conn.execute("""SELECT p.id,p.name,p.email,p.phone,p.created_at,COUNT(dv.id) AS summary_count FROM patients p LEFT JOIN patient_documents pd ON pd.patient_id=p.id LEFT JOIN extraction_jobs j ON j.document_id=pd.document_id LEFT JOIN document_versions dv ON dv.job_id=j.id GROUP BY p.id ORDER BY p.name""").fetchall(); conn.close()
    return [dict(row) for row in rows]

@app.post("/api/v1/patients", status_code=201)
def create_patient(patient: PatientCreate, actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    if not patient.name.strip() or (not patient.email and not patient.phone):
        raise HTTPException(400, "Name and at least one contact method are required.")
    patient_id = f"CBP-{uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    conn = db(); conn.execute("INSERT INTO patients VALUES (?,?,?,?,?,?)", (patient_id, patient.name.strip(), patient.email, patient.phone, actor_id, now)); conn.commit(); conn.close()
    return {"id": patient_id, "name": patient.name.strip(), "email": patient.email, "phone": patient.phone, "created_at": now}

@app.post("/api/v1/patients/{patient_id}/care-partners", status_code=201)
def grant_care_partner(patient_id: str, grant: CarePartnerGrant, actor_role: str = "", actor_id: str = ""):
    email = grant.partner_email.strip().lower()
    if not email: raise HTTPException(400, "Care-partner email is required.")
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close(); raise HTTPException(403, "Only the patient can authorize a care partner.")
    if conn.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone() is None:
        conn.close(); raise HTTPException(404, "Patient not found.")
    now = datetime.now(timezone.utc).isoformat()
    existing = conn.execute("SELECT id FROM care_partner_grants WHERE patient_id=? AND partner_email=?", (patient_id, email)).fetchone()
    grant_id = existing["id"] if existing else str(uuid4())
    conn.execute("INSERT INTO care_partner_grants VALUES (?,?,?,?,?) ON CONFLICT(patient_id,partner_email) DO UPDATE SET status='active'", (grant_id, patient_id, email, "active", now))
    conn.execute("INSERT INTO care_partner_permissions VALUES (?,?,?,?,?,?,?) ON CONFLICT(grant_id) DO NOTHING", (grant_id, 1, 1, 0, 1, actor_id, now))
    conn.commit(); conn.close()
    return {"id": grant_id, "patient_id": patient_id, "partner_email": email, "status": "active"}

@app.get("/api/v1/patients/{patient_id}/care-partners")
def list_care_partners(patient_id: str, actor_role: str = "", actor_id: str = ""):
    conn = db(); authorize_patient(conn, patient_id, actor_role, actor_id)
    rows = conn.execute("""SELECT g.id,g.partner_email,g.status,g.created_at,
        COALESCE(p.can_view_records,1) can_view_records,COALESCE(p.can_manage_questions,1) can_manage_questions,
        COALESCE(p.can_approve_actions,0) can_approve_actions,COALESCE(p.version,1) version,p.updated_at
        FROM care_partner_grants g LEFT JOIN care_partner_permissions p ON p.grant_id=g.id
        WHERE g.patient_id=? ORDER BY g.created_at""", (patient_id,)).fetchall()
    result=[]
    for row in rows:
        item=dict(row)
        for field in ("can_view_records","can_manage_questions","can_approve_actions"): item[field]=bool(item[field])
        result.append(item)
    conn.close(); return result

@app.patch("/api/v1/patients/{patient_id}/care-partners/{grant_id}")
def update_care_partner(patient_id: str, grant_id: str, request: CarePartnerPermissionUpdate, actor_role: str = "", actor_id: str = ""):
    conn = db(); authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close(); raise HTTPException(403, "Only the patient can change sharing permissions.")
    row = conn.execute("""SELECT g.status,COALESCE(p.can_view_records,1) can_view_records,
        COALESCE(p.can_manage_questions,1) can_manage_questions,COALESCE(p.can_approve_actions,0) can_approve_actions,
        COALESCE(p.version,1) version FROM care_partner_grants g LEFT JOIN care_partner_permissions p ON p.grant_id=g.id
        WHERE g.id=? AND g.patient_id=?""", (grant_id, patient_id)).fetchone()
    if not row: conn.close(); raise HTTPException(404, "Care-partner permission was not found.")
    if row["version"] != request.expected_version: conn.close(); raise HTTPException(409, "Permissions changed. Refresh before trying again.")
    status=request.status or row["status"]
    if status not in {"active","revoked"}: conn.close(); raise HTTPException(400, "Status must be active or revoked.")
    values={field:int(getattr(request,field) if getattr(request,field) is not None else bool(row[field])) for field in ("can_view_records","can_manage_questions","can_approve_actions")}
    if status == "revoked": values={field:0 for field in values}
    version=row["version"]+1; now=datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE care_partner_grants SET status=? WHERE id=?", (status,grant_id))
    conn.execute("""INSERT INTO care_partner_permissions VALUES (?,?,?,?,?,?,?) ON CONFLICT(grant_id) DO UPDATE SET
        can_view_records=excluded.can_view_records,can_manage_questions=excluded.can_manage_questions,
        can_approve_actions=excluded.can_approve_actions,version=excluded.version,updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
        (grant_id,values["can_view_records"],values["can_manage_questions"],values["can_approve_actions"],version,actor_id,now))
    conn.commit(); conn.close()
    return {"id":grant_id,"status":status,"version":version,**{key:bool(value) for key,value in values.items()}}

@app.get("/health")
def health(): return {"status": "ok", "service": "carebridge-api"}

@app.post("/api/v1/documents", response_model=DocumentOut, status_code=202)
async def upload_document(file: Annotated[UploadFile, File()], workspace_id: str = "demo-workspace", patient_id: str | None = None, actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    if not patient_id:
        raise HTTPException(400, "A patient workspace is required for document upload.")
    if file.content_type not in ALLOWED:
        raise HTTPException(415, "Only PDF, JPEG, and PNG files are supported.")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Files must be 10 MB or smaller.")
    if not content:
        raise HTTPException(400, "The uploaded file is empty.")
    now = datetime.now(timezone.utc).isoformat()
    document_id, job_id = str(uuid4()), str(uuid4())
    digest = hashlib.sha256(content).hexdigest()
    conn = db()
    conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)", (document_id, workspace_id, file.filename or "untitled", file.content_type, len(content), digest, "queued", now))
    (STORAGE_PATH / document_id).write_bytes(content)
    conn.execute("INSERT INTO extraction_jobs VALUES (?,?,?,?)", (job_id, document_id, "queued", now))
    if patient_id:
        patient = conn.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone()
        if patient is None:
            conn.rollback(); conn.close(); (STORAGE_PATH / document_id).unlink(missing_ok=True)
            raise HTTPException(404, "Patient not found.")
        conn.execute("INSERT INTO patient_documents VALUES (?,?)", (patient_id, document_id))
    conn.commit(); conn.close()
    return DocumentOut(id=document_id, filename=file.filename or "untitled", content_type=file.content_type, size_bytes=len(content), status="queued", extraction_job_id=job_id)

@app.get("/api/v1/documents")
def list_documents(workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    conn = db(); rows = conn.execute("SELECT id,filename,content_type,size_bytes,status,created_at FROM documents WHERE workspace_id=? ORDER BY created_at DESC", (workspace_id,)).fetchall(); conn.close()
    return [dict(row) for row in rows]

@app.get("/api/v1/documents/{document_id}")
def get_document(document_id: str, workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    conn = db()
    row = conn.execute("""
        SELECT d.id, d.filename, d.content_type, d.size_bytes, d.sha256,
               d.status, d.created_at, j.id AS extraction_job_id, j.status AS extraction_status,
               pd.patient_id
        FROM documents d JOIN extraction_jobs j ON j.document_id = d.id
        JOIN patient_documents pd ON pd.document_id=d.id
        WHERE d.id = ? AND d.workspace_id = ?
    """, (document_id, workspace_id)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Document not found.")
    authorize_patient(conn, row["patient_id"], actor_role, actor_id)
    result = dict(row); result.pop("patient_id", None); conn.close(); return result

@app.get("/api/v1/documents/{document_id}/content")
def get_document_content(document_id: str, workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    conn = db(); row = conn.execute("SELECT d.content_type,d.filename,pd.patient_id FROM documents d JOIN patient_documents pd ON pd.document_id=d.id WHERE d.id=? AND d.workspace_id=?", (document_id, workspace_id)).fetchone()
    path = STORAGE_PATH / document_id
    if row is None or not path.exists(): conn.close(); raise HTTPException(404, "Document content not found.")
    authorize_patient(conn, row["patient_id"], actor_role, actor_id); conn.close()
    return FileResponse(path, media_type=row["content_type"], filename=row["filename"], content_disposition_type="inline")

@app.get("/api/v1/extraction-jobs/{job_id}")
def get_extraction_job(job_id: str, workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    conn = db()
    row = conn.execute("""
        SELECT j.id, j.document_id, j.status, j.created_at,
               r.pages, r.provider, pd.patient_id
        FROM extraction_jobs j JOIN documents d ON d.id = j.document_id
        JOIN patient_documents pd ON pd.document_id=d.id
        LEFT JOIN extraction_results r ON r.job_id = j.id
        WHERE j.id = ? AND d.workspace_id = ?
    """, (job_id, workspace_id)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Extraction job not found.")
    authorize_patient(conn, row["patient_id"], actor_role, actor_id)
    result = dict(row); result.pop("patient_id", None); conn.close(); return result

@app.get("/api/v1/extraction-jobs/{job_id}/result")
def get_extraction_result(job_id: str, workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    conn = db()
    row = conn.execute("""
        SELECT r.job_id, j.document_id, pd.patient_id, r.text AS original_text,
               COALESCE((SELECT tv.text FROM transcript_versions tv WHERE tv.job_id=j.id ORDER BY tv.version DESC LIMIT 1), r.text) AS text,
               r.pages, r.provider, r.created_at
        FROM extraction_results r
        JOIN extraction_jobs j ON j.id = r.job_id
        JOIN documents d ON d.id = j.document_id
        LEFT JOIN patient_documents pd ON pd.document_id=d.id
        WHERE r.job_id = ? AND d.workspace_id = ?
    """, (job_id, workspace_id)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Extraction result not available.")
    authorize_patient(conn, row["patient_id"], actor_role, actor_id)
    result = dict(row); conn.close(); return result

@app.post("/api/v1/extraction-jobs/{job_id}/transcript", status_code=201)
def save_transcript_correction(job_id: str, correction: TranscriptCorrection, workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    if not correction.text.strip(): raise HTTPException(400, "Transcript text is required.")
    conn = db()
    exists = conn.execute("SELECT pd.patient_id FROM extraction_jobs j JOIN documents d ON d.id=j.document_id JOIN patient_documents pd ON pd.document_id=d.id WHERE j.id=? AND d.workspace_id=?", (job_id, workspace_id)).fetchone()
    if exists is None:
        conn.close(); raise HTTPException(404, "Extraction job not found.")
    version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM transcript_versions WHERE job_id=?", (job_id,)).fetchone()[0]
    transcript_id = str(uuid4())
    conn.execute("INSERT INTO transcript_versions VALUES (?,?,?,?,?,?)", (transcript_id, job_id, correction.text, version, actor_id, datetime.now(timezone.utc).isoformat()))
    conn.commit(); conn.close()
    return {"id": transcript_id, "job_id": job_id, "version": version}

@app.post("/api/v1/extraction-jobs/{job_id}/publish", status_code=201)
def publish_document(job_id: str, request: PublishRequest, workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    if not request.approval:
        raise HTTPException(400, "Explicit approval is required.")
    if not request.audience.strip() or not request.text.strip():
        raise HTTPException(400, "Audience and reviewed transcript are required.")
    conn = db()
    exists = conn.execute("SELECT pd.patient_id FROM extraction_jobs j JOIN documents d ON d.id=j.document_id JOIN patient_documents pd ON pd.document_id=d.id WHERE j.id=? AND d.workspace_id=?", (job_id, workspace_id)).fetchone()
    if exists is None:
        conn.close(); raise HTTPException(404, "Extraction job not found.")
    version = conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM document_versions WHERE job_id=?", (job_id,)).fetchone()[0]
    version_id = str(uuid4())
    import json
    now=datetime.now(timezone.utc).isoformat()
    conn.execute("INSERT INTO document_versions VALUES (?,?,?,?,?,?,?)", (version_id, job_id, json.dumps({"text": request.text, "audience": request.audience}, sort_keys=True), version, "indexing_pending", actor_id, now))
    conn.execute("INSERT INTO outbox_events VALUES (?,?,?,?,?,?,?,?,?)", (str(uuid4()),"DocumentPublished",version_id,json.dumps({"version_id":version_id,"job_id":job_id,"version":version,"audience":request.audience}),"pending",0,None,now,None))
    conn.commit(); conn.close()
    return {"id": version_id, "job_id": job_id, "version": version, "status": "indexing_pending", "audience": request.audience}

@app.post("/api/v1/document-versions/{version_id}/index")
def index_document_version(version_id: str, actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    conn = db()
    row = conn.execute("""
      SELECT dv.id,dv.payload,dv.version,dv.job_id,dv.status,pd.patient_id,j.document_id FROM document_versions dv
      JOIN extraction_jobs j ON j.id=dv.job_id
      JOIN patient_documents pd ON pd.document_id=j.document_id
      WHERE dv.id=?
    """, (version_id,)).fetchone()
    if row is None:
        conn.close(); raise HTTPException(404, "Published document version not found.")
    latest_version = conn.execute(
        "SELECT MAX(version) FROM document_versions WHERE job_id=?",
        (row["job_id"],),
    ).fetchone()[0]
    if row["version"] < latest_version:
        if row["status"] != "index_ready":
            conn.execute(
                "UPDATE document_versions SET status='superseded' WHERE id=?",
                (version_id,),
            )
            conn.commit()
        conn.execute("UPDATE outbox_events SET status='processed',attempts=attempts+1,processed_at=?,last_error='superseded before indexing' WHERE event_type='DocumentPublished' AND aggregate_id=?", (datetime.now(timezone.utc).isoformat(),version_id)); conn.commit()
        status = "index_ready" if row["status"] == "index_ready" else "superseded"
        conn.close()
        return {
            "version_id": version_id,
            "status": status,
            "retrieval_modes": [],
            "semantic_warning": "A newer published version exists; this version was not activated.",
        }
    import json
    content = json.loads(row["payload"])["text"]
    old_rows = conn.execute(
        """SELECT id FROM document_versions
           WHERE job_id=? AND id!=? AND status='index_ready'""",
        (row["job_id"], version_id),
    ).fetchall()
    old_version_ids = {old["id"] for old in old_rows}
    if old_version_ids:
        placeholders = ",".join("?" for _ in old_version_ids)
        conn.execute(
            f"UPDATE document_versions SET status='superseded' WHERE id IN ({placeholders})",
            tuple(old_version_ids),
        )
        conn.execute(
            f"DELETE FROM summary_fts WHERE version_id IN ({placeholders})",
            tuple(old_version_ids),
        )
        invalidate_preparation_sources(
            conn,
            version_ids=old_version_ids,
            reason="A newer approved version of a source summary is available. Build and approve a new checklist.",
            actor_role="system",
            actor_id="indexing-worker",
        )
    conn.execute("DELETE FROM summary_fts WHERE version_id=?", (version_id,))
    conn.execute("INSERT INTO summary_fts(version_id,patient_id,content) VALUES (?,?,?)", (version_id, row["patient_id"], content))
    conn.execute("UPDATE document_versions SET status='index_ready' WHERE id=?", (version_id,))
    conn.commit(); conn.close()
    retrieval_modes = ["bm25"]
    semantic_warning = None
    if semantic_configured():
        try:
            index_semantically(
                patient_id=row["patient_id"],
                version_id=version_id,
                document_id=row["document_id"],
                version=row["version"],
                text=content,
            )
            retrieval_modes.append("semantic")
        except SemanticUnavailable:
            logger.exception("Semantic indexing failed for version %s", version_id)
            semantic_warning = "Semantic indexing is unavailable; BM25 indexing succeeded."
    event_conn=db(); event_conn.execute("UPDATE outbox_events SET status='processed',attempts=attempts+1,processed_at=?,last_error=? WHERE event_type='DocumentPublished' AND aggregate_id=?",(datetime.now(timezone.utc).isoformat(),semantic_warning,version_id)); event_conn.commit(); event_conn.close()
    return {
        "version_id": version_id,
        "status": "index_ready",
        "retrieval_modes": retrieval_modes,
        "semantic_warning": semantic_warning,
    }

@app.post("/api/v1/workers/publication-index/run")
def run_publication_index_worker(actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role,actor_id)
    conn=db(); rows=conn.execute("SELECT aggregate_id FROM outbox_events WHERE event_type='DocumentPublished' AND status='pending' ORDER BY created_at LIMIT 20").fetchall(); conn.close()
    processed=[]; failed=[]
    for row in rows:
        try: processed.append(index_document_version(row["aggregate_id"], actor_role, actor_id))
        except Exception as exc:
            failed.append(row["aggregate_id"]); failure=db(); failure.execute("UPDATE outbox_events SET attempts=attempts+1,last_error=? WHERE event_type='DocumentPublished' AND aggregate_id=?",(type(exc).__name__,row["aggregate_id"])); failure.commit(); failure.close()
    return {"processed":len(processed),"failed":len(failed),"pending_examined":len(rows)}

@app.get("/api/v1/patients/{patient_id}/search")
def search_patient_summaries(patient_id: str, q: str, actor_role: str = "", actor_id: str = ""):
    conn = db(); authorize_patient(conn, patient_id, actor_role, actor_id)
    if not q.strip():
        conn.close()
        return {"query": q, "retrieval_mode": "bm25", "results": []}
    tokens = re.findall(r"[A-Za-z0-9]+", q.lower())
    lexical_rows = []
    if tokens:
        match = " OR ".join(f'"{token}"*' for token in tokens)
        lexical_rows = conn.execute("""
          SELECT summary_fts.version_id,summary_fts.content,bm25(summary_fts) AS score,d.id AS document_id,d.filename,dv.version
          FROM summary_fts JOIN document_versions dv ON dv.id=summary_fts.version_id
          JOIN extraction_jobs j ON j.id=dv.job_id JOIN documents d ON d.id=j.document_id
          WHERE summary_fts MATCH ? AND summary_fts.patient_id=? AND dv.status='index_ready'
          ORDER BY score LIMIT 10
        """, (match, patient_id)).fetchall()

    lexical_ids = [row["version_id"] for row in lexical_rows]
    semantic_ids: list[str] = []
    semantic_warning = None
    if semantic_configured():
        try:
            semantic_ids = [
                match.version_id for match in search_semantically(patient_id, q.strip())
            ]
        except SemanticUnavailable:
            logger.exception("Semantic search failed for patient %s", patient_id)
            semantic_warning = "Semantic search is unavailable; BM25 results are shown."

    ranked = reciprocal_rank_fusion([lexical_ids, semantic_ids])[:5]
    ranked_ids = [identifier for identifier, _ in ranked]
    rows_by_id = {row["version_id"]: dict(row) for row in lexical_rows}
    missing_ids = [identifier for identifier in ranked_ids if identifier not in rows_by_id]
    if missing_ids:
        placeholders = ",".join("?" for _ in missing_ids)
        hydrated = conn.execute(f"""
          SELECT dv.id AS version_id,json_extract(dv.payload,'$.text') AS content,
                 d.id AS document_id,d.filename,dv.version
          FROM document_versions dv
          JOIN extraction_jobs j ON j.id=dv.job_id
          JOIN documents d ON d.id=j.document_id
          JOIN patient_documents pd ON pd.document_id=d.id
          WHERE dv.id IN ({placeholders}) AND pd.patient_id=? AND dv.status='index_ready'
        """, (*missing_ids, patient_id)).fetchall()
        rows_by_id.update({row["version_id"]: dict(row) for row in hydrated})
    conn.close()

    results = []
    fused_scores = dict(ranked)
    for identifier in ranked_ids:
        row = rows_by_id.get(identifier)
        if row:
            row["score"] = fused_scores[identifier]
            results.append(row)
    return {
        "query": q,
        "retrieval_mode": "hybrid" if semantic_ids else "bm25",
        "semantic_warning": semantic_warning,
        "results": results,
    }

@app.post("/api/v1/patients/{patient_id}/answer")
def answer_patient_question(
    patient_id: str,
    request: QuestionRequest,
    actor_role: str = "",
    actor_id: str = "",
):
    question = request.question.strip()
    if not question:
        raise HTTPException(400, "A question is required.")
    if len(question) > 1_000:
        raise HTTPException(400, "Questions must be 1,000 characters or fewer.")
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    evidence_count = conn.execute(
        """SELECT COUNT(*) FROM document_versions dv
           JOIN extraction_jobs j ON j.id=dv.job_id
           JOIN patient_documents pd ON pd.document_id=j.document_id
           WHERE pd.patient_id=? AND dv.status='index_ready'""",
        (patient_id,),
    ).fetchone()[0]
    conn.close()
    run_id = start_workflow_run(
        patient_id, "grounded_answer", os.getenv("OPENAI_ANSWER_MODEL", "gpt-4o-mini"),
        evidence_count,
    )

    def retrieve(authorized_question: str):
        return search_patient_summaries(
            patient_id, authorized_question, actor_role, actor_id
        )

    try:
        result = answer_question(question, retrieve)
        finish_workflow_run(
            run_id,
            "stopped" if result["abstained"] else "completed",
            len(result["citations"]),
            "insufficient_supported_evidence" if result["abstained"] else None,
        )
        result["run_id"] = run_id
        return result
    except AnswerUnavailable as exc:
        finish_workflow_run(run_id, "failed", 0, "model_unavailable")
        logger.exception("Answer workflow failed for patient %s", patient_id)
        raise HTTPException(503, str(exc)) from exc

@app.post("/api/v1/patients/{patient_id}/questions", status_code=201)
def create_care_question(
    patient_id: str,
    request: CareQuestionCreate,
    actor_role: str = "",
    actor_id: str = "",
):
    text = request.text.strip()
    if not text:
        raise HTTPException(400, "Question text is required.")
    if len(text) > 1_000:
        raise HTTPException(400, "Questions must be 1,000 characters or fewer.")
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role not in {"patient", "partner"}:
        conn.close()
        raise HTTPException(403, "Only patients and authorized care partners can save questions here.")

    source_ids = list(dict.fromkeys(request.source_version_ids))[:5]
    if source_ids:
        placeholders = ",".join("?" for _ in source_ids)
        count = conn.execute(f"""
          SELECT COUNT(DISTINCT dv.id) FROM document_versions dv
          JOIN extraction_jobs j ON j.id=dv.job_id
          JOIN patient_documents pd ON pd.document_id=j.document_id
          WHERE dv.id IN ({placeholders}) AND pd.patient_id=? AND dv.status='index_ready'
        """, (*source_ids, patient_id)).fetchone()[0]
        if count != len(source_ids):
            conn.close()
            raise HTTPException(400, "One or more question sources are not available in this patient workspace.")

    question_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    original_text = request.original_text.strip() or text
    source_label = request.source_label.strip()[:500] or "Added by you"
    conn.execute(
        "INSERT INTO care_questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            question_id,
            patient_id,
            text,
            original_text,
            source_label,
            json.dumps(source_ids),
            "open",
            actor_role,
            actor_id,
            None,
            None,
            now,
            now,
        ),
    )
    record_question_event(
        conn, question_id, "created", actor_role, actor_id, {"status": "open"}
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM care_questions WHERE id=?", (question_id,)
    ).fetchone()
    conn.close()
    return serialize_care_question(row)

@app.get("/api/v1/patients/{patient_id}/questions")
def list_care_questions(
    patient_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    rows = conn.execute("""
      SELECT * FROM care_questions WHERE patient_id=?
      ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'follow_up_needed' THEN 1
               WHEN 'discussed' THEN 2 ELSE 3 END, updated_at DESC
    """, (patient_id,)).fetchall()
    conn.close()
    return [serialize_care_question(row) for row in rows]

@app.patch("/api/v1/patients/{patient_id}/questions/{question_id}")
def update_care_question(
    patient_id: str,
    question_id: str,
    request: CareQuestionUpdate,
    actor_role: str = "",
    actor_id: str = "",
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role not in {"patient", "partner"}:
        conn.close()
        raise HTTPException(403, "Patients and authorized care partners edit question wording and status here.")
    row = conn.execute(
        "SELECT * FROM care_questions WHERE id=? AND patient_id=?",
        (question_id, patient_id),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Question not found.")
    text = row["text"] if request.text is None else request.text.strip()
    status = row["status"] if request.status is None else request.status
    if not text or len(text) > 1_000:
        conn.close()
        raise HTTPException(400, "Question text must be between 1 and 1,000 characters.")
    if status not in QUESTION_STATUSES:
        conn.close()
        raise HTTPException(400, "Question status is invalid.")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE care_questions SET text=?,status=?,updated_at=? WHERE id=?",
        (text, status, now, question_id),
    )
    record_question_event(
        conn,
        question_id,
        "updated",
        actor_role,
        actor_id,
        {"status": status, "text_changed": text != row["text"]},
    )
    if text != row["text"] or (status == "resolved" and row["status"] != "resolved"):
        invalidate_preparation_questions(
            conn,
            question_ids={question_id},
            reason="A question used by this checklist changed or was resolved. Review the preparation plan.",
            actor_role=actor_role,
            actor_id=actor_id,
        )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM care_questions WHERE id=?", (question_id,)
    ).fetchone()
    conn.close()
    return serialize_care_question(updated)

@app.get("/api/v1/clinician/questions")
def list_clinician_questions(actor_role: str = "", actor_id: str = ""):
    if actor_role != "clinician" or not actor_id:
        raise HTTPException(403, "Clinician access is required.")
    conn = db()
    rows = conn.execute("""
      SELECT cq.*,p.name AS patient_name FROM care_questions cq
      JOIN patients p ON p.id=cq.patient_id
      ORDER BY CASE cq.status WHEN 'open' THEN 0 WHEN 'follow_up_needed' THEN 1
               WHEN 'discussed' THEN 2 ELSE 3 END, cq.updated_at DESC
    """).fetchall()
    conn.close()
    return [serialize_care_question(row) for row in rows]

@app.post("/api/v1/clinician/questions/{question_id}/respond")
def respond_to_care_question(
    question_id: str,
    request: ClinicianQuestionResponse,
    actor_role: str = "",
    actor_id: str = "",
):
    if actor_role != "clinician" or not actor_id:
        raise HTTPException(403, "Clinician access is required.")
    response = request.response.strip()
    if not response or len(response) > 4_000:
        raise HTTPException(400, "Response text must be between 1 and 4,000 characters.")
    if request.status not in QUESTION_STATUSES - {"open"}:
        raise HTTPException(400, "A clinician response must update the question status.")
    conn = db()
    row = conn.execute(
        "SELECT * FROM care_questions WHERE id=?", (question_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Question not found.")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE care_questions SET clinician_response=?,responded_by=?,status=?,updated_at=? WHERE id=?",
        (response, actor_id, request.status, now, question_id),
    )
    record_question_event(
        conn,
        question_id,
        "clinician_responded",
        actor_role,
        actor_id,
        {"status": request.status},
    )
    invalidate_preparation_questions(
        conn,
        question_ids={question_id},
        reason="A care-team response changed a question used by this checklist. Review the preparation plan.",
        actor_role=actor_role,
        actor_id=actor_id,
    )
    conn.commit()
    updated = conn.execute("""
      SELECT cq.*,p.name AS patient_name FROM care_questions cq
      JOIN patients p ON p.id=cq.patient_id WHERE cq.id=?
    """, (question_id,)).fetchone()
    conn.close()
    return serialize_care_question(updated)

@app.post("/api/v1/patients/{patient_id}/preparation-plans", status_code=201)
def create_preparation_plan(
    patient_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role not in {"patient", "partner"}:
        conn.close()
        raise HTTPException(403, "Patients and authorized care partners can prepare a checklist.")
    summaries = conn.execute("""
      SELECT dv.id AS version_id,dv.version,json_extract(dv.payload,'$.text') AS content,
             d.filename
      FROM document_versions dv
      JOIN extraction_jobs j ON j.id=dv.job_id
      JOIN documents d ON d.id=j.document_id
      JOIN patient_documents pd ON pd.document_id=d.id
      WHERE pd.patient_id=? AND dv.status='index_ready'
        AND dv.version=(
          SELECT MAX(latest.version) FROM document_versions latest
          WHERE latest.job_id=dv.job_id AND latest.status='index_ready'
        )
      ORDER BY dv.created_at DESC LIMIT 5
    """, (patient_id,)).fetchall()
    questions = conn.execute("""
      SELECT id AS question_id,text,status,clinician_response
      FROM care_questions
      WHERE patient_id=? AND status IN ('open','discussed','follow_up_needed')
      ORDER BY updated_at DESC LIMIT 20
    """, (patient_id,)).fetchall()
    conn.close()

    context = {
        "summaries": [dict(row) for row in summaries],
        "questions": [dict(row) for row in questions],
    }
    run_id = start_workflow_run(
        patient_id,
        "preparation_planner",
        os.getenv("OPENAI_PREPARATION_MODEL", "gpt-4o-mini"),
        len(context["summaries"]) + len(context["questions"]),
    )
    try:
        proposed = generate_preparation(lambda: context)
    except PreparationUnavailable as exc:
        finish_workflow_run(run_id, "failed", 0, "model_unavailable")
        logger.exception("Preparation workflow failed for patient %s", patient_id)
        raise HTTPException(503, str(exc)) from exc
    if not proposed["verified"] or not proposed["items"]:
        finish_workflow_run(run_id, "stopped", 0, "no_verified_items")
        raise HTTPException(422, proposed["message"])

    plan_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = db()
    conn.execute(
        """INSERT INTO preparation_plans
           (id,patient_id,status,summary,message,verified,model,created_by_role,
            created_by_id,created_at,approved_by,approved_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            plan_id, patient_id, "draft", proposed["summary"], proposed["message"],
            int(proposed["verified"]), proposed["model"], actor_role, actor_id, now,
            None, None,
        ),
    )
    for position, item in enumerate(proposed["items"]):
        task_id=str(uuid4())
        conn.execute(
            """INSERT INTO preparation_tasks
               (id,plan_id,patient_id,title,description,origin_type,
                source_version_ids,source_question_ids,blocked_reason,status,
                position,completed_by,completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id, plan_id, patient_id, item["title"], item["description"],
                item["origin_type"], json.dumps(item["source_version_ids"]),
                json.dumps(item["source_question_ids"]), item["blocked_reason"],
                "proposed", position, None, None,
            ),
        )
        action_type=item.get("action_type","none")
        specialist_status="not_applicable" if action_type=="none" else "identified"
        conn.execute("""INSERT INTO preparation_task_actions
          (task_id,action_type,documented_date,documented_time,documented_service,
           order_reference,specialist_status,arrangement_id,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?)""",(task_id,action_type,item.get("documented_date"),item.get("documented_time"),item.get("documented_service"),item.get("order_reference"),specialist_status,None,now))
    record_preparation_event(
        conn, plan_id, None, "draft_generated", actor_role, actor_id,
        {"item_count": len(proposed["items"]), "verified": proposed["verified"]},
    )
    conn.commit()
    row = conn.execute("SELECT * FROM preparation_plans WHERE id=?", (plan_id,)).fetchone()
    result = serialize_preparation_plan(conn, row)
    conn.close()
    finish_workflow_run(run_id, "completed", len(proposed["items"]))
    result["run_id"] = run_id
    return result

@app.get("/api/v1/patients/{patient_id}/preparation-plans/current")
def get_current_preparation_plan(
    patient_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    row = conn.execute("""
      SELECT * FROM preparation_plans
      WHERE patient_id=? AND status IN ('draft','approved','needs_review')
      ORDER BY created_at DESC LIMIT 1
    """, (patient_id,)).fetchone()
    if row is None:
        conn.close()
        return None
    result = serialize_preparation_plan(conn, row)
    conn.close()
    return result

@app.post("/api/v1/patients/{patient_id}/preparation-plans/{plan_id}/approve")
def approve_preparation_plan(
    patient_id: str,
    plan_id: str,
    request: PreparationApproval,
    actor_role: str = "",
    actor_id: str = "",
):
    if not request.approval:
        raise HTTPException(400, "Explicit checklist approval is required.")
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close()
        raise HTTPException(403, "The patient must approve the preparation checklist.")
    row = conn.execute(
        "SELECT * FROM preparation_plans WHERE id=? AND patient_id=?",
        (plan_id, patient_id),
    ).fetchone()
    item_count = conn.execute(
        "SELECT COUNT(*) FROM preparation_tasks WHERE plan_id=?", (plan_id,)
    ).fetchone()[0]
    if row is None:
        conn.close()
        raise HTTPException(404, "Preparation checklist not found.")
    if row["status"] != "draft" or not row["verified"] or item_count == 0:
        conn.close()
        raise HTTPException(409, "Only a verified draft with proposed items can be approved.")
    now = datetime.now(timezone.utc).isoformat()
    old_task_rows = conn.execute("""
      SELECT t.id FROM preparation_tasks t JOIN preparation_plans p ON p.id=t.plan_id
      WHERE p.patient_id=? AND p.status='approved'
    """, (patient_id,)).fetchall()
    old_task_ids = {task["id"] for task in old_task_rows}
    conn.execute(
        "UPDATE preparation_plans SET status='superseded' WHERE patient_id=? AND status='approved'",
        (patient_id,),
    )
    if old_task_ids:
        pause_affected_reminders(
            conn,
            reason="A replacement preparation checklist was approved.",
            actor_role=actor_role,
            actor_id=actor_id,
            task_ids=old_task_ids,
        )
    conn.execute(
        "UPDATE preparation_plans SET status='approved',approved_by=?,approved_at=? WHERE id=?",
        (actor_id, now, plan_id),
    )
    conn.execute(
        "UPDATE preparation_tasks SET status='open' WHERE plan_id=?",
        (plan_id,),
    )
    record_preparation_event(
        conn, plan_id, None, "approved", actor_role, actor_id,
        {"item_count": item_count},
    )
    conn.commit()
    approved = conn.execute(
        "SELECT * FROM preparation_plans WHERE id=?", (plan_id,)
    ).fetchone()
    conn.close()
    orchestration_status = "completed"
    try:
        orchestrate_preparation_actions(patient_id, plan_id, actor_id)
    except Exception:
        orchestration_status = "failed"
        logger.exception(
            "Preparation action orchestration failed for plan %s", plan_id
        )
    conn = db()
    approved = conn.execute(
        "SELECT * FROM preparation_plans WHERE id=?", (plan_id,)
    ).fetchone()
    result = serialize_preparation_plan(conn, approved)
    conn.close()
    result["action_orchestration_status"] = orchestration_status
    return result

@app.patch("/api/v1/patients/{patient_id}/preparation-tasks/{task_id}")
def update_preparation_task(
    patient_id: str,
    task_id: str,
    request: PreparationTaskUpdate,
    actor_role: str = "",
    actor_id: str = "",
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close()
        raise HTTPException(403, "The patient controls checklist completion.")
    row = conn.execute("""
      SELECT t.*,p.status AS plan_status FROM preparation_tasks t
      JOIN preparation_plans p ON p.id=t.plan_id
      WHERE t.id=? AND t.patient_id=?
    """, (task_id, patient_id)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Preparation item not found.")
    if row["plan_status"] != "approved":
        conn.close()
        raise HTTPException(409, "Approve the checklist before updating its items.")
    if request.complete and row["blocked_reason"]:
        conn.close()
        raise HTTPException(409, "Resolve the blocked item before marking it complete.")
    now = datetime.now(timezone.utc).isoformat()
    status = "completed" if request.complete else "open"
    conn.execute(
        "UPDATE preparation_tasks SET status=?,completed_by=?,completed_at=? WHERE id=?",
        (status, actor_id if request.complete else None, now if request.complete else None, task_id),
    )
    if request.complete:
        pause_affected_reminders(
            conn,
            reason="The linked preparation item was marked complete.",
            actor_role=actor_role,
            actor_id=actor_id,
            task_ids={task_id},
        )
    record_preparation_event(
        conn, row["plan_id"], task_id,
        "task_completed" if request.complete else "task_reopened",
        actor_role, actor_id, {},
    )
    conn.commit()
    plan = conn.execute(
        "SELECT * FROM preparation_plans WHERE id=?", (row["plan_id"],)
    ).fetchone()
    result = serialize_preparation_plan(conn, plan)
    conn.close()
    return result

def validate_reminder_draft(
    conn: sqlite3.Connection, patient_id: str, request: ReminderDraftRequest
):
    text = request.text.strip()
    if not text or len(text) > 240:
        raise HTTPException(400, "Reminder text must be between 1 and 240 characters.")
    if request.channel not in REMINDER_CHANNELS:
        raise HTTPException(400, "Reminder channel is invalid.")
    task = conn.execute("""
      SELECT t.*,p.status AS plan_status FROM preparation_tasks t
      JOIN preparation_plans p ON p.id=t.plan_id
      WHERE t.id=? AND t.patient_id=?
    """, (request.task_id, patient_id)).fetchone()
    if task is None:
        raise HTTPException(404, "Preparation item not found.")
    if task["plan_status"] != "approved" or task["status"] != "open":
        raise HTTPException(409, "Reminders require an open item from an approved checklist.")
    if task["blocked_reason"]:
        raise HTTPException(409, "Resolve the blocked preparation item first.")
    patient = conn.execute(
        "SELECT * FROM patients WHERE id=?", (patient_id,)
    ).fetchone()
    consent = current_reminder_consent(conn, patient_id)
    if not consent["enabled"]:
        raise HTTPException(409, "Reminder permission is disabled for this patient.")
    recipient, recipient_label = reminder_recipient(patient, request.channel)
    utc_schedule = validate_reminder_schedule(
        request.local_date, request.local_time, request.timezone
    )
    return {
        "task": task,
        "text": text,
        "recipient": recipient,
        "recipient_label": recipient_label,
        "utc_schedule": utc_schedule,
        "consent_version": consent["consent_version"],
    }

@app.get("/api/v1/patients/{patient_id}/reminder-consent")
def get_reminder_consent(
    patient_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    result = current_reminder_consent(conn, patient_id)
    conn.close()
    return result

@app.patch("/api/v1/patients/{patient_id}/reminder-consent")
def update_reminder_consent(
    patient_id: str,
    request: ReminderConsentUpdate,
    actor_role: str = "",
    actor_id: str = "",
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close()
        raise HTTPException(403, "Only the patient controls reminder permission.")
    current = current_reminder_consent(conn, patient_id)
    if current["enabled"] == request.enabled:
        conn.close()
        return current
    version = current["version"] + 1
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO reminder_consents
           (patient_id,enabled,version,updated_by,updated_at) VALUES (?,?,?,?,?)
           ON CONFLICT(patient_id) DO UPDATE SET enabled=excluded.enabled,
             version=excluded.version,updated_by=excluded.updated_by,
             updated_at=excluded.updated_at""",
        (patient_id, int(request.enabled), version, actor_id, now),
    )
    if not request.enabled:
        pause_affected_reminders(
            conn,
            reason="The patient disabled reminder permission.",
            actor_role=actor_role,
            actor_id=actor_id,
            patient_ids={patient_id},
        )
    conn.commit()
    result = current_reminder_consent(conn, patient_id)
    conn.close()
    return result

@app.get("/api/v1/patients/{patient_id}/reminders/current")
def get_current_reminder(
    patient_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    row = conn.execute(
        "SELECT id FROM reminders WHERE patient_id=? ORDER BY created_at DESC LIMIT 1",
        (patient_id,),
    ).fetchone()
    result = serialize_reminder(conn, row["id"]) if row else None
    conn.close()
    return result

@app.post("/api/v1/patients/{patient_id}/reminders", status_code=201)
def create_reminder(
    patient_id: str,
    request: ReminderDraftRequest,
    actor_role: str = "",
    actor_id: str = "",
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role not in {"patient", "partner"}:
        conn.close()
        raise HTTPException(403, "Patients and authorized care partners can draft reminders.")
    existing = conn.execute(
        "SELECT id FROM reminders WHERE patient_id=? AND task_id=? AND status!='cancelled'",
        (patient_id, request.task_id),
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(409, "This preparation item already has an active reminder.")
    validated = validate_reminder_draft(conn, patient_id, request)
    reminder_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    task = validated["task"]
    conn.execute(
        """INSERT INTO reminders
           (id,patient_id,task_id,current_version,status,idempotency_key,
            provider_receipt,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (reminder_id, patient_id, request.task_id, 1, "awaiting_approval", None, None, now, now),
    )
    conn.execute(
        """INSERT INTO reminder_versions
           (reminder_id,version,text,channel,recipient,recipient_label,local_date,
            local_time,timezone,utc_schedule,source_version_ids,source_question_ids,
            approval_hash,approved_by,approved_at,consent_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            reminder_id, 1, validated["text"], request.channel,
            validated["recipient"], validated["recipient_label"], request.local_date,
            request.local_time, request.timezone, validated["utc_schedule"],
            task["source_version_ids"], task["source_question_ids"], None, None, None,
            validated["consent_version"],
        ),
    )
    record_reminder_event(
        conn, reminder_id, 1, "draft_created", actor_role, actor_id,
        {"task_id": request.task_id, "channel": request.channel},
    )
    conn.commit()
    result = serialize_reminder(conn, reminder_id)
    conn.close()
    return result

@app.patch("/api/v1/patients/{patient_id}/reminders/{reminder_id}")
def revise_reminder(
    patient_id: str,
    reminder_id: str,
    request: ReminderDraftRequest,
    actor_role: str = "",
    actor_id: str = "",
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role not in {"patient", "partner"}:
        conn.close()
        raise HTTPException(403, "Patients and authorized care partners can revise reminders.")
    current = conn.execute(
        "SELECT * FROM reminders WHERE id=? AND patient_id=?", (reminder_id, patient_id)
    ).fetchone()
    if current is None:
        conn.close()
        raise HTTPException(404, "Reminder not found.")
    if current["status"] in {"cancelled", "delivered"}:
        conn.close()
        raise HTTPException(409, "A cancelled or delivered reminder cannot be revised.")
    if request.expected_version != current["current_version"]:
        conn.close()
        raise HTTPException(409, "The reminder changed. Reload it before saving.")
    validated = validate_reminder_draft(conn, patient_id, request)
    now = datetime.now(timezone.utc).isoformat()
    if current["idempotency_key"]:
        mock_reminder_scheduler.cancel(
            conn, idempotency_key=current["idempotency_key"], now=now
        )
    version = current["current_version"] + 1
    task = validated["task"]
    status = (
        "awaiting_reapproval"
        if current["status"] in {"scheduled", "paused", "awaiting_reapproval"}
        else "awaiting_approval"
    )
    conn.execute(
        """INSERT INTO reminder_versions
           (reminder_id,version,text,channel,recipient,recipient_label,local_date,
            local_time,timezone,utc_schedule,source_version_ids,source_question_ids,
            approval_hash,approved_by,approved_at,consent_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            reminder_id, version, validated["text"], request.channel,
            validated["recipient"], validated["recipient_label"], request.local_date,
            request.local_time, request.timezone, validated["utc_schedule"],
            task["source_version_ids"], task["source_question_ids"], None, None, None,
            validated["consent_version"],
        ),
    )
    conn.execute(
        """UPDATE reminders SET task_id=?,current_version=?,status=?,idempotency_key=NULL,
           provider_receipt=NULL,updated_at=? WHERE id=?""",
        (request.task_id, version, status, now, reminder_id),
    )
    record_reminder_event(
        conn, reminder_id, version, "revised", actor_role, actor_id,
        {"previous_version": current["current_version"], "approval_invalidated": True},
    )
    conn.commit()
    result = serialize_reminder(conn, reminder_id)
    conn.close()
    return result

@app.post("/api/v1/patients/{patient_id}/reminders/{reminder_id}/approve")
def approve_reminder(
    patient_id: str,
    reminder_id: str,
    request: ReminderApproval,
    actor_role: str = "",
    actor_id: str = "",
):
    if not request.approval:
        raise HTTPException(400, "Explicit reminder approval is required.")
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close()
        raise HTTPException(403, "The patient must approve this reminder.")
    row = conn.execute("""
      SELECT r.id AS reminder_id,r.patient_id,r.task_id,r.current_version,r.status,
             rv.* FROM reminders r
      JOIN reminder_versions rv ON rv.reminder_id=r.id AND rv.version=r.current_version
      WHERE r.id=? AND r.patient_id=?
    """, (reminder_id, patient_id)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Reminder not found.")
    if request.expected_version != row["current_version"]:
        conn.close()
        raise HTTPException(409, "The reminder changed. Review the current version.")
    if row["status"] == "scheduled":
        result = serialize_reminder(conn, reminder_id)
        conn.close()
        return result
    if row["status"] not in {"awaiting_approval", "awaiting_reapproval"}:
        conn.close()
        raise HTTPException(409, "This reminder is not awaiting approval.")
    consent = current_reminder_consent(conn, patient_id)
    if not consent["enabled"] or consent["consent_version"] != row["consent_version"]:
        conn.close()
        raise HTTPException(
            409, "Reminder permission changed. Save a new reminder version before approval."
        )
    task = conn.execute("""
      SELECT t.status,t.blocked_reason,p.status AS plan_status
      FROM preparation_tasks t JOIN preparation_plans p ON p.id=t.plan_id
      WHERE t.id=? AND t.patient_id=?
    """, (row["task_id"], patient_id)).fetchone()
    if (
        task is None or task["status"] != "open" or task["blocked_reason"]
        or task["plan_status"] != "approved"
    ):
        conn.close()
        raise HTTPException(409, "The source preparation item is no longer eligible.")
    payload = reminder_payload(row)
    approval_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    idempotency_key = f"reminder:{reminder_id}:v{row['current_version']}"
    now = datetime.now(timezone.utc).isoformat()
    try:
        receipt = mock_reminder_scheduler.schedule(
            conn,
            idempotency_key=idempotency_key,
            reminder_id=reminder_id,
            payload_hash=approval_hash,
            now=now,
        )
    except MockSchedulerConflict as exc:
        conn.rollback()
        conn.close()
        raise HTTPException(409, str(exc)) from exc
    conn.execute(
        """UPDATE reminder_versions SET approval_hash=?,approved_by=?,approved_at=?
           WHERE reminder_id=? AND version=?""",
        (approval_hash, actor_id, now, reminder_id, row["current_version"]),
    )
    conn.execute(
        """UPDATE reminders SET status='scheduled',idempotency_key=?,provider_receipt=?,
           updated_at=? WHERE id=?""",
        (idempotency_key, receipt.receipt_id, now, reminder_id),
    )
    record_reminder_event(
        conn, reminder_id, row["current_version"], "approved_and_scheduled",
        actor_role, actor_id,
        {"approval_hash": approval_hash, "receipt_id": receipt.receipt_id, "simulation": True},
    )
    conn.commit()
    result = serialize_reminder(conn, reminder_id)
    conn.close()
    return result

def reminder_is_currently_eligible(conn: sqlite3.Connection, row: sqlite3.Row):
    consent = current_reminder_consent(conn, row["patient_id"])
    if not consent["enabled"] or consent["consent_version"] != row["consent_version"]:
        return False, "Reminder permission changed."
    task = conn.execute("""
      SELECT t.status,t.blocked_reason,p.status AS plan_status
      FROM preparation_tasks t JOIN preparation_plans p ON p.id=t.plan_id
      WHERE t.id=? AND t.patient_id=?
    """, (row["task_id"], row["patient_id"])).fetchone()
    if (
        task is None or task["status"] != "open" or task["blocked_reason"]
        or task["plan_status"] != "approved"
    ):
        return False, "The source preparation item is no longer eligible."
    return True, ""

@app.post("/api/v1/patients/{patient_id}/reminders/{reminder_id}/dispatch")
def simulate_reminder_delivery(
    patient_id: str,
    reminder_id: str,
    request: DeliverySimulationRequest,
    actor_role: str = "",
    actor_id: str = "",
):
    allowed_outcomes = {
        "delivered", "failed", "timeout_before_commit", "timeout_after_commit"
    }
    if request.outcome not in allowed_outcomes:
        raise HTTPException(400, "The simulated delivery outcome is invalid.")
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close()
        raise HTTPException(403, "The patient can run this delivery simulation.")
    row = conn.execute("""
      SELECT r.id AS reminder_id,r.patient_id,r.task_id,r.current_version,r.status,
             r.idempotency_key,rv.consent_version
      FROM reminders r JOIN reminder_versions rv
        ON rv.reminder_id=r.id AND rv.version=r.current_version
      WHERE r.id=? AND r.patient_id=?
    """, (reminder_id, patient_id)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Reminder not found.")
    if request.expected_version != row["current_version"]:
        conn.close()
        raise HTTPException(409, "The reminder changed. Reload it before delivery.")
    if row["status"] in {"delivered", "failed"}:
        result = serialize_reminder(conn, reminder_id)
        conn.close()
        return result
    if row["status"] == "outcome_unknown":
        conn.close()
        raise HTTPException(409, "Reconcile the uncertain outcome before retrying.")
    if row["status"] != "scheduled" or not row["idempotency_key"]:
        conn.close()
        raise HTTPException(409, "Only a scheduled reminder can be delivered.")
    eligible, reason = reminder_is_currently_eligible(conn, row)
    if not eligible:
        pause_affected_reminders(
            conn,
            reason=reason,
            actor_role="system",
            actor_id="delivery-worker",
            task_ids={row["task_id"]},
        )
        conn.commit()
        conn.close()
        raise HTTPException(409, reason)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE reminders SET status='attempted',updated_at=? WHERE id=?",
        (now, reminder_id),
    )
    record_reminder_event(
        conn, reminder_id, row["current_version"], "delivery_attempted",
        actor_role, actor_id, {"simulation": True},
    )
    try:
        receipt = mock_reminder_scheduler.dispatch(
            conn,
            idempotency_key=row["idempotency_key"],
            outcome=request.outcome,
            now=now,
        )
    except MockSchedulerTimeout:
        conn.execute(
            "UPDATE reminders SET status='outcome_unknown',updated_at=? WHERE id=?",
            (now, reminder_id),
        )
        record_reminder_event(
            conn, reminder_id, row["current_version"], "delivery_outcome_unknown",
            actor_role, actor_id,
            {"reason": "The mock provider timed out. Reconcile before retrying.", "simulation": True},
        )
        conn.commit()
        result = serialize_reminder(conn, reminder_id)
        conn.close()
        return result
    except MockSchedulerConflict as exc:
        conn.rollback()
        conn.close()
        raise HTTPException(409, str(exc)) from exc
    conn.execute(
        "UPDATE reminders SET status=?,updated_at=? WHERE id=?",
        (receipt.status, now, reminder_id),
    )
    record_reminder_event(
        conn, reminder_id, row["current_version"], f'delivery_{receipt.status}',
        actor_role, actor_id,
        {"receipt_id": receipt.receipt_id, "simulation": True},
    )
    conn.commit()
    result = serialize_reminder(conn, reminder_id)
    conn.close()
    return result

@app.post("/api/v1/patients/{patient_id}/reminders/{reminder_id}/reconcile")
def reconcile_reminder_delivery(
    patient_id: str, reminder_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    row = conn.execute(
        "SELECT * FROM reminders WHERE id=? AND patient_id=?",
        (reminder_id, patient_id),
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Reminder not found.")
    if row["status"] != "outcome_unknown" or not row["idempotency_key"]:
        result = serialize_reminder(conn, reminder_id)
        conn.close()
        return result
    receipt = mock_reminder_scheduler.get_status(
        conn, idempotency_key=row["idempotency_key"]
    )
    if receipt is None:
        conn.close()
        raise HTTPException(409, "The mock provider has no matching operation.")
    reconciled_status = {
        "delivered": "delivered",
        "failed": "failed",
        "scheduled": "scheduled",
        "cancelled": "paused",
    }.get(receipt.status, "outcome_unknown")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE reminders SET status=?,updated_at=? WHERE id=?",
        (reconciled_status, now, reminder_id),
    )
    record_reminder_event(
        conn, reminder_id, row["current_version"], "delivery_reconciled",
        actor_role, actor_id,
        {"provider_status": receipt.status, "result": reconciled_status, "simulation": True},
    )
    conn.commit()
    result = serialize_reminder(conn, reminder_id)
    conn.close()
    return result

@app.get("/api/v1/patients/{patient_id}/reminders/{reminder_id}/events")
def list_reminder_events(
    patient_id: str, reminder_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    exists = conn.execute(
        "SELECT 1 FROM reminders WHERE id=? AND patient_id=?", (reminder_id, patient_id)
    ).fetchone()
    if exists is None:
        conn.close()
        raise HTTPException(404, "Reminder not found.")
    rows = conn.execute(
        """SELECT id,version,action,actor_role,actor_id,payload,created_at
           FROM reminder_events WHERE reminder_id=? ORDER BY created_at DESC,rowid DESC""",
        (reminder_id,),
    ).fetchall()
    conn.close()
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

@app.get("/api/v1/patients/{patient_id}/activity")
def list_patient_activity(
    patient_id: str, actor_role: str = "", actor_id: str = ""
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    activity = []
    summaries = conn.execute("""
      SELECT dv.id,dv.version,dv.status,dv.created_at,d.id AS document_id,d.filename
      FROM document_versions dv JOIN extraction_jobs j ON j.id=dv.job_id
      JOIN documents d ON d.id=j.document_id
      JOIN patient_documents pd ON pd.document_id=d.id WHERE pd.patient_id=?
    """, (patient_id,)).fetchall()
    for row in summaries:
        activity.append({
            "id": f'summary:{row["id"]}', "category": "summary",
            "title": "Visit summary version published",
            "detail": f'{row["filename"]} · Version {row["version"]}',
            "status": row["status"], "actor_role": "clinician",
            "created_at": row["created_at"], "document_id": row["document_id"],
            "version_id": row["id"],
        })
    question_events = conn.execute("""
      SELECT e.* FROM care_question_events e JOIN care_questions q ON q.id=e.question_id
      WHERE q.patient_id=?
    """, (patient_id,)).fetchall()
    question_titles = {
        "created": "Visit question saved",
        "updated": "Visit question updated",
        "clinician_responded": "Care team responded to a question",
    }
    for row in question_events:
        payload = json.loads(row["payload"])
        activity.append({
            "id": f'question:{row["id"]}', "category": "question",
            "title": question_titles.get(row["action"], "Question activity"),
            "detail": payload.get("status", row["action"]).replace("_", " "),
            "status": payload.get("status"), "actor_role": row["actor_role"],
            "created_at": row["created_at"], "question_id": row["question_id"],
        })
    preparation_events = conn.execute("""
      SELECT e.* FROM preparation_events e JOIN preparation_plans p ON p.id=e.plan_id
      WHERE p.patient_id=?
    """, (patient_id,)).fetchall()
    preparation_titles = {
        "draft_generated": "Preparation checklist drafted",
        "approved": "Preparation checklist approved",
        "task_completed": "Preparation item completed",
        "task_reopened": "Preparation item reopened",
        "sources_invalidated": "Checklist source changed",
        "question_sources_invalidated": "Checklist question changed",
    }
    for row in preparation_events:
        payload = json.loads(row["payload"])
        activity.append({
            "id": f'preparation:{row["id"]}', "category": "preparation",
            "title": preparation_titles.get(row["action"], "Preparation activity"),
            "detail": payload.get("reason", row["action"].replace("_", " ")),
            "status": row["action"], "actor_role": row["actor_role"],
            "created_at": row["created_at"], "plan_id": row["plan_id"],
        })
    reminder_events = conn.execute("""
      SELECT e.* FROM reminder_events e JOIN reminders r ON r.id=e.reminder_id
      WHERE r.patient_id=?
    """, (patient_id,)).fetchall()
    reminder_titles = {
        "draft_created": "Reminder draft saved",
        "revised": "Reminder version revised",
        "approved_and_scheduled": "Reminder approved and scheduled",
        "delivery_attempted": "Mock delivery attempted",
        "delivery_delivered": "Mock reminder delivered",
        "delivery_failed": "Mock reminder delivery failed",
        "delivery_outcome_unknown": "Mock delivery outcome uncertain",
        "delivery_reconciled": "Mock delivery reconciled",
        "paused": "Reminder paused",
        "cancelled": "Reminder cancelled",
        "paused_by_dependency_change": "Reminder paused after a dependency changed",
        "provider_callback_applied": "Mock-provider callback applied",
        "provider_callback_ignored": "Late mock-provider callback recorded",
    }
    for row in reminder_events:
        payload = json.loads(row["payload"])
        detail = payload.get("reason") or payload.get("result") or row["action"].replace("_", " ")
        activity.append({
            "id": f'reminder:{row["id"]}', "category": "reminder",
            "title": reminder_titles.get(row["action"], "Reminder activity"),
            "detail": detail, "status": row["action"],
            "actor_role": row["actor_role"], "created_at": row["created_at"],
            "reminder_id": row["reminder_id"], "version": row["version"],
        })
    arrangement_events = conn.execute("""SELECT e.*,a.action_type FROM arrangement_events e
      JOIN arrangements a ON a.id=e.arrangement_id WHERE a.patient_id=?""", (patient_id,)).fetchall()
    for row in arrangement_events:
        activity.append({
            "id": f'arrangement:{row["id"]}', "category": "arrangement",
            "title": f'{row["action_type"].title()} arrangement {row["action"].replace("mock_", "").replace("_", " ")}',
            "detail": "Simulated provider operation; no external booking or purchase occurred.",
            "status": row["action"], "actor_role": row["actor_role"],
            "created_at": row["created_at"], "arrangement_id": row["arrangement_id"],
        })
    workflow_runs = conn.execute(
        "SELECT * FROM workflow_runs WHERE patient_id=?", (patient_id,)
    ).fetchall()
    for row in workflow_runs:
        activity.append({
            "id": f'workflow:{row["id"]}', "category": "workflow",
            "title": row["workflow"].replace("_", " ").title(),
            "detail": (
                f'{row["status"]} · {row["input_count"]} authorized inputs · '
                f'{row["result_count"] or 0} results'
            ),
            "status": row["status"], "actor_role": "system",
            "created_at": row["created_at"], "run_id": row["id"],
            "stop_reason": row["stop_reason"], "model": row["model"],
        })
    conn.close()
    activity.sort(key=lambda item: item["created_at"], reverse=True)
    return activity[:100]

@app.post("/api/v1/providers/mock/reminders/callback")
def receive_mock_reminder_callback(
    request: MockDeliveryCallback,
    x_mock_signature: Annotated[str | None, Header(alias="X-Mock-Signature")] = None,
):
    if request.status not in {"delivered", "failed"}:
        raise HTTPException(400, "Callback status is invalid.")
    secret = os.getenv("MOCK_PROVIDER_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Mock provider callback secret is not configured.")
    signed = f"{request.event_id}.{request.receipt_id}.{request.status}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not x_mock_signature or not hmac.compare_digest(x_mock_signature, expected):
        raise HTTPException(401, "Callback signature is invalid.")
    conn = db()
    duplicate = conn.execute(
        "SELECT 1 FROM mock_callback_events WHERE event_id=?", (request.event_id,)
    ).fetchone()
    if duplicate:
        conn.close()
        return {"accepted": True, "duplicate": True}
    now = datetime.now(timezone.utc).isoformat()
    operation = mock_reminder_scheduler.record_callback(
        conn, receipt_id=request.receipt_id, status=request.status, now=now
    )
    if operation is None:
        conn.close()
        raise HTTPException(404, "Mock provider operation not found.")
    conn.execute(
        "INSERT INTO mock_callback_events VALUES (?,?,?,?)",
        (request.event_id, request.receipt_id, request.status, now),
    )
    reminder = conn.execute(
        "SELECT * FROM reminders WHERE id=?", (operation["reminder_id"],)
    ).fetchone()
    action = "provider_callback_ignored"
    if (
        reminder
        and reminder["idempotency_key"] == operation["idempotency_key"]
        and reminder["status"] not in {"paused", "cancelled"}
    ):
        conn.execute(
            "UPDATE reminders SET status=?,updated_at=? WHERE id=?",
            (request.status, now, reminder["id"]),
        )
        action = "provider_callback_applied"
    if reminder:
        record_reminder_event(
            conn, reminder["id"], reminder["current_version"], action,
            "provider", "carebridge-local-mock",
            {"event_id": request.event_id, "provider_status": request.status},
        )
    conn.commit()
    conn.close()
    return {"accepted": True, "duplicate": False, "applied": action.endswith("applied")}

def stop_reminder(
    patient_id: str,
    reminder_id: str,
    target_status: str,
    actor_role: str,
    actor_id: str,
):
    conn = db()
    authorize_patient(conn, patient_id, actor_role, actor_id)
    if actor_role != "patient" or actor_id != patient_id:
        conn.close()
        raise HTTPException(403, "The patient controls reminder delivery.")
    row = conn.execute(
        "SELECT * FROM reminders WHERE id=? AND patient_id=?", (reminder_id, patient_id)
    ).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, "Reminder not found.")
    if row["status"] == "cancelled":
        result = serialize_reminder(conn, reminder_id)
        conn.close()
        return result
    if row["status"] == "delivered":
        conn.close()
        raise HTTPException(409, "A delivered reminder cannot be recalled.")
    now = datetime.now(timezone.utc).isoformat()
    if row["idempotency_key"]:
        mock_reminder_scheduler.cancel(
            conn, idempotency_key=row["idempotency_key"], now=now
        )
    conn.execute(
        "UPDATE reminders SET status=?,updated_at=? WHERE id=?",
        (target_status, now, reminder_id),
    )
    record_reminder_event(
        conn, reminder_id, row["current_version"], target_status,
        actor_role, actor_id, {"simulation": True},
    )
    conn.commit()
    result = serialize_reminder(conn, reminder_id)
    conn.close()
    return result

@app.post("/api/v1/patients/{patient_id}/reminders/{reminder_id}/pause")
def pause_reminder(
    patient_id: str, reminder_id: str, actor_role: str = "", actor_id: str = ""
):
    return stop_reminder(patient_id, reminder_id, "paused", actor_role, actor_id)

@app.post("/api/v1/patients/{patient_id}/reminders/{reminder_id}/cancel")
def cancel_reminder(
    patient_id: str, reminder_id: str, actor_role: str = "", actor_id: str = ""
):
    return stop_reminder(patient_id, reminder_id, "cancelled", actor_role, actor_id)


def require_clinician(actor_role: str, actor_id: str):
    if actor_role != "clinician" or not actor_id:
        raise HTTPException(403, "Clinician access is required.")

ARRANGEMENT_FIELDS = {
    "appointment": {"clinic", "date", "time", "timezone", "appointment_type"},
    "travel": {"provider", "pickup", "destination", "date", "time", "passengers", "cost"},
    "lab": {"order_id", "facility", "date", "time", "timezone"},
    "imaging": {"order_id", "facility", "date", "time", "timezone", "service"},
}

def serialize_arrangement(conn: sqlite3.Connection, row: sqlite3.Row):
    version = conn.execute("SELECT * FROM arrangement_versions WHERE arrangement_id=? AND version=?", (row["id"],row["current_version"])).fetchone()
    item=dict(row); item["payload"]=json.loads(version["payload"]); item["source_version_ids"]=json.loads(version["source_version_ids"])
    item["source_labels"] = []
    for version_id in item["source_version_ids"]:
        source = conn.execute("""SELECT d.filename,dv.version FROM document_versions dv
          JOIN extraction_jobs j ON j.id=dv.job_id JOIN documents d ON d.id=j.document_id
          WHERE dv.id=?""", (version_id,)).fetchone()
        if source:
            item["source_labels"].append(
                f'{source["filename"]} · Version {source["version"]}'
            )
    item["approved_by"]=version["approved_by"]; item["approved_at"]=version["approved_at"]; item["simulation"]=True
    return item

def arrangement_approver(conn, patient_id, actor_role, actor_id):
    if actor_role == "patient" and actor_id == patient_id: return
    if actor_role == "partner" and conn.execute("""SELECT 1 FROM care_partner_grants g JOIN care_partner_permissions p ON p.grant_id=g.id
        WHERE g.patient_id=? AND lower(g.partner_email)=lower(?) AND g.status='active' AND p.can_approve_actions=1""",(patient_id,actor_id)).fetchone(): return
    raise HTTPException(403,"Patient approval or explicit care-partner delegation is required.")

@app.get("/api/v1/mock-integrations/options")
def mock_integration_options(action_type: str, actor_role: str = "", actor_id: str = ""):
    if actor_role not in {"patient","partner"} or not actor_id: raise HTTPException(403,"Signed-in patient access is required.")
    options={
        "appointment":[{"clinic":"Fieldstone Clinic","date":"2026-10-08","time":"10:00","timezone":"America/New_York","appointment_type":"Follow-up","fee":"No fee shown"}],
        "travel":[{"provider":"CareRide","pickup":"Enter pickup location","destination":"Fieldstone Clinic","date":"2026-10-08","time":"09:00","passengers":1,"cost":"$24.00 estimated fare"}],
        "lab":[{"order_id":"LAB-1001","facility":"Fieldstone Lab","date":"2026-10-06","time":"08:30","timezone":"America/New_York"}],
        "imaging":[{"order_id":"IMG-1001","facility":"Fieldstone Imaging","date":"2026-10-01","time":"11:00","timezone":"America/New_York","service":"MRI"}],
    }
    if action_type not in options: raise HTTPException(400,"Unsupported arrangement type.")
    return {"action_type":action_type,"simulation":True,"options":options[action_type]}

@app.get("/api/v1/patients/{patient_id}/arrangements")
def list_arrangements(patient_id: str, actor_role: str = "", actor_id: str = ""):
    conn=db(); authorize_patient(conn,patient_id,actor_role,actor_id)
    rows=conn.execute("SELECT * FROM arrangements WHERE patient_id=? ORDER BY created_at DESC",(patient_id,)).fetchall()
    result=[serialize_arrangement(conn,row) for row in rows]; conn.close(); return result

@app.post("/api/v1/patients/{patient_id}/arrangements",status_code=201)
def create_arrangement(patient_id: str, request: ArrangementDraft, actor_role: str = "", actor_id: str = ""):
    conn=db(); authorize_patient(conn,patient_id,actor_role,actor_id)
    if actor_role not in {"patient","partner"}: conn.close(); raise HTTPException(403,"Only a patient or authorized care partner can request options.")
    required=ARRANGEMENT_FIELDS.get(request.action_type)
    if not required: conn.close(); raise HTTPException(400,"Unsupported arrangement type.")
    missing=sorted(field for field in required if request.payload.get(field) in (None,""))
    proposed_date = str(request.payload.get("date", ""))
    if proposed_date:
        try:
            date.fromisoformat(proposed_date)
        except ValueError:
            missing.append("full_date_with_year")
    proposed_time = str(request.payload.get("time", ""))
    if proposed_time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", proposed_time):
        missing.append("valid_24_hour_time")
    proposed_timezone = request.payload.get("timezone")
    if proposed_timezone:
        try:
            ZoneInfo(str(proposed_timezone))
        except ZoneInfoNotFoundError:
            missing.append("valid_timezone")
    status="awaiting_information" if missing else "awaiting_approval"
    prefixes={"lab":"LAB-","imaging":"IMG-"}
    if request.action_type in prefixes and not str(request.payload.get("order_id","")).startswith(prefixes[request.action_type]): status="awaiting_information"; missing.append("valid_order_id")
    arrangement_id=str(uuid4()); now=datetime.now(timezone.utc).isoformat()
    payload={**request.payload,"missing_inputs":sorted(set(missing)),"simulation":True}
    conn.execute("INSERT INTO arrangements VALUES (?,?,?,?,?,?,?,?,?)",(arrangement_id,patient_id,request.action_type,1,status,None,None,now,now))
    conn.execute("INSERT INTO arrangement_versions VALUES (?,?,?,?,?,?,?)",(arrangement_id,1,json.dumps(payload),json.dumps(request.source_version_ids),None,None,None))
    conn.execute("INSERT INTO arrangement_events VALUES (?,?,?,?,?,?,?,?)",(str(uuid4()),arrangement_id,1,"draft_created",actor_role,actor_id,json.dumps({"status":status}),now))
    conn.commit(); row=conn.execute("SELECT * FROM arrangements WHERE id=?",(arrangement_id,)).fetchone(); result=serialize_arrangement(conn,row); conn.close(); return result

@app.post("/api/v1/patients/{patient_id}/arrangements/{arrangement_id}/approve")
def approve_arrangement(patient_id: str, arrangement_id: str, request: ArrangementApproval, actor_role: str = "", actor_id: str = ""):
    conn=db(); authorize_patient(conn,patient_id,actor_role,actor_id); arrangement_approver(conn,patient_id,actor_role,actor_id)
    row=conn.execute("SELECT * FROM arrangements WHERE id=? AND patient_id=?",(arrangement_id,patient_id)).fetchone()
    if not row: conn.close(); raise HTTPException(404,"Arrangement was not found.")
    if row["status"] == "confirmed" and row["current_version"] == request.expected_version:
        result=serialize_arrangement(conn,row); conn.close(); return result
    if not request.approval or row["status"]!="awaiting_approval" or row["current_version"]!=request.expected_version: conn.close(); raise HTTPException(409,"This exact arrangement is not available for approval.")
    version=conn.execute("SELECT * FROM arrangement_versions WHERE arrangement_id=? AND version=?",(arrangement_id,row["current_version"])).fetchone()
    approval_hash=hashlib.sha256((version["payload"]+version["source_version_ids"]).encode()).hexdigest(); key=f"arrangement:{arrangement_id}:{row['current_version']}:{approval_hash}"
    receipt=f"CB-{row['action_type'].upper()}-{hashlib.sha256(key.encode()).hexdigest()[:10].upper()}"; now=datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE arrangement_versions SET approval_hash=?,approved_by=?,approved_at=? WHERE arrangement_id=? AND version=?",(approval_hash,actor_id,now,arrangement_id,row["current_version"]))
    conn.execute("UPDATE arrangements SET status='confirmed',idempotency_key=?,provider_receipt=?,updated_at=? WHERE id=?",(key,receipt,now,arrangement_id))
    conn.execute("UPDATE preparation_task_actions SET specialist_status=?,updated_at=? WHERE arrangement_id=?",("confirmed",now,arrangement_id))
    conn.execute("INSERT INTO arrangement_events VALUES (?,?,?,?,?,?,?,?)",(str(uuid4()),arrangement_id,row["current_version"],"mock_confirmed",actor_role,actor_id,json.dumps({"receipt":receipt}),now))
    conn.commit(); row=conn.execute("SELECT * FROM arrangements WHERE id=?",(arrangement_id,)).fetchone(); result=serialize_arrangement(conn,row); conn.close(); return result

@app.post("/api/v1/patients/{patient_id}/arrangements/{arrangement_id}/cancel")
def cancel_arrangement(patient_id: str, arrangement_id: str, actor_role: str = "", actor_id: str = ""):
    conn=db(); authorize_patient(conn,patient_id,actor_role,actor_id); arrangement_approver(conn,patient_id,actor_role,actor_id)
    row=conn.execute("SELECT * FROM arrangements WHERE id=? AND patient_id=?",(arrangement_id,patient_id)).fetchone()
    if not row: conn.close(); raise HTTPException(404,"Arrangement was not found.")
    now=datetime.now(timezone.utc).isoformat(); conn.execute("UPDATE arrangements SET status='cancelled',updated_at=? WHERE id=?",(now,arrangement_id)); conn.execute("UPDATE preparation_task_actions SET specialist_status=?,updated_at=? WHERE arrangement_id=?",("cancelled",now,arrangement_id)); conn.execute("INSERT INTO arrangement_events VALUES (?,?,?,?,?,?,?,?)",(str(uuid4()),arrangement_id,row["current_version"],"mock_cancelled",actor_role,actor_id,"{}",now)); conn.commit(); row=conn.execute("SELECT * FROM arrangements WHERE id=?",(arrangement_id,)).fetchone(); result=serialize_arrangement(conn,row); conn.close(); return result

def orchestrate_preparation_actions(patient_id: str, plan_id: str, actor_id: str):
    conn=db(); rows=conn.execute("""SELECT a.*,t.source_version_ids FROM preparation_task_actions a
      JOIN preparation_tasks t ON t.id=a.task_id WHERE t.plan_id=? AND a.action_type!='none' AND a.arrangement_id IS NULL""",(plan_id,)).fetchall(); conn.close()
    requests = [
        {
            "task_id": row["task_id"],
            "action_type": row["action_type"],
            "documented_date": row["documented_date"],
            "documented_time": row["documented_time"],
            "documented_service": row["documented_service"],
            "order_reference": row["order_reference"],
            "source_version_ids": json.loads(row["source_version_ids"]),
        }
        for row in rows
    ]
    if not requests:
        return []
    run_id = start_workflow_run(
        patient_id, "preparation_action_orchestrator", "deterministic-specialists", len(requests)
    )
    created=[]
    try:
        proposals = propose_preparation_actions(requests)
        for proposal in proposals:
            arrangement=create_arrangement(patient_id,ArrangementDraft(action_type=proposal["action_type"],payload=proposal["payload"],source_version_ids=proposal["source_version_ids"]),"patient",patient_id)
            update=db(); update.execute("UPDATE preparation_task_actions SET specialist_status=?,arrangement_id=?,updated_at=? WHERE task_id=?",(arrangement["status"],arrangement["id"],datetime.now(timezone.utc).isoformat(),proposal["task_id"])); update.commit(); update.close(); created.append(arrangement)
    except Exception:
        finish_workflow_run(run_id, "failed", len(created), "specialist_workflow_failed")
        raise
    finish_workflow_run(run_id, "completed", len(created))
    return created

@app.post("/api/v1/patients/{patient_id}/preparation-plans/{plan_id}/orchestrate")
def orchestrate_plan(patient_id: str, plan_id: str, actor_role: str = "", actor_id: str = ""):
    conn=db(); authorize_patient(conn,patient_id,actor_role,actor_id); plan=conn.execute("SELECT 1 FROM preparation_plans WHERE id=? AND patient_id=? AND status='approved'",(plan_id,patient_id)).fetchone(); conn.close()
    if not plan: raise HTTPException(409,"Approve the preparation plan before arranging its actions.")
    return {"arrangements":orchestrate_preparation_actions(patient_id,plan_id,actor_id),"simulation":True}

@app.get("/api/v1/patients/{patient_id}/preparation-calendar.ics")
def preparation_calendar(patient_id: str, actor_role: str = "", actor_id: str = ""):
    conn=db(); authorize_patient(conn,patient_id,actor_role,actor_id)
    rows=conn.execute("""SELECT a.id,a.action_type,av.payload FROM arrangements a JOIN arrangement_versions av
      ON av.arrangement_id=a.id AND av.version=a.current_version WHERE a.patient_id=? AND a.status='confirmed' ORDER BY a.created_at""",(patient_id,)).fetchall(); conn.close()
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//CareBridge//Preparation Schedule//EN","CALSCALE:GREGORIAN"]
    for row in rows:
        payload=json.loads(row["payload"]); local_date=str(payload.get("date","")).replace("-",""); local_time=str(payload.get("time","09:00")).replace(":","")+"00"
        if len(local_date)!=8: continue
        summary=f"CareBridge: {row['action_type'].title()} (simulated booking)".replace(",","\\,")
        location=str(payload.get("facility") or payload.get("clinic") or payload.get("destination") or "").replace(",","\\,")
        timezone_name = str(payload.get("timezone", "UTC"))
        lines += ["BEGIN:VEVENT",f"UID:{row['id']}@carebridge.local",f"DTSTART;TZID={timezone_name}:{local_date}T{local_time}",f"SUMMARY:{summary}",f"LOCATION:{location}","DESCRIPTION:Fictional CareBridge preparation activity. Verify details with the provider.","END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines)+"\r\n",media_type="text/calendar",headers={"Content-Disposition":f'attachment; filename="carebridge-{patient_id}-preparation.ics"'})


def serialize_eval_run(conn: sqlite3.Connection, row: sqlite3.Row, include_cases: bool = False):
    item = dict(row)
    item["include_ragas"] = bool(item["include_ragas"])
    item["aggregate_metrics"] = json.loads(item["aggregate_metrics"])
    if include_cases:
        case_rows = conn.execute(
            "SELECT * FROM eval_case_results WHERE run_id=? ORDER BY case_id", (row["id"],)
        ).fetchall()
        item["cases"] = []
        for case_row in case_rows:
            case_item = json.loads(case_row["result"])
            case_item.update(
                {
                    "status": case_row["status"],
                    "passed": bool(case_row["passed"]),
                    "error": case_row["error"],
                }
            )
            item["cases"].append(case_item)
    return item


@app.get("/api/v1/evaluations/dataset")
def get_evaluation_dataset(actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    cases = load_cases()
    conn = db()
    latest = conn.execute(
        "SELECT * FROM eval_runs WHERE dataset_name='grounded-answer-synthetic' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    latest_run = serialize_eval_run(conn, latest) if latest else None
    conn.close()
    return {
        "name": "grounded-answer-synthetic",
        "version": cases[0].dataset_version,
        "scope": "Synthetic grounded-answer retrieval, abstention, and citation behavior",
        "case_count": len(cases),
        "cases": [
            {
                "case_id": case.case_id,
                "title": case.title,
                "question": case.question,
                "expected_behavior": case.expected_behavior,
                "reference_context_ids": case.reference_context_ids,
                "tags": case.tags,
            }
            for case in cases
        ],
        "latest_run": latest_run,
    }


@app.get("/api/v1/evaluations/preparation-dataset")
def get_preparation_evaluation_dataset(
    actor_role: str = "", actor_id: str = ""
):
    require_clinician(actor_role, actor_id)
    cases = load_preparation_cases()
    conn = db()
    latest = conn.execute(
        "SELECT * FROM eval_runs WHERE dataset_name='preparation-action-synthetic' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    latest_run = serialize_eval_run(conn, latest) if latest else None
    conn.close()
    return {
        "name": "preparation-action-synthetic",
        "version": cases[0].dataset_version,
        "scope": "Preparation extraction, safety, prerequisites, and specialist routing",
        "case_count": len(cases),
        "cases": [
            {
                "case_id": case.case_id,
                "title": case.title,
                "expected_action_types": case.expected_action_types,
                "tags": case.tags,
            }
            for case in cases
        ],
        "latest_run": latest_run,
    }


@app.get("/api/v1/evaluations/runs")
def list_evaluation_runs(actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    conn = db()
    rows = conn.execute("SELECT * FROM eval_runs ORDER BY created_at DESC").fetchall()
    result = [serialize_eval_run(conn, row) for row in rows]
    conn.close()
    return result


@app.get("/api/v1/evaluations/runs/{run_id}")
def get_evaluation_run(run_id: str, actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    conn = db()
    row = conn.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Evaluation run was not found.")
    result = serialize_eval_run(conn, row, include_cases=True)
    conn.close()
    return result


@app.post("/api/v1/evaluations/runs", status_code=201)
def create_evaluation_run(
    request: EvaluationRunRequest,
    actor_role: str = "",
    actor_id: str = "",
):
    require_clinician(actor_role, actor_id)
    cases = load_cases()
    run_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    model = os.getenv("OPENAI_ANSWER_MODEL", "gpt-4o-mini")
    conn = db()
    conn.execute(
        "INSERT INTO eval_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, "grounded-answer-synthetic", cases[0].dataset_version,
            "running", int(request.include_ragas), model, len(cases), 0, 0,
            "{}", None, actor_id, now, None,
        ),
    )
    conn.commit()

    completed = 0
    passed = 0
    errors: list[str] = []
    metric_values: dict[str, list[float]] = {}
    for case in cases:
        try:
            result = run_evaluation_case(case, include_ragas=request.include_ragas)
            case_passed = bool(result["scores"]["passed"])
            passed += int(case_passed)
            completed += 1
            for name, value in result["scores"].items():
                if name != "passed" and isinstance(value, (int, float)):
                    metric_values.setdefault(name, []).append(float(value))
            conn.execute(
                "INSERT INTO eval_case_results VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), run_id, case.case_id, "completed", int(case_passed),
                    json.dumps(result), None, datetime.now(timezone.utc).isoformat(),
                ),
            )
        except (EvaluationUnavailable, AnswerUnavailable) as exc:
            message = str(exc)
            errors.append(f"{case.case_id}: {message}")
            conn.execute(
                "INSERT INTO eval_case_results VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), run_id, case.case_id, "error", 0,
                    json.dumps(
                        {
                            "case_id": case.case_id,
                            "title": case.title,
                            "expected_behavior": case.expected_behavior,
                            "question": case.question,
                            "tags": case.tags,
                            "scores": {},
                        }
                    ),
                    message, datetime.now(timezone.utc).isoformat(),
                ),
            )
        conn.commit()

    aggregates = {
        name: round(sum(values) / len(values), 4)
        for name, values in metric_values.items()
        if values
    }
    status = "completed" if not errors else ("partial" if completed else "failed")
    finished = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE eval_runs SET status=?,completed_cases=?,passed_cases=?,
           aggregate_metrics=?,error=?,completed_at=? WHERE id=?""",
        (
            status, completed, passed, json.dumps(aggregates),
            " | ".join(errors) if errors else None, finished, run_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,)).fetchone()
    result = serialize_eval_run(conn, row, include_cases=True)
    conn.close()
    return result


@app.post("/api/v1/evaluations/preparation-runs", status_code=201)
def create_preparation_evaluation_run(
    actor_role: str = "", actor_id: str = ""
):
    require_clinician(actor_role, actor_id)
    cases = load_preparation_cases()
    run_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    model = os.getenv("OPENAI_PREPARATION_MODEL", "gpt-4o-mini")
    conn = db()
    conn.execute(
        "INSERT INTO eval_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, "preparation-action-synthetic", cases[0].dataset_version,
            "running", 0, model, len(cases), 0, 0, "{}", None, actor_id, now, None,
        ),
    )
    conn.commit()
    completed = 0
    passed = 0
    errors: list[str] = []
    metric_values: dict[str, list[float]] = {}
    for case in cases:
        try:
            result = run_preparation_evaluation_case(case)
            case_passed = bool(result["scores"]["passed"])
            completed += 1
            passed += int(case_passed)
            for name, value in result["scores"].items():
                if name != "passed" and isinstance(value, (int, float)):
                    metric_values.setdefault(name, []).append(float(value))
            conn.execute(
                "INSERT INTO eval_case_results VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), run_id, case.case_id, "completed",
                    int(case_passed), json.dumps(result), None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except PreparationUnavailable as exc:
            message = str(exc)
            errors.append(f"{case.case_id}: {message}")
            conn.execute(
                "INSERT INTO eval_case_results VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()), run_id, case.case_id, "error", 0,
                    json.dumps(
                        {
                            "case_id": case.case_id,
                            "title": case.title,
                            "expected_action_types": case.expected_action_types,
                            "scores": {},
                            "tags": case.tags,
                        }
                    ),
                    message, datetime.now(timezone.utc).isoformat(),
                ),
            )
        conn.commit()
    aggregates = {
        name: round(sum(values) / len(values), 4)
        for name, values in metric_values.items()
        if values
    }
    status = "completed" if not errors else ("partial" if completed else "failed")
    conn.execute(
        """UPDATE eval_runs SET status=?,completed_cases=?,passed_cases=?,
           aggregate_metrics=?,error=?,completed_at=? WHERE id=?""",
        (
            status, completed, passed, json.dumps(aggregates),
            " | ".join(errors) if errors else None,
            datetime.now(timezone.utc).isoformat(), run_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM eval_runs WHERE id=?", (run_id,)).fetchone()
    result = serialize_eval_run(conn, row, include_cases=True)
    conn.close()
    return result

@app.get("/api/v1/patients/{patient_id}/summaries")
def list_patient_summaries(patient_id: str, actor_role: str = "", actor_id: str = ""):
    conn = db(); authorize_patient(conn, patient_id, actor_role, actor_id)
    rows = conn.execute("""
      SELECT dv.id, dv.version, dv.status, dv.payload, dv.created_at,
             d.id AS document_id, d.filename
      FROM patient_documents pd
      JOIN documents d ON d.id=pd.document_id
      JOIN extraction_jobs j ON j.document_id=d.id
      JOIN document_versions dv ON dv.job_id=j.id
      WHERE pd.patient_id=?
      ORDER BY dv.created_at DESC
    """, (patient_id,)).fetchall()
    conn.close()
    import json
    return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

@app.post("/api/v1/extraction-jobs/{job_id}/process")
async def process_extraction_job(job_id: str, workspace_id: str = "demo-workspace", actor_role: str = "", actor_id: str = ""):
    require_clinician(actor_role, actor_id)
    conn = db()
    row = conn.execute("""
        SELECT j.id, j.document_id, d.filename FROM extraction_jobs j
        JOIN documents d ON d.id = j.document_id
        WHERE j.id = ? AND d.workspace_id = ?
    """, (job_id, workspace_id)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, "Extraction job not found.")
    try:
        result = await LlamaParseAdapter(os.getenv("LLAMA_CLOUD_API_KEY")).parse((STORAGE_PATH / row["document_id"]).read_bytes(), row["filename"])
        conn = db()
        conn.execute("UPDATE documents SET status='completed' WHERE id=(SELECT document_id FROM extraction_jobs WHERE id=?)", (job_id,))
        conn.execute("UPDATE extraction_jobs SET status='completed' WHERE id=?", (job_id,))
        conn.execute("INSERT OR REPLACE INTO extraction_results VALUES (?,?,?,?,datetime('now'))", (job_id, result.text, result.pages, result.provider))
        conn.commit(); conn.close()
        return {"job_id": job_id, "status": "completed", "provider": result.provider, "pages": result.pages, "text": result.text}
    except OcrUnavailable as exc:
        raise HTTPException(503, str(exc))
