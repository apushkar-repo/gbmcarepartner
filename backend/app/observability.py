"""Privacy-preserving LangSmith instrumentation for CareBridge workflows."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
import os
from typing import Any, Iterator


logger = logging.getLogger(__name__)

_SAFE_METADATA_KEYS = {
    "actor_role",
    "content_type",
    "file_size_bytes",
    "input_count",
    "item_count",
    "model",
    "page_count",
    "provider",
    "result_count",
    "retrieval_mode",
    "scoped_to_visit",
    "status",
    "stop_reason",
    "workflow_run_id",
}


def tracing_enabled() -> bool:
    return (
        os.getenv("LANGSMITH_TRACING", "").strip().lower() == "true"
        and bool(os.getenv("LANGSMITH_API_KEY", "").strip())
    )


def _safe_values(values: dict[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    return {
        key: value
        for key, value in values.items()
        if key in _SAFE_METADATA_KEYS
        and (value is None or isinstance(value, (str, int, float, bool)))
    }


@dataclass
class TraceSpan:
    run: Any = None

    def record(self, **values: Any) -> None:
        if self.run is None:
            return
        try:
            self.run.add_outputs(_safe_values(values))
        except Exception:
            logger.warning("LangSmith output metadata could not be recorded.", exc_info=True)


@contextmanager
def carebridge_trace(
    name: str,
    *,
    run_type: str = "chain",
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> Iterator[TraceSpan]:
    """Create a trace with redacted I/O and allow the application to continue offline."""

    if not tracing_enabled():
        yield TraceSpan()
        return

    manager = None
    try:
        from langsmith import trace

        manager = trace(
            name,
            run_type=run_type,
            inputs={"content_redacted": True},
            project_name=os.getenv("LANGSMITH_PROJECT", "carebridge-development"),
            tags=["carebridge", *(tags or [])],
            metadata={"content_redacted": True, **_safe_values(metadata)},
        )
        run = manager.__enter__()
    except Exception:
        logger.warning("LangSmith trace could not be started.", exc_info=True)
        yield TraceSpan()
        return

    try:
        yield TraceSpan(run)
    except BaseException as exc:
        try:
            manager.__exit__(type(exc), exc, exc.__traceback__)
        except Exception:
            logger.warning("LangSmith trace could not record failure.", exc_info=True)
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception:
            logger.warning("LangSmith trace could not be completed.", exc_info=True)
