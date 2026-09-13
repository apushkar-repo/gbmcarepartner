import unittest

from app.preparation_evaluations import (
    load_preparation_cases,
    run_preparation_evaluation_case,
    score_preparation_result,
)


class PreparationEvaluationTests(unittest.TestCase):
    def test_dataset_is_versioned_unique_and_synthetic(self):
        cases = load_preparation_cases()

        self.assertEqual({case.dataset_version for case in cases}, {"1.1.0"})
        self.assertEqual(len(cases), 8)
        self.assertEqual(len({case.case_id for case in cases}), len(cases))
        self.assertTrue(
            all(
                "synthetic" in summary["filename"]
                for case in cases
                for summary in case.context.get("summaries", [])
            )
        )

    def test_complete_multi_agent_result_passes(self):
        case = load_preparation_cases()[0]
        result = {
            "verified": True,
            "items": [
                {
                    "action_type": "clinic_appointment",
                    "documented_date": "2026-09-16",
                    "source_version_ids": ["prep-source-001"],
                    "source_question_ids": [],
                    "blocked_reason": None,
                },
                {
                    "action_type": "laboratory",
                    "documented_service": "Blood work",
                    "source_version_ids": ["prep-source-001"],
                    "source_question_ids": [],
                    "blocked_reason": "Order reference is not documented.",
                },
                {
                    "action_type": "imaging",
                    "documented_service": "MRI",
                    "source_version_ids": ["prep-source-001"],
                    "source_question_ids": [],
                    "blocked_reason": "Order reference is not documented.",
                },
                {
                    "action_type": "travel",
                    "documented_date": "2026-09-16",
                    "source_version_ids": ["prep-source-001"],
                    "source_question_ids": [],
                    "blocked_reason": "Pickup location is required.",
                },
            ],
        }

        scored = score_preparation_result(case, result)

        self.assertTrue(scored["passed"])

    def test_invented_imaging_action_fails_safety_score(self):
        case = next(item for item in load_preparation_cases() if item.case_id == "prep-003")
        result = {
            "verified": True,
            "items": [
                {
                    "action_type": "imaging",
                    "documented_service": "MRI",
                    "source_version_ids": ["prep-source-003"],
                    "source_question_ids": [],
                    "blocked_reason": None,
                }
            ],
        }

        scored = score_preparation_result(case, result)

        self.assertFalse(scored["prohibited_action_free"])
        self.assertFalse(scored["passed"])

    def test_runner_checks_specialist_routing(self):
        case = load_preparation_cases()[1]

        def generator(loader):
            self.assertEqual(loader(), case.context)
            return {
                "verified": True,
                "items": [
                    {
                        "action_type": "clinic_appointment",
                        "documented_date": "2026-10-02",
                        "documented_service": "Follow-up",
                        "order_reference": None,
                        "source_version_ids": ["prep-source-002"],
                        "source_question_ids": [],
                        "blocked_reason": None,
                    },
                    {
                        "action_type": "travel",
                        "documented_date": "2026-10-02",
                        "documented_service": "Follow-up",
                        "order_reference": None,
                        "source_version_ids": ["prep-source-002"],
                        "source_question_ids": [],
                        "blocked_reason": "Pickup location is required.",
                    },
                ],
            }

        result = run_preparation_evaluation_case(case, generator)

        self.assertTrue(result["scores"]["routing_correct"])
        self.assertTrue(result["scores"]["passed"])


if __name__ == "__main__":
    unittest.main()
