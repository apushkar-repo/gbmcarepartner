import unittest

from app.retrieval import OpenAIEmbedder, chunk_text, reciprocal_rank_fusion


class ChunkTextTests(unittest.TestCase):
    def test_chunks_overlap_without_dropping_the_end(self):
        chunks = chunk_text("abcdefghij", size=6, overlap=2)

        self.assertEqual(chunks, ["abcdef", "efghij"])

    def test_empty_text_has_no_chunks(self):
        self.assertEqual(chunk_text("   "), [])

    def test_configured_dimensions_are_sent_to_embedding_provider(self):
        captured = {}

        class Embeddings:
            def create(self, **request):
                captured.update(request)
                item = type("Embedding", (), {"index": 0, "embedding": [0.1, 0.2]})()
                return type("Response", (), {"data": [item]})()

        embedder = OpenAIEmbedder.__new__(OpenAIEmbedder)
        embedder._client = type("Client", (), {"embeddings": Embeddings()})()
        embedder._model = "text-embedding-3-small"
        embedder._dimensions = 1024

        embedder.embed(["summary"])

        self.assertEqual(captured["dimensions"], 1024)


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_item_found_by_both_retrievers_ranks_first(self):
        ranked = reciprocal_rank_fusion(
            [["lexical-first", "shared"], ["shared", "semantic-second"]]
        )

        self.assertEqual(ranked[0][0], "shared")

    def test_ties_preserve_first_seen_order(self):
        ranked = reciprocal_rank_fusion([["a"], ["b"]])

        self.assertEqual([identifier for identifier, _ in ranked], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
