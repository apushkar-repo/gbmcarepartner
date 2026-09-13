"""Versioned, synthetic evaluation runner for the grounded-answer workflow."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import types
from typing import Any

from .answering import answer_question


DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "grounded_answer_v1.jsonl"
)
TOKEN = re.compile(r"[a-z0-9]+")
STOP_WORDS = {
    "a", "an", "and", "are", "be", "do", "for", "i", "is", "it", "my",
    "of", "should", "the", "to", "what", "when", "will",
}


class EvaluationUnavailable(RuntimeError):
    """The requested evaluation configuration cannot run."""


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    dataset_version: str
    title: str
    question: str
    expected_behavior: str
    reference_answer: str
    reference_context_ids: list[str]
    tags: list[str]
    documents: list[dict[str, Any]]


def load_cases(path: Path = DATASET_PATH) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cases.append(EvaluationCase(**json.loads(line)))
    if not cases:
        raise EvaluationUnavailable("The evaluation dataset is empty.")
    versions = {case.dataset_version for case in cases}
    if len(versions) != 1:
        raise EvaluationUnavailable("The evaluation dataset mixes versions.")
    return cases


def _terms(text: str) -> list[str]:
    return [term for term in TOKEN.findall(text.lower()) if term not in STOP_WORDS]


def retrieve_fixture(case: EvaluationCase, limit: int = 5) -> dict[str, Any]:
    """Rank only the current synthetic case's approved fixture documents."""
    query = Counter(_terms(case.question))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for document in case.documents:
        content = Counter(_terms(document["content"]))
        score = sum(min(count, content.get(term, 0)) for term, count in query.items())
        if score:
            ranked.append((float(score), {**document, "score": float(score)}))
    ranked.sort(key=lambda item: (-item[0], item[1]["version_id"]))
    return {"results": [item[1] for item in ranked[:limit]], "retrieval_mode": "fixture_bm25"}


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def deterministic_scores(
    case: EvaluationCase,
    result: dict[str, Any],
    retrieved_ids: list[str],
) -> dict[str, float | bool]:
    expected = set(case.reference_context_ids)
    retrieved = set(retrieved_ids)
    cited = {item["version_id"] for item in result.get("citations", [])}
    expected_abstention = case.expected_behavior == "abstain"
    behavior_correct = bool(result.get("abstained")) == expected_abstention
    citation_precision = _ratio(len(cited & expected), len(cited))
    citation_recall = _ratio(len(cited & expected), len(expected))
    retrieval_recall = _ratio(len(retrieved & expected), len(expected))
    passed = (
        behavior_correct
        and retrieval_recall == 1.0
        and (expected_abstention or (citation_precision == 1.0 and citation_recall == 1.0))
    )
    return {
        "behavior_correct": behavior_correct,
        "retrieval_recall_at_5": retrieval_recall,
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "passed": passed,
    }


def ragas_scores(
    case: EvaluationCase,
    result: dict[str, Any],
    retrieved_contexts: list[str],
) -> dict[str, float | None]:
    """Run current RAGAS collection metrics without exposing the gold to the app model."""
    if result.get("abstained"):
        return {"faithfulness": None, "context_recall": None, "context_precision": None}
    if not os.getenv("OPENAI_API_KEY"):
        raise EvaluationUnavailable("OPENAI_API_KEY is required for RAGAS scoring.")
    try:
        # RAGAS 0.4.3 still imports the legacy VertexAI adapter eagerly. Current
        # langchain-community releases removed that module. CareBridge does not use
        # VertexAI, so provide the type placeholder RAGAS needs for its capability
        # check without adding an unused Google provider dependency.
        try:
            import langchain_community.chat_models.vertexai  # type: ignore[import-not-found]  # noqa: F401
        except ModuleNotFoundError:
            from langchain_core.language_models import BaseChatModel

            legacy_vertex = types.ModuleType("langchain_community.chat_models.vertexai")
            legacy_vertex.ChatVertexAI = BaseChatModel
            sys.modules[legacy_vertex.__name__] = legacy_vertex

        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness
    except ImportError as exc:
        raise EvaluationUnavailable(
            "RAGAS is not installed. Install the backend requirements and restart the API."
        ) from exc

    try:
        model = os.getenv("RAGAS_EVALUATOR_MODEL", "gpt-4o-mini")
        evaluator = llm_factory(
            model, client=AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
        )
        values: dict[str, float | None] = {}
        metric_inputs = {
            "user_input": case.question,
            "response": result["answer"],
            "retrieved_contexts": retrieved_contexts,
            "reference": case.reference_answer,
        }
        for name, metric in (
            ("faithfulness", Faithfulness(llm=evaluator)),
            ("context_recall", ContextRecall(llm=evaluator)),
            ("context_precision", ContextPrecision(llm=evaluator)),
        ):
            scored = metric.score(**metric_inputs)
            values[name] = round(float(scored.value), 4)
        return values
    except Exception as exc:
        raise EvaluationUnavailable("RAGAS scoring could not be completed.") from exc


def run_evaluation_case(
    case: EvaluationCase,
    include_ragas: bool = False,
    answerer: Callable[[str, Callable[[str], dict[str, Any]]], dict[str, Any]] = answer_question,
    semantic_scorer: Callable[[EvaluationCase, dict[str, Any], list[str]], dict[str, Any]] = ragas_scores,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def retriever(_: str) -> dict[str, Any]:
        captured.update(retrieve_fixture(case))
        return captured

    result = answerer(case.question, retriever)
    evidence = captured.get("results", [])
    scores: dict[str, Any] = deterministic_scores(
        case, result, [item["version_id"] for item in evidence]
    )
    if include_ragas:
        scores.update(semantic_scorer(case, result, [item["content"] for item in evidence]))
    return {
        "case_id": case.case_id,
        "title": case.title,
        "expected_behavior": case.expected_behavior,
        "actual_behavior": "abstain" if result.get("abstained") else "answer",
        "question": case.question,
        "reference_answer": case.reference_answer,
        "answer": result.get("answer", ""),
        "retrieved_context_ids": [item["version_id"] for item in evidence],
        "reference_context_ids": case.reference_context_ids,
        "cited_context_ids": [item["version_id"] for item in result.get("citations", [])],
        "scores": scores,
        "tags": case.tags,
    }
