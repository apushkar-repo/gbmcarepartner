from pathlib import Path
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from app import main


class ReminderLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._database = tempfile.TemporaryDirectory()
        self._original_path = main.DB_PATH
        main.DB_PATH = Path(self._database.name) / "carebridge.db"
        conn = main.db()
        conn.execute(
            "INSERT INTO patients VALUES (?,?,?,?,?,?)",
            (
                "patient-1",
                "Test Patient",
                "patient@example.test",
                "+15555550100",
                "clinician-1",
                "now",
            ),
        )
        conn.execute(
            """INSERT INTO preparation_plans
               (id,patient_id,status,summary,message,verified,model,created_by_role,
                created_by_id,created_at,approved_by,approved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "plan-1",
                "patient-1",
                "approved",
                "Prepare",
                "Approved",
                1,
                "test-model",
                "patient",
                "patient-1",
                "now",
                "patient-1",
                "now",
            ),
        )
        conn.execute(
            """INSERT INTO preparation_tasks
               (id,plan_id,patient_id,title,description,origin_type,
                source_version_ids,source_question_ids,blocked_reason,status,
                position,completed_by,completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "task-1",
                "plan-1",
                "patient-1",
                "Bring your records",
                "Bring the requested records.",
                "document_instruction",
                json.dumps(["version-1"]),
                json.dumps(["question-1"]),
                None,
                "open",
                0,
                None,
                None,
            ),
        )
        conn.execute(
            """INSERT INTO care_questions
               (id,patient_id,text,original_text,source_label,source_version_ids,
                status,created_by_role,created_by_id,clinician_response,
                responded_by,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "question-1", "patient-1", "What should I bring?",
                "What should I bring?", "Added by you", "[]", "open",
                "patient", "patient-1", None, None, "now", "now",
            ),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        main.DB_PATH = self._original_path
        self._database.cleanup()

    @staticmethod
    def draft(**changes):
        values = {
            "task_id": "task-1",
            "text": "Prepare for your upcoming visit.",
            "local_date": "2099-06-15",
            "local_time": "09:30",
            "timezone": "America/New_York",
            "channel": "email",
        }
        values.update(changes)
        return main.ReminderDraftRequest(**values)

    def test_approval_is_idempotent_and_does_not_complete_task(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        scheduled = main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )
        retried = main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )

        self.assertEqual(scheduled["status"], "scheduled")
        self.assertEqual(retried["provider_receipt"], scheduled["provider_receipt"])
        conn = main.db()
        operations = conn.execute(
            "SELECT COUNT(*) FROM mock_reminder_operations"
        ).fetchone()[0]
        task_status = conn.execute(
            "SELECT status FROM preparation_tasks WHERE id='task-1'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(operations, 1)
        self.assertEqual(task_status, "open")

    def test_edit_after_approval_requires_fresh_approval(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        scheduled = main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )

        revised = main.revise_reminder(
            "patient-1",
            created["reminder_id"],
            self.draft(text="Prepare tomorrow.", expected_version=1),
            "patient",
            "patient-1",
        )

        self.assertEqual(revised["version"], 2)
        self.assertEqual(revised["status"], "awaiting_reapproval")
        self.assertIsNone(revised["approved_at"])
        conn = main.db()
        old_operation = conn.execute(
            "SELECT status FROM mock_reminder_operations WHERE receipt_id=?",
            (scheduled["provider_receipt"],),
        ).fetchone()
        conn.close()
        self.assertEqual(old_operation["status"], "cancelled")

    def test_cancel_is_persistent_and_repeatable(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        cancelled = main.cancel_reminder(
            "patient-1", created["reminder_id"], "patient", "patient-1"
        )
        repeated = main.cancel_reminder(
            "patient-1", created["reminder_id"], "patient", "patient-1"
        )
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(repeated["status"], "cancelled")

    def test_care_partner_cannot_approve(self):
        main.grant_care_partner(
            "patient-1", main.CarePartnerGrant(partner_email="partner@example.test")
        )
        created = main.create_reminder(
            "patient-1", self.draft(), "partner", "partner@example.test"
        )
        with self.assertRaises(main.HTTPException) as raised:
            main.approve_reminder(
                "patient-1",
                created["reminder_id"],
                main.ReminderApproval(approval=True, expected_version=1),
                "partner",
                "partner@example.test",
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_daylight_saving_gap_and_overlap_are_rejected(self):
        with self.assertRaises(main.HTTPException) as gap:
            main.validate_reminder_schedule(
                "2027-03-14", "02:30", "America/New_York"
            )
        with self.assertRaises(main.HTTPException) as overlap:
            main.validate_reminder_schedule(
                "2027-11-07", "01:30", "America/New_York"
            )
        self.assertEqual(gap.exception.status_code, 400)
        self.assertEqual(overlap.exception.status_code, 400)

    def test_task_completion_pauses_a_scheduled_reminder(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )

        main.update_preparation_task(
            "patient-1",
            "task-1",
            main.PreparationTaskUpdate(complete=True),
            "patient",
            "patient-1",
        )
        reminder = main.get_current_reminder(
            "patient-1", "patient", "patient-1"
        )
        self.assertEqual(reminder["status"], "paused")
        self.assertEqual(
            reminder["status_reason"],
            "The linked preparation item was marked complete.",
        )

    def test_question_change_invalidates_plan_and_pauses_reminder(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )

        main.update_care_question(
            "patient-1",
            "question-1",
            main.CareQuestionUpdate(text="What records should I bring?"),
            "patient",
            "patient-1",
        )

        plan = main.get_current_preparation_plan(
            "patient-1", "patient", "patient-1"
        )
        reminder = main.get_current_reminder(
            "patient-1", "patient", "patient-1"
        )
        self.assertEqual(plan["status"], "needs_review")
        self.assertEqual(reminder["status"], "paused")

    def test_revoking_reminder_permission_pauses_delivery_and_versions_consent(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        scheduled = main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )

        revoked = main.update_reminder_consent(
            "patient-1",
            main.ReminderConsentUpdate(enabled=False),
            "patient",
            "patient-1",
        )
        reminder = main.get_current_reminder(
            "patient-1", "patient", "patient-1"
        )

        self.assertFalse(revoked["enabled"])
        self.assertEqual(revoked["version"], 2)
        self.assertEqual(reminder["status"], "paused")
        self.assertIn("disabled reminder permission", reminder["status_reason"])
        conn = main.db()
        provider_status = conn.execute(
            "SELECT status FROM mock_reminder_operations WHERE receipt_id=?",
            (scheduled["provider_receipt"],),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(provider_status, "cancelled")

    def test_permission_version_change_invalidates_an_unapproved_draft(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        main.update_reminder_consent(
            "patient-1",
            main.ReminderConsentUpdate(enabled=False),
            "patient",
            "patient-1",
        )
        main.update_reminder_consent(
            "patient-1",
            main.ReminderConsentUpdate(enabled=True),
            "patient",
            "patient-1",
        )

        with self.assertRaises(main.HTTPException) as raised:
            main.approve_reminder(
                "patient-1",
                created["reminder_id"],
                main.ReminderApproval(approval=True, expected_version=1),
                "patient",
                "patient-1",
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_delivery_timeout_after_commit_reconciles_without_duplicate(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        scheduled = main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )

        uncertain = main.simulate_reminder_delivery(
            "patient-1",
            created["reminder_id"],
            main.DeliverySimulationRequest(
                outcome="timeout_after_commit", expected_version=1
            ),
            "patient",
            "patient-1",
        )
        reconciled = main.reconcile_reminder_delivery(
            "patient-1", created["reminder_id"], "patient", "patient-1"
        )

        self.assertEqual(uncertain["status"], "outcome_unknown")
        self.assertEqual(reconciled["status"], "delivered")
        self.assertEqual(reconciled["provider_receipt"], scheduled["provider_receipt"])
        conn = main.db()
        operations = conn.execute(
            "SELECT COUNT(*) FROM mock_reminder_operations"
        ).fetchone()[0]
        task_status = conn.execute(
            "SELECT status FROM preparation_tasks WHERE id='task-1'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(operations, 1)
        self.assertEqual(task_status, "open")

    def test_timeout_before_commit_reconciles_to_scheduled_then_delivers(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )
        main.simulate_reminder_delivery(
            "patient-1",
            created["reminder_id"],
            main.DeliverySimulationRequest(
                outcome="timeout_before_commit", expected_version=1
            ),
            "patient",
            "patient-1",
        )

        reconciled = main.reconcile_reminder_delivery(
            "patient-1", created["reminder_id"], "patient", "patient-1"
        )
        delivered = main.simulate_reminder_delivery(
            "patient-1",
            created["reminder_id"],
            main.DeliverySimulationRequest(outcome="delivered", expected_version=1),
            "patient",
            "patient-1",
        )

        self.assertEqual(reconciled["status"], "scheduled")
        self.assertEqual(delivered["status"], "delivered")

    @patch.dict(os.environ, {"MOCK_PROVIDER_WEBHOOK_SECRET": "test-secret"})
    def test_signed_callback_is_applied_once(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        scheduled = main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )
        callback = main.MockDeliveryCallback(
            event_id="event-1",
            receipt_id=scheduled["provider_receipt"],
            status="delivered",
        )
        signed = f"{callback.event_id}.{callback.receipt_id}.{callback.status}".encode()
        signature = hmac.new(
            b"test-secret", signed, hashlib.sha256
        ).hexdigest()

        first = main.receive_mock_reminder_callback(callback, signature)
        second = main.receive_mock_reminder_callback(callback, signature)
        reminder = main.get_current_reminder(
            "patient-1", "patient", "patient-1"
        )

        self.assertTrue(first["applied"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(reminder["status"], "delivered")

    def test_activity_projects_events_without_reminder_content_or_recipient(self):
        created = main.create_reminder(
            "patient-1", self.draft(), "patient", "patient-1"
        )
        main.approve_reminder(
            "patient-1",
            created["reminder_id"],
            main.ReminderApproval(approval=True, expected_version=1),
            "patient",
            "patient-1",
        )
        main.simulate_reminder_delivery(
            "patient-1",
            created["reminder_id"],
            main.DeliverySimulationRequest(outcome="delivered", expected_version=1),
            "patient",
            "patient-1",
        )

        activity = main.list_patient_activity(
            "patient-1", "patient", "patient-1"
        )
        serialized = json.dumps(activity)

        self.assertIn("Mock reminder delivered", serialized)
        self.assertNotIn("Prepare for your upcoming visit", serialized)
        self.assertNotIn("patient@example.test", serialized)


if __name__ == "__main__":
    unittest.main()
