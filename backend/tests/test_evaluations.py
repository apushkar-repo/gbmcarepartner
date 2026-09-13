import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app import main
from app.evaluations import (
    deterministic_scores,
    load_cases,
    retrieve_fixture,
    run_evaluation_case,
)


class EvaluationRunnerTests(unittest.TestCase):
    def test_dataset_is_single_version_and_contains_no_patient_records(self):
        cases = load_cases()

        self.assertEqual({case.dataset_version for case in cases}, {"1.0.0"})
        self.assertEqual(len({case.case_id for case in cases}), len(cases))
        self.assertTrue(all("fictional" in doc["filename"] for case in cases for doc in case.documents))

    def test_reference_context_is_retrieved_for_direct_instruction(self):
        case = load_cases()[0]

        result = retrieve_fixture(case)

        self.assertEqual(result["results"][0]["version_id"], "fixture-summary-001")

    def test_deterministic_checks_require_expected_behavior_and_citation(self):
        case = load_cases()[0]
        good = {
            "abstained": False,
            "citations": [{"version_id": "fixture-summary-001"}],
        }
        uncited = {"abstained": False, "citations": []}

        self.assertTrue(
            deterministic_scores(case, good, ["fixture-summary-001"])["passed"]
        )
        self.assertFalse(
            deterministic_scores(case, uncited, ["fixture-summary-001"])["passed"]
        )

    def test_gold_answer_is_not_passed_to_answering_workflow(self):
        case = load_cases()[0]
        observed = {}

        def fake_answerer(question, retriever):
            observed["question"] = question
            evidence = retriever(question)["results"]
            return {
                "answer": "Bring your current medication list and your questions.",
                "abstained": False,
                "citations": [{"version_id": evidence[0]["version_id"]}],
            }

        result = run_evaluation_case(case, answerer=fake_answerer)

        self.assertEqual(observed, {"question": case.question})
        self.assertTrue(result["scores"]["passed"])


class EvaluationApiTests(unittest.TestCase):
    def setUp(self):
        self._database = tempfile.TemporaryDirectory()
        self._original_path = main.DB_PATH
        main.DB_PATH = Path(self._database.name) / "carebridge.db"

    def tearDown(self):
        main.DB_PATH = self._original_path
        self._database.cleanup()

    def test_dataset_requires_clinician_role(self):
        with self.assertRaises(main.HTTPException) as raised:
            main.get_evaluation_dataset("patient", "patient-1")

        self.assertEqual(raised.exception.status_code, 403)

    def test_preparation_dataset_is_available_to_clinicians(self):
        result = main.get_preparation_evaluation_dataset("clinician", "c1")

        self.assertEqual(result["name"], "preparation-action-synthetic")
        self.assertEqual(result["case_count"], 8)

    @patch("app.main.run_preparation_evaluation_case")
    def test_preparation_run_is_persisted(self, run_case):
        def result_for(case):
            return {
                "case_id": case.case_id,
                "title": case.title,
                "expected_action_types": case.expected_action_types,
                "actual_action_types": case.expected_action_types,
                "specialist_proposals": [],
                "scores": {
                    "action_precision": 1.0,
                    "action_recall": 1.0,
                    "source_valid": True,
                    "routing_correct": True,
                    "passed": True,
                },
                "tags": case.tags,
            }

        run_case.side_effect = result_for

        result = main.create_preparation_evaluation_run("clinician", "c1")

        self.assertEqual(result["dataset_name"], "preparation-action-synthetic")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["passed_cases"], 8)
        self.assertEqual(len(result["cases"]), 8)

    @patch("app.main.run_evaluation_case")
    def test_run_is_persisted_with_actual_case_results(self, run_case):
        def result_for(case, include_ragas=False):
            return {
                "case_id": case.case_id,
                "title": case.title,
                "expected_behavior": case.expected_behavior,
                "actual_behavior": case.expected_behavior,
                "question": case.question,
                "reference_answer": case.reference_answer,
                "answer": "fixture output",
                "retrieved_context_ids": case.reference_context_ids,
                "reference_context_ids": case.reference_context_ids,
                "cited_context_ids": case.reference_context_ids,
                "scores": {
                    "behavior_correct": True,
                    "retrieval_recall_at_5": 1.0,
                    "citation_precision": 1.0,
                    "citation_recall": 1.0,
                    "passed": True,
                },
                "tags": case.tags,
            }

        run_case.side_effect = result_for

        result = main.create_evaluation_run(
            main.EvaluationRunRequest(include_ragas=False), "clinician", "clinician-1"
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["passed_cases"], result["total_cases"])
        self.assertEqual(len(result["cases"]), result["total_cases"])
        loaded = main.get_evaluation_run(result["id"], "clinician", "clinician-1")
        self.assertEqual(loaded["id"], result["id"])


if __name__ == "__main__":
    unittest.main()
