from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from app import main


class ArrangementAndSharingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = main.DB_PATH
        main.DB_PATH = Path(self.temp.name) / "carebridge.db"
        conn = main.db()
        conn.execute("INSERT INTO patients VALUES (?,?,?,?,?,?)", ("p1","Patient","p@test.local",None,"c1","now"))
        conn.commit(); conn.close()

    def tearDown(self):
        main.DB_PATH = self.original
        self.temp.cleanup()

    def test_exact_appointment_approval_is_idempotent(self):
        draft = main.create_arrangement("p1", main.ArrangementDraft(action_type="appointment", payload={"clinic":"Fieldstone Clinic","date":"2026-10-08","time":"10:00","timezone":"America/New_York","appointment_type":"Follow-up"}), "patient", "p1")
        request = main.ArrangementApproval(approval=True, expected_version=1)

        first = main.approve_arrangement("p1", draft["id"], request, "patient", "p1")
        second = main.approve_arrangement("p1", draft["id"], request, "patient", "p1")

        self.assertEqual(first["provider_receipt"], second["provider_receipt"])
        self.assertEqual(first["status"], "confirmed")

    def test_invalid_lab_order_waits_for_information(self):
        draft = main.create_arrangement("p1", main.ArrangementDraft(action_type="lab", payload={"order_id":"unknown","facility":"Fieldstone Lab","date":"2026-10-06","time":"08:30","timezone":"America/New_York"}), "patient", "p1")

        self.assertEqual(draft["status"], "awaiting_information")
        self.assertIn("valid_order_id", draft["payload"]["missing_inputs"])

    def test_ambiguous_arrangement_date_waits_for_information(self):
        draft = main.create_arrangement(
            "p1",
            main.ArrangementDraft(
                action_type="appointment",
                payload={"clinic":"Fieldstone Clinic","date":"9/16","time":"10:00","timezone":"America/New_York","appointment_type":"Follow-up"},
            ),
            "patient",
            "p1",
        )

        self.assertEqual(draft["status"], "awaiting_information")
        self.assertIn("full_date_with_year", draft["payload"]["missing_inputs"])

    def test_patient_can_revoke_persisted_partner_access(self):
        grant = main.grant_care_partner("p1", main.CarePartnerGrant(partner_email="partner@test.local"))
        current = main.list_care_partners("p1", "patient", "p1")[0]

        changed = main.update_care_partner("p1", grant["id"], main.CarePartnerPermissionUpdate(status="revoked", expected_version=current["version"]), "patient", "p1")

        self.assertEqual(changed["status"], "revoked")
        with self.assertRaises(main.HTTPException):
            main.list_patient_summaries("p1", "partner", "partner@test.local")

    def test_preparation_orchestrator_creates_specialist_proposals_once(self):
        conn = main.db()
        conn.execute(
            "INSERT INTO preparation_plans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("plan-1", "p1", "approved", "Next visit", "", 1, "test", "patient", "p1", "now", "p1", "now"),
        )
        actions = [
            ("clinic_appointment", "2026-09-16", "Follow-up visit"),
            ("laboratory", None, "Blood work"),
            ("imaging", None, "MRI"),
        ]
        for position, (action_type, documented_date, service) in enumerate(actions):
            task_id = str(uuid4())
            conn.execute(
                "INSERT INTO preparation_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, "plan-1", "p1", service, service, "document_instruction", "[]", "[]", None, "open", position, None, None),
            )
            conn.execute(
                "INSERT INTO preparation_task_actions VALUES (?,?,?,?,?,?,?,?)",
                (task_id, action_type, documented_date, service, None, "identified", None, "now"),
            )
        conn.commit()
        conn.close()

        first = main.orchestrate_preparation_actions("p1", "plan-1", "p1")
        second = main.orchestrate_preparation_actions("p1", "plan-1", "p1")

        self.assertEqual(len(first), 3)
        self.assertEqual(second, [])
        by_type = {item["action_type"]: item for item in first}
        self.assertEqual(by_type["appointment"]["payload"]["date"], "2026-09-16")
        self.assertEqual(by_type["lab"]["payload"]["date"], "2026-09-13")
        self.assertEqual(by_type["imaging"]["payload"]["date"], "2026-09-09")
        self.assertEqual(by_type["lab"]["payload"]["order_id"], "")
        self.assertEqual(by_type["imaging"]["payload"]["order_id"], "")
        self.assertEqual(by_type["appointment"]["status"], "awaiting_approval")
        self.assertEqual(by_type["lab"]["status"], "awaiting_information")
        self.assertEqual(by_type["imaging"]["status"], "awaiting_information")

    def test_approving_plan_automatically_invokes_specialist_agent(self):
        conn = main.db()
        conn.execute(
            "INSERT INTO preparation_plans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("plan-auto", "p1", "draft", "Next visit", "", 1, "test", "patient", "p1", "now", None, None),
        )
        conn.execute(
            "INSERT INTO preparation_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("task-auto", "plan-auto", "p1", "Book follow-up", "Book the documented follow-up.", "document_instruction", "[]", "[]", None, "proposed", 0, None, None),
        )
        conn.execute(
            "INSERT INTO preparation_task_actions VALUES (?,?,?,?,?,?,?,?)",
            ("task-auto", "clinic_appointment", "2026-09-16", "Follow-up", None, "identified", None, "now"),
        )
        conn.commit()
        conn.close()

        approved = main.approve_preparation_plan(
            "p1", "plan-auto", main.PreparationApproval(approval=True), "patient", "p1"
        )

        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["items"][0]["action"]["specialist_status"], "awaiting_approval")
        self.assertIsNotNone(approved["items"][0]["action"]["arrangement_id"])

    def test_travel_agent_creates_a_visible_proposal_that_requests_patient_details(self):
        conn = main.db()
        conn.execute(
            "INSERT INTO preparation_plans VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("plan-travel", "p1", "approved", "Next visit", "", 1, "test", "patient", "p1", "now", "p1", "now"),
        )
        conn.execute(
            "INSERT INTO preparation_tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("task-travel", "plan-travel", "p1", "Review travel", "Choose whether travel help is needed.", "app_suggestion", "[]", "[]", "Pickup needed", "open", 0, None, None),
        )
        conn.execute(
            "INSERT INTO preparation_task_actions VALUES (?,?,?,?,?,?,?,?)",
            ("task-travel", "travel", "2026-10-08", "Neuro-Oncology Clinic", None, "identified", None, "now"),
        )
        conn.commit()
        conn.close()

        created = main.orchestrate_preparation_actions("p1", "plan-travel", "p1")

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["action_type"], "travel")
        self.assertEqual(created[0]["status"], "awaiting_information")
        self.assertIn("pickup", created[0]["payload"]["missing_inputs"])

    def test_calendar_contains_only_patient_approved_arrangements(self):
        draft = main.create_arrangement(
            "p1",
            main.ArrangementDraft(
                action_type="appointment",
                payload={"clinic":"Fieldstone Clinic","date":"2026-09-16","time":"10:00","timezone":"America/New_York","appointment_type":"Follow-up"},
            ),
            "patient",
            "p1",
        )
        empty_calendar = main.preparation_calendar("p1", "patient", "p1")
        self.assertNotIn(b"BEGIN:VEVENT", empty_calendar.body)

        main.approve_arrangement(
            "p1",
            draft["id"],
            main.ArrangementApproval(approval=True, expected_version=1),
            "patient",
            "p1",
        )
        calendar = main.preparation_calendar("p1", "patient", "p1")
        self.assertIn(b"BEGIN:VEVENT", calendar.body)
        self.assertIn(b"DTSTART;TZID=America/New_York:20260916T100000", calendar.body)


if __name__ == "__main__":
    unittest.main()
