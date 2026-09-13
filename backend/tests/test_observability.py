import os
import sys
import types
import unittest
from unittest.mock import patch

from app.observability import carebridge_trace, tracing_enabled
from app import main


class FakeRun:
    def __init__(self):
        self.outputs = None

    def add_outputs(self, outputs):
        self.outputs = outputs


class FakeTraceManager:
    def __init__(self, run):
        self.run = run
        self.exited = None

    def __enter__(self):
        return self.run

    def __exit__(self, *args):
        self.exited = args


class ObservabilityTests(unittest.TestCase):
    @patch.dict(os.environ, {"LANGSMITH_TRACING": "false"}, clear=False)
    def test_tracing_is_disabled_without_configuration(self):
        self.assertFalse(tracing_enabled())
        with carebridge_trace("disabled") as span:
            span.record(status="completed")
        self.assertIsNone(span.run)

    @patch.dict(
        os.environ,
        {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "test-key",
            "LANGSMITH_PROJECT": "test-project",
        },
        clear=False,
    )
    def test_trace_keeps_only_approved_metadata(self):
        run = FakeRun()
        manager = FakeTraceManager(run)
        calls = []

        def fake_trace(name, **kwargs):
            calls.append((name, kwargs))
            return manager

        fake_module = types.SimpleNamespace(trace=fake_trace)
        with patch.dict(sys.modules, {"langsmith": fake_module}):
            with carebridge_trace(
                "carebridge.test",
                metadata={"actor_role": "patient", "patient_name": "Private"},
            ) as span:
                span.record(status="completed", result_count=2, answer="Private")

        self.assertEqual(calls[0][0], "carebridge.test")
        self.assertEqual(calls[0][1]["inputs"], {"content_redacted": True})
        self.assertNotIn("patient_name", calls[0][1]["metadata"])
        self.assertEqual(run.outputs, {"status": "completed", "result_count": 2})
        self.assertIsNotNone(manager.exited)

    @patch.dict(
        os.environ,
        {"LANGSMITH_TRACING": "false", "LANGSMITH_API_KEY": ""},
        clear=False,
    )
    def test_status_endpoint_is_clinician_only_and_does_not_expose_credentials(self):
        status = main.observability_status("clinician", "clinician-1")

        self.assertFalse(status["enabled"])
        self.assertEqual(status["provider"], "langsmith")
        self.assertNotIn("api_key", status)
        with self.assertRaises(main.HTTPException) as raised:
            main.observability_status("patient", "patient-1")
        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
