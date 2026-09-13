"""Idempotent, local mock reminder provider."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from uuid import uuid4


class MockSchedulerConflict(RuntimeError):
    """An idempotency key was reused with a different payload."""


class MockSchedulerTimeout(RuntimeError):
    def __init__(self, committed: bool):
        super().__init__("The mock provider response timed out.")
        self.committed = committed


@dataclass(frozen=True)
class MockScheduleReceipt:
    receipt_id: str
    status: str
    simulation: bool = True


class MockReminderScheduler:
    provider_name = "carebridge-local-mock"

    def schedule(
        self,
        conn: sqlite3.Connection,
        *,
        idempotency_key: str,
        reminder_id: str,
        payload_hash: str,
        now: str,
    ) -> MockScheduleReceipt:
        existing = conn.execute(
            "SELECT * FROM mock_reminder_operations WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise MockSchedulerConflict(
                    "The scheduling key is already bound to another payload."
                )
            return MockScheduleReceipt(
                receipt_id=existing["receipt_id"], status=existing["status"]
            )
        receipt_id = f"CB-MOCK-{uuid4().hex[:12].upper()}"
        conn.execute(
            """INSERT INTO mock_reminder_operations
               (idempotency_key,reminder_id,payload_hash,status,receipt_id,
                provider,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                idempotency_key,
                reminder_id,
                payload_hash,
                "scheduled",
                receipt_id,
                self.provider_name,
                now,
                now,
            ),
        )
        return MockScheduleReceipt(receipt_id=receipt_id, status="scheduled")

    def cancel(
        self,
        conn: sqlite3.Connection,
        *,
        idempotency_key: str,
        now: str,
    ) -> MockScheduleReceipt | None:
        existing = conn.execute(
            "SELECT * FROM mock_reminder_operations WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing is None:
            return None
        conn.execute(
            "UPDATE mock_reminder_operations SET status='cancelled',updated_at=? WHERE idempotency_key=?",
            (now, idempotency_key),
        )
        return MockScheduleReceipt(
            receipt_id=existing["receipt_id"], status="cancelled"
        )

    def dispatch(
        self,
        conn: sqlite3.Connection,
        *,
        idempotency_key: str,
        outcome: str,
        now: str,
    ) -> MockScheduleReceipt:
        existing = conn.execute(
            "SELECT * FROM mock_reminder_operations WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if existing is None:
            raise MockSchedulerConflict("The scheduled mock operation was not found.")
        if existing["status"] in {"delivered", "failed", "cancelled"}:
            return MockScheduleReceipt(
                receipt_id=existing["receipt_id"], status=existing["status"]
            )
        if outcome == "timeout_before_commit":
            raise MockSchedulerTimeout(committed=False)
        provider_status = "delivered" if outcome in {"delivered", "timeout_after_commit"} else "failed"
        conn.execute(
            "UPDATE mock_reminder_operations SET status=?,updated_at=? WHERE idempotency_key=?",
            (provider_status, now, idempotency_key),
        )
        if outcome == "timeout_after_commit":
            raise MockSchedulerTimeout(committed=True)
        return MockScheduleReceipt(
            receipt_id=existing["receipt_id"], status=provider_status
        )

    def get_status(
        self, conn: sqlite3.Connection, *, idempotency_key: str
    ) -> MockScheduleReceipt | None:
        row = conn.execute(
            "SELECT * FROM mock_reminder_operations WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        return MockScheduleReceipt(receipt_id=row["receipt_id"], status=row["status"])

    def record_callback(
        self,
        conn: sqlite3.Connection,
        *,
        receipt_id: str,
        status: str,
        now: str,
    ) -> sqlite3.Row | None:
        row = conn.execute(
            "SELECT * FROM mock_reminder_operations WHERE receipt_id=?", (receipt_id,)
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE mock_reminder_operations SET status=?,updated_at=? WHERE receipt_id=?",
            (status, now, receipt_id),
        )
        return row
