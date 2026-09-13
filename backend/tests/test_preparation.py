import unittest

from app.preparation import (
    EMPTY_MESSAGE,
    PreparationDraft,
    PreparationItem,
    PreparationVerification,
    build_preparation_graph,
)


CONTEXT = {
    "summaries": [
        {
            "version_id": "version-1",
            "filename": "visit.png",
            "version": 1,
            "content": "Bring your medication list to the next visit.",
        }
    ],
    "questions": [
        {
            "question_id": "question-1",
            "text": "What time is the visit?",
            "status": "open",
            "clinician_response": None,
        }
    ],
}


class FakeModel:
    def __init__(self, item: PreparationItem, supported: bool = True):
        self.item = item
        self.supported = supported
        self.draft_calls = 0
        self.verify_calls = 0

    def draft(self, context):
        self.draft_calls += 1
        return PreparationDraft(summary="Prepare for the visit", items=[self.item])

    def verify(self, draft, context):
        self.verify_calls += 1
        return PreparationVerification(
            supported=self.supported,
            reason="The item is unsupported." if not self.supported else "",
        )


def document_item(version_id="version-1"):
    return PreparationItem(
        title="Bring your medication list",
        description="Bring the current list to the visit.",
        origin_type="document_instruction",
        source_version_ids=[version_id],
    )


class PreparationGraphTests(unittest.TestCase):
    def test_explicit_lab_and_appointment_are_prioritized_and_travel_is_offered(self):
        context = {
            "summaries": [
                {
                    "version_id": "version-visit",
                    "filename": "visit.png",
                    "version": 1,
                    "content": (
                        "Recommendations / next steps:\n"
                        "- Run a full blood work CBC RFT for the next follow-up\n"
                        "Next appointment:\n"
                        "October 8, 2026 at 10:00 AM\n"
                        "Neuro-Oncology Clinic"
                    ),
                }
            ],
            "questions": [],
        }
        generic = PreparationItem(
            title="Prepare questions",
            description="Write down questions for the next visit.",
            origin_type="document_instruction",
            source_version_ids=["version-visit"],
        )

        result = build_preparation_graph(lambda: context, FakeModel(generic)).invoke({})

        actions = {item["action_type"]: item for item in result["items"]}
        self.assertEqual(actions["clinic_appointment"]["documented_date"], "2026-10-08")
        self.assertIn("blood work", actions["laboratory"]["documented_service"].lower())
        self.assertEqual(actions["travel"]["origin_type"], "app_suggestion")
        self.assertIsNotNone(actions["travel"]["blocked_reason"])

    def test_no_context_returns_empty_plan_without_model_call(self):
        model = FakeModel(document_item())

        result = build_preparation_graph(
            lambda: {"summaries": [], "questions": []}, model
        ).invoke({})

        self.assertEqual(result["items"], [])
        self.assertEqual(result["message"], EMPTY_MESSAGE)
        self.assertEqual(model.draft_calls, 0)

    def test_valid_cited_item_is_returned_after_verification(self):
        model = FakeModel(document_item())

        result = build_preparation_graph(lambda: CONTEXT, model).invoke({})

        self.assertTrue(result["verified"])
        self.assertEqual(result["items"][0]["source_version_ids"], ["version-1"])
        self.assertEqual(model.verify_calls, 1)

    def test_explicit_imaging_action_preserves_evidence_and_booking_fields(self):
        item = PreparationItem(
            title="Arrange MRI",
            description="Arrange the MRI documented for the next visit.",
            origin_type="document_instruction",
            source_version_ids=["version-1"],
            blocked_reason="The approved summary does not include an order reference.",
            action_type="imaging",
            documented_date="2026-09-16",
            documented_service="MRI",
        )

        result = build_preparation_graph(lambda: CONTEXT, FakeModel(item)).invoke({})

        self.assertTrue(result["verified"])
        self.assertEqual(result["items"][0]["action_type"], "imaging")
        self.assertEqual(result["items"][0]["documented_service"], "MRI")

    def test_unknown_source_is_rejected_before_verification(self):
        model = FakeModel(document_item("invented-version"))

        result = build_preparation_graph(lambda: CONTEXT, model).invoke({})

        self.assertFalse(result["verified"])
        self.assertEqual(result["items"], [])
        self.assertEqual(model.verify_calls, 0)

    def test_failed_safety_verification_rejects_the_entire_plan(self):
        model = FakeModel(document_item(), supported=False)

        result = build_preparation_graph(lambda: CONTEXT, model).invoke({})

        self.assertFalse(result["verified"])
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
