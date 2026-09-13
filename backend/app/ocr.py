from dataclasses import dataclass
from typing import Protocol
from pathlib import Path
import asyncio


@dataclass(frozen=True)
class OcrResult:
    text: str
    pages: int
    provider: str


class OcrAdapter(Protocol):
    async def parse(self, content: bytes, filename: str) -> OcrResult: ...


class OcrUnavailable(RuntimeError):
    """Raised when the configured OCR provider cannot be used."""


class LlamaParseAdapter:
    """LlamaParse adapter; importing the optional SDK only when called."""

    def __init__(
        self,
        api_key: str | None = None,
        tier: str = "agentic_plus",
        version: str = "latest",
    ):
        self.api_key = api_key
        self.tier = tier
        self.version = version

    async def parse(self, content: bytes, filename: str) -> OcrResult:
        if not self.api_key:
            raise OcrUnavailable("LlamaParse is not configured; upload remains queued.")
        try:
            from llama_parse import LlamaParse  # type: ignore
        except ImportError as exc:
            raise OcrUnavailable("Install llama-cloud-services to enable LlamaParse.") from exc
        temp = Path("/tmp") / f"carebridge-{filename}"
        temp.write_bytes(content)
        try:
            parser = LlamaParse(
                api_key=self.api_key,
                result_type="text",
                tier=self.tier,
                version=self.version,
                high_res_ocr=True,
                language="en",
                user_prompt=(
                    "Transcribe every visible word from this visit document verbatim in "
                    "natural reading order. Preserve headings, line breaks, dates, medication "
                    "names, doses, tests, and appointments. Do not summarize, correct, infer, "
                    "or add medical content. Write [unclear] for text that cannot be read "
                    "reliably. Return plain text without Markdown formatting."
                ),
                verbose=False,
            )
            documents = await asyncio.to_thread(parser.load_data, str(temp))
            text = "\n\n".join(getattr(doc, "text", str(doc)) for doc in documents)
            return OcrResult(text=text, pages=len(documents), provider="llamaparse")
        finally:
            temp.unlink(missing_ok=True)
