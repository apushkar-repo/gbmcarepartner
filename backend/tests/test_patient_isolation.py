from pathlib import Path
import tempfile
import unittest

from app import main


class PatientIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = main.DB_PATH
        main.DB_PATH = Path(self.temp.name) / "carebridge.db"
        conn = main.db()
        conn.executemany(
            "INSERT INTO patients VALUES (?,?,?,?,?,?)",
            [
                ("patient-a", "Patient A", "a@example.test", None, "c1", "now"),
                ("patient-b", "Patient B", "b@example.test", None, "c1", "now"),
            ],
        )
        conn.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
            ("document-b", "workspace", "private-b.png", "image/png", 10, "hash", "completed", "now"),
        )
        conn.execute(
            "INSERT INTO extraction_jobs VALUES (?,?,?,?)",
            ("job-b", "document-b", "completed", "now"),
        )
        conn.execute(
            "INSERT INTO extraction_results VALUES (?,?,?,?,?)",
            ("job-b", "Patient B private transcript", 1, "test", "now"),
        )
        conn.execute(
            "INSERT INTO patient_documents VALUES (?,?)",
            ("patient-b", "document-b"),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        main.DB_PATH = self.original_db
        self.temp.cleanup()

    def assert_forbidden(self, call):
        with self.assertRaises(main.HTTPException) as raised:
            call()
        self.assertEqual(raised.exception.status_code, 403)

    def test_patient_cannot_enumerate_the_patient_directory(self):
        self.assert_forbidden(lambda: main.list_patients("patient", "patient-a"))

    def test_patient_cannot_read_another_patients_document_or_extraction(self):
        self.assert_forbidden(
            lambda: main.get_document(
                "document-b", "workspace", "patient", "patient-a"
            )
        )
        self.assert_forbidden(
            lambda: main.get_extraction_job(
                "job-b", "workspace", "patient", "patient-a"
            )
        )
        self.assert_forbidden(
            lambda: main.get_extraction_result(
                "job-b", "workspace", "patient", "patient-a"
            )
        )

    def test_patient_cannot_access_another_patients_workspace_resources(self):
        checks = [
            lambda: main.list_patient_summaries(
                "patient-b", "patient", "patient-a"
            ),
            lambda: main.list_care_questions("patient-b", "patient", "patient-a"),
            lambda: main.get_current_preparation_plan(
                "patient-b", "patient", "patient-a"
            ),
            lambda: main.list_arrangements("patient-b", "patient", "patient-a"),
            lambda: main.list_patient_activity(
                "patient-b", "patient", "patient-a"
            ),
            lambda: main.preparation_calendar(
                "patient-b", "patient", "patient-a"
            ),
        ]
        for check in checks:
            with self.subTest(check=check):
                self.assert_forbidden(check)

    def test_patient_cannot_grant_access_to_another_patients_workspace(self):
        self.assert_forbidden(
            lambda: main.grant_care_partner(
                "patient-b",
                main.CarePartnerGrant(partner_email="attacker@example.test"),
                "patient",
                "patient-a",
            )
        )

    def test_patient_and_clinician_can_grant_access_to_the_patient_workspace(self):
        patient_grant = main.grant_care_partner(
            "patient-a",
            main.CarePartnerGrant(partner_email="patient-choice@example.test"),
            "patient",
            "patient-a",
        )
        clinician_grant = main.grant_care_partner(
            "patient-b",
            main.CarePartnerGrant(partner_email="clinician-choice@example.test"),
            "clinician",
            "c1",
        )

        self.assertEqual(patient_grant["status"], "active")
        self.assertEqual(clinician_grant["status"], "active")

    def test_removed_patient_gets_a_clear_sharing_error(self):
        with self.assertRaises(main.HTTPException) as raised:
            main.list_care_partners("removed-patient", "patient", "removed-patient")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertIn("onboard the patient again", raised.exception.detail)

    def test_document_management_endpoints_require_a_clinician(self):
        self.assert_forbidden(
            lambda: main.list_documents("workspace", "patient", "patient-a")
        )
        self.assert_forbidden(
            lambda: main.index_document_version(
                "unknown-version", "patient", "patient-a"
            )
        )


if __name__ == "__main__":
    unittest.main()
