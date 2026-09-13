import sys
import types
import unittest
from unittest.mock import patch

from app.ocr import LlamaParseAdapter


class LlamaParseAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_high_accuracy_verbatim_transcription_configuration(self):
        captured = {}

        class FakeParser:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def load_data(self, _path):
                return [types.SimpleNamespace(text="Exact transcript")]

        fake_module = types.SimpleNamespace(LlamaParse=FakeParser)
        with patch.dict(sys.modules, {"llama_parse": fake_module}):
            result = await LlamaParseAdapter("test-key").parse(
                b"synthetic image", "visit.png"
            )

        self.assertEqual(result.text, "Exact transcript")
        self.assertEqual(captured["result_type"], "text")
        self.assertEqual(captured["tier"], "agentic_plus")
        self.assertEqual(captured["version"], "latest")
        self.assertTrue(captured["high_res_ocr"])
        self.assertIn("[unclear]", captured["user_prompt"])


if __name__ == "__main__":
    unittest.main()
