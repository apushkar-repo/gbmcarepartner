import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import main


class SearchFlowTests(unittest.TestCase):
    def setUp(self):
        self._database = tempfile.TemporaryDirectory()
        self._original_path = main.DB_PATH
        main.DB_PATH = Path(self._database.name) / "carebridge.db"
        conn = main.db()
        conn.execute(
            "INSERT INTO patients VALUES (?,?,?,?,?,?)",
            ("patient-1", "Test Patient", "patient@example.test", None, "clinician-1", "now"),
        )
        conn.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
            ("document-1", "workspace-1", "visit.png", "image/png", 10, "digest", "completed", "now"),
        )
        conn.execute(
            "INSERT INTO extraction_jobs VALUES (?,?,?,?)",
            ("job-1", "document-1", "completed", "now"),
        )
        conn.execute(
            "INSERT INTO patient_documents VALUES (?,?)",
            ("patient-1", "document-1"),
        )
        conn.execute(
            "INSERT INTO document_versions VALUES (?,?,?,?,?,?,?)",
            (
                "version-1",
                "job-1",
                json.dumps({"text": "Bring your medication list to the next visit.", "audience": "patient"}),
                1,
                "indexing_pending",
                "clinician-1",
                "now",
            ),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        main.DB_PATH = self._original_path
        self._database.cleanup()

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "",
            "PINECONE_API_KEY": "",
            "PINECONE_INDEX_HOST": "",
            "PINECONE_INDEX": "",
        },
    )
    def test_approved_summary_is_searchable_with_bm25_fallback(self):
        indexed = main.index_document_version("version-1", "clinician", "c1")
        result = main.search_patient_summaries(
            "patient-1", "medication", "patient", "patient-1"
        )

        self.assertEqual(indexed["retrieval_modes"], ["bm25"])
        self.assertEqual(result["retrieval_mode"], "bm25")
        self.assertEqual(result["results"][0]["version_id"], "version-1")
        self.assertIn("medication list", result["results"][0]["content"])

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "",
            "PINECONE_API_KEY": "",
            "PINECONE_INDEX_HOST": "",
            "PINECONE_INDEX": "",
        },
    )
    def test_answer_endpoint_abstains_without_model_call_when_no_evidence_exists(self):
        result = main.answer_patient_question(
            "patient-1",
            main.QuestionRequest(question="What is tomorrow's weather?"),
            "patient",
            "patient-1",
        )

        self.assertTrue(result["abstained"])
        self.assertEqual(result["citations"], [])
        self.assertIn("run_id", result)
        conn = main.db()
        run = conn.execute(
            "SELECT * FROM workflow_runs WHERE id=?", (result["run_id"],)
        ).fetchone()
        conn.close()
        self.assertEqual(run["status"], "stopped")
        self.assertEqual(run["stop_reason"], "insufficient_supported_evidence")

    def test_answer_endpoint_checks_patient_access_before_retrieval(self):
        with self.assertRaises(main.HTTPException) as raised:
            main.answer_patient_question(
                "patient-1",
                main.QuestionRequest(question="What should I bring?"),
                "patient",
                "another-patient",
            )

        self.assertEqual(raised.exception.status_code, 403)

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "",
            "PINECONE_API_KEY": "",
            "PINECONE_INDEX_HOST": "",
            "PINECONE_INDEX": "",
        },
    )
    def test_new_document_version_supersedes_search_and_plan_sources(self):
        main.index_document_version("version-1", "clinician", "c1")
        conn = main.db()
        conn.execute(
            """INSERT INTO preparation_plans
               (id,patient_id,status,summary,message,verified,model,created_by_role,
                created_by_id,created_at,approved_by,approved_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "plan-1", "patient-1", "approved", "Prepare", "Approved", 1,
                "test", "patient", "patient-1", "now", "patient-1", "now",
            ),
        )
        conn.execute(
            """INSERT INTO preparation_tasks
               (id,plan_id,patient_id,title,description,origin_type,
                source_version_ids,source_question_ids,blocked_reason,status,
                position,completed_by,completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "task-1", "plan-1", "patient-1", "Bring records", "Bring records",
                "document_instruction", json.dumps(["version-1"]), "[]", None,
                "open", 0, None, None,
            ),
        )
        conn.execute(
            "INSERT INTO document_versions VALUES (?,?,?,?,?,?,?)",
            (
                "version-2", "job-1",
                json.dumps({"text": "Bring the corrected report.", "audience": "patient"}),
                2, "indexing_pending", "clinician-1", "later",
            ),
        )
        conn.commit()
        conn.close()

        main.index_document_version("version-2", "clinician", "c1")

        conn = main.db()
        statuses = {
            row["id"]: row["status"]
            for row in conn.execute(
                "SELECT id,status FROM document_versions WHERE job_id='job-1'"
            ).fetchall()
        }
        plan_status = conn.execute(
            "SELECT status FROM preparation_plans WHERE id='plan-1'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(statuses["version-1"], "superseded")
        self.assertEqual(statuses["version-2"], "index_ready")
        self.assertEqual(plan_status, "needs_review")
        results = main.search_patient_summaries(
            "patient-1", "corrected", "patient", "patient-1"
        )
        self.assertEqual(results["results"][0]["version_id"], "version-2")

    def test_out_of_order_indexing_cannot_activate_an_older_version(self):
        conn = main.db()
        conn.execute(
            "INSERT INTO document_versions VALUES (?,?,?,?,?,?,?)",
            (
                "version-2", "job-1",
                json.dumps({"text": "Newer text", "audience": "patient"}),
                2, "indexing_pending", "clinician-1", "later",
            ),
        )
        conn.commit()
        conn.close()

        result = main.index_document_version("version-1", "clinician", "c1")

        self.assertEqual(result["status"], "superseded")
        conn = main.db()
        indexed = conn.execute(
            "SELECT COUNT(*) FROM summary_fts WHERE version_id='version-1'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(indexed, 0)

    def test_saved_question_and_clinician_response_persist(self):
        created = main.create_care_question(
            "patient-1",
            main.CareQuestionCreate(
                text="Should I bring my medication list?",
                original_text="What should I bring?",
                source_label="visit.png · Version 1",
            ),
            "patient",
            "patient-1",
        )

        inbox = main.list_clinician_questions("clinician", "clinician-1")
        self.assertEqual(inbox[0]["id"], created["id"])
        self.assertEqual(inbox[0]["patient_name"], "Test Patient")

        main.respond_to_care_question(
            created["id"],
            main.ClinicianQuestionResponse(
                response="Yes, please bring the current list.", status="resolved"
            ),
            "clinician",
            "clinician-1",
        )
        patient_questions = main.list_care_questions(
            "patient-1", "patient", "patient-1"
        )

        self.assertEqual(patient_questions[0]["status"], "resolved")
        self.assertEqual(
            patient_questions[0]["clinician_response"],
            "Yes, please bring the current list.",
        )
        conn = main.db()
        events = conn.execute(
            "SELECT action FROM care_question_events WHERE question_id=? ORDER BY created_at",
            (created["id"],),
        ).fetchall()
        conn.close()
        self.assertEqual(
            [event["action"] for event in events],
            ["created", "clinician_responded"],
        )

    def test_unapproved_question_source_is_rejected(self):
        with self.assertRaises(main.HTTPException) as raised:
            main.create_care_question(
                "patient-1",
                main.CareQuestionCreate(
                    text="Is this in my record?",
                    source_version_ids=["version-1"],
                ),
                "patient",
                "patient-1",
            )

        self.assertEqual(raised.exception.status_code, 400)

    @patch("app.main.generate_preparation")
    def test_preparation_draft_approval_and_completion_are_persistent(self, generate):
        generate.return_value = {
            "summary": "Prepare for the visit",
            "message": "Review each proposed item before saving the checklist.",
            "verified": True,
            "model": "test-model",
            "items": [
                {
                    "title": "Bring your medication list",
                    "description": "Bring the current list to the visit.",
                    "origin_type": "document_instruction",
                    "source_version_ids": ["version-1"],
                    "source_question_ids": [],
                    "blocked_reason": None,
                }
            ],
        }
        draft = main.create_preparation_plan(
            "patient-1", "patient", "patient-1"
        )
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["items"][0]["status"], "proposed")

        approved = main.approve_preparation_plan(
            "patient-1",
            draft["id"],
            main.PreparationApproval(approval=True),
            "patient",
            "patient-1",
        )
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["items"][0]["status"], "open")

        completed = main.update_preparation_task(
            "patient-1",
            approved["items"][0]["id"],
            main.PreparationTaskUpdate(complete=True),
            "patient",
            "patient-1",
        )
        self.assertEqual(completed["items"][0]["status"], "completed")
        loaded = main.get_current_preparation_plan(
            "patient-1", "patient", "patient-1"
        )
        self.assertEqual(loaded["items"][0]["status"], "completed")

        generate.return_value = {
            "summary": "No preparation items yet",
            "message": "No supported preparation items were found.",
            "verified": True,
            "model": None,
            "items": [],
        }
        with self.assertRaises(main.HTTPException) as raised:
            main.create_preparation_plan(
                "patient-1", "patient", "patient-1"
            )
        self.assertEqual(raised.exception.status_code, 422)
        still_current = main.get_current_preparation_plan(
            "patient-1", "patient", "patient-1"
        )
        self.assertEqual(still_current["id"], approved["id"])

    @patch("app.main.generate_preparation")
    def test_care_partner_cannot_approve_a_preparation_draft(self, generate):
        generate.return_value = {
            "summary": "Prepare for the visit",
            "message": "Review this draft.",
            "verified": True,
            "model": "test-model",
            "items": [
                {
                    "title": "Discuss the saved question",
                    "description": "Bring the question to the visit.",
                    "origin_type": "saved_question",
                    "source_version_ids": [],
                    "source_question_ids": [],
                    "blocked_reason": None,
                }
            ],
        }
        main.grant_care_partner(
            "patient-1",
            main.CarePartnerGrant(partner_email="partner@example.test"),
            "patient",
            "patient-1",
        )
        draft = main.create_preparation_plan(
            "patient-1", "partner", "partner@example.test"
        )

        with self.assertRaises(main.HTTPException) as raised:
            main.approve_preparation_plan(
                "patient-1",
                draft["id"],
                main.PreparationApproval(approval=True),
                "partner",
                "partner@example.test",
            )

        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
