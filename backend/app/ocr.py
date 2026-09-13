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

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

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
            parser = LlamaParse(api_key=self.api_key, result_type="text", verbose=False)
            documents = await asyncio.to_thread(parser.load_data, str(temp))
            text = "\n\n".join(getattr(doc, "text", str(doc)) for doc in documents)
            return OcrResult(text=text, pages=len(documents), provider="llamaparse")
        finally:
            temp.unlink(missing_ok=True)
