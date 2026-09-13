import unittest

from app.answering import (
    ABSTENTION,
    GroundedDraft,
    VerificationResult,
    build_answer_graph,
)


EVIDENCE = {
    "version_id": "version-1",
    "document_id": "document-1",
    "filename": "visit.png",
    "version": 1,
    "content": "Bring your medication list to the next visit.",
}


class FakeModel:
    def __init__(self, draft: GroundedDraft, supported: bool = True):
        self.proposed = draft
        self.supported = supported
        self.draft_calls = 0
        self.verify_calls = 0
        self.verified_evidence = []

    def draft(self, question, evidence):
        self.draft_calls += 1
        return self.proposed

    def verify(self, question, draft, evidence):
        self.verify_calls += 1
        self.verified_evidence = evidence
        return VerificationResult(supported=self.supported)


def retriever_with(evidence):
    return lambda _: {"results": evidence, "retrieval_mode": "hybrid"}


class AnswerGraphTests(unittest.TestCase):
    def test_no_evidence_abstains_without_calling_model(self):
        model = FakeModel(
            GroundedDraft(answer="unused", cited_version_ids=[], sufficient_evidence=False)
        )

        result = build_answer_graph(retriever_with([]), model).invoke(
            {"question": "What should I bring?"}
        )

        self.assertTrue(result["abstained"])
        self.assertEqual(result["answer"], ABSTENTION)
        self.assertEqual(model.draft_calls, 0)
        self.assertEqual(model.verify_calls, 0)

    def test_supported_answer_preserves_valid_citation(self):
        model = FakeModel(
            GroundedDraft(
                answer="Bring your medication list.",
                cited_version_ids=["version-1"],
                sufficient_evidence=True,
            )
        )

        result = build_answer_graph(retriever_with([EVIDENCE]), model).invoke(
            {"question": "What should I bring?"}
        )

        self.assertFalse(result["abstained"])
        self.assertEqual(result["cited_version_ids"], ["version-1"])
        self.assertEqual(model.verified_evidence, [EVIDENCE])

    def test_unknown_citation_abstains_before_verification(self):
        model = FakeModel(
            GroundedDraft(
                answer="Bring a scan.",
                cited_version_ids=["invented-version"],
                sufficient_evidence=True,
            )
        )

        result = build_answer_graph(retriever_with([EVIDENCE]), model).invoke(
            {"question": "What should I bring?"}
        )

        self.assertTrue(result["abstained"])
        self.assertEqual(model.verify_calls, 0)

    def test_failed_support_check_replaces_draft_with_abstention(self):
        model = FakeModel(
            GroundedDraft(
                answer="Change your medication.",
                cited_version_ids=["version-1"],
                sufficient_evidence=True,
            ),
            supported=False,
        )

        result = build_answer_graph(retriever_with([EVIDENCE]), model).invoke(
            {"question": "Should I change my medication?"}
        )

        self.assertTrue(result["abstained"])
        self.assertEqual(result["answer"], ABSTENTION)


if __name__ == "__main__":
    unittest.main()
