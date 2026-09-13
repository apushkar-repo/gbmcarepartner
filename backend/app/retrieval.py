"""Semantic retrieval adapters for approved visit-summary versions.

SQLite remains the authoritative source for summary text. Pinecone stores only
embeddings and identifiers, so API results are hydrated from SQLite.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import os


class SemanticUnavailable(RuntimeError):
    """Semantic retrieval is not configured or cannot be reached."""


def semantic_configured() -> bool:
    return bool(
        os.getenv("OPENAI_API_KEY")
        and os.getenv("PINECONE_API_KEY")
        and (os.getenv("PINECONE_INDEX_HOST") or os.getenv("PINECONE_INDEX"))
    )


def chunk_text(text: str, size: int = 6_000, overlap: int = 500) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size must be positive and overlap smaller than size.")
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = end - overlap
    return chunks


def reciprocal_rank_fusion(
    rankings: Iterable[Sequence[str]], k: int = 60
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    sequence = 0
    for ranking in rankings:
        for rank, identifier in enumerate(ranking, start=1):
            if identifier not in first_seen:
                first_seen[identifier] = sequence
                sequence += 1
            scores[identifier] = scores.get(identifier, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], first_seen[item[0]]))


@dataclass(frozen=True)
class SemanticMatch:
    version_id: str
    score: float


class OpenAIEmbedder:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise SemanticUnavailable("OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise SemanticUnavailable("The OpenAI SDK is not installed.") from exc
        self._client = OpenAI(api_key=api_key)
        self._model = os.getenv(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        )
        dimensions = os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "").strip()
        try:
            self._dimensions = int(dimensions) if dimensions else None
        except ValueError as exc:
            raise SemanticUnavailable(
                "OPENAI_EMBEDDING_DIMENSIONS must be a positive integer."
            ) from exc
        if self._dimensions is not None and self._dimensions <= 0:
            raise SemanticUnavailable(
                "OPENAI_EMBEDDING_DIMENSIONS must be a positive integer."
            )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            request = {"model": self._model, "input": list(texts)}
            if self._dimensions is not None:
                request["dimensions"] = self._dimensions
            response = self._client.embeddings.create(**request)
        except Exception as exc:
            raise SemanticUnavailable("OpenAI embeddings are unavailable.") from exc
        ordered = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in ordered]


class PineconeSummaryIndex:
    def __init__(self) -> None:
        api_key = os.getenv("PINECONE_API_KEY")
        index_host = os.getenv("PINECONE_INDEX_HOST")
        index_name = os.getenv("PINECONE_INDEX")
        if not api_key or not (index_host or index_name):
            raise SemanticUnavailable("Pinecone is not configured.")
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise SemanticUnavailable("The Pinecone SDK is not installed.") from exc
        try:
            client = Pinecone(api_key=api_key)
            self._index = (
                client.Index(host=index_host)
                if index_host
                else client.Index(index_name)
            )
        except Exception as exc:
            raise SemanticUnavailable("The Pinecone index is unavailable.") from exc

    def upsert_version(
        self,
        *,
        patient_id: str,
        version_id: str,
        document_id: str,
        version: int,
        vectors: Sequence[Sequence[float]],
    ) -> None:
        records = [
            {
                "id": f"{version_id}:{chunk_number}",
                "values": list(vector),
                "metadata": {
                    "version_id": version_id,
                    "document_id": document_id,
                    "version": version,
                },
            }
            for chunk_number, vector in enumerate(vectors)
        ]
        if not records:
            return
        try:
            self._index.upsert(vectors=records, namespace=patient_id)
        except Exception as exc:
            raise SemanticUnavailable("Pinecone indexing is unavailable.") from exc

    def query_versions(
        self, *, patient_id: str, vector: Sequence[float], top_k: int = 10
    ) -> list[SemanticMatch]:
        try:
            response = self._index.query(
                namespace=patient_id,
                vector=list(vector),
                top_k=top_k,
                include_metadata=True,
            )
        except Exception as exc:
            raise SemanticUnavailable("Pinecone search is unavailable.") from exc

        best_by_version: dict[str, float] = {}
        for match in response.matches:
            metadata = match.metadata or {}
            version_id = metadata.get("version_id")
            if isinstance(version_id, str):
                best_by_version[version_id] = max(
                    float(match.score), best_by_version.get(version_id, float("-inf"))
                )
        return [
            SemanticMatch(version_id=identifier, score=score)
            for identifier, score in sorted(
                best_by_version.items(), key=lambda item: item[1], reverse=True
            )
        ]


def index_semantically(
    *, patient_id: str, version_id: str, document_id: str, version: int, text: str
) -> None:
    chunks = chunk_text(text)
    vectors = OpenAIEmbedder().embed(chunks)
    PineconeSummaryIndex().upsert_version(
        patient_id=patient_id,
        version_id=version_id,
        document_id=document_id,
        version=version,
        vectors=vectors,
    )


def search_semantically(patient_id: str, query: str) -> list[SemanticMatch]:
    vector = OpenAIEmbedder().embed([query])[0]
    return PineconeSummaryIndex().query_versions(
        patient_id=patient_id, vector=vector
    )
