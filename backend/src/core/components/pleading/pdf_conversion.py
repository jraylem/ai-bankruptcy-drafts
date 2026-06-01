"""DOCX → PDF conversion for the v2 pleading download flow.

Wraps the legacy `convert_to_pdf_libreoffice` subprocess helper so we can
call it from async code without blocking the event loop. The legacy helper
already serializes concurrent LibreOffice invocations via a module-level
`threading.Lock`, so this wrapper does not add additional locking.

Tier 1 of the PDF download feature: lazy conversion on each request, no
caching. A future tier will cache the PDF bytes back to R2 keyed on the
log row so repeat downloads are instant.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from src.motion_filling.pdf_utils import convert_to_pdf_libreoffice

logger = logging.getLogger(__name__)


async def convert_docx_bytes_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    """Convert in-memory docx bytes to in-memory pdf bytes via LibreOffice.

    Runs the synchronous subprocess on a worker thread so the event loop
    stays responsive during the ~3-5s conversion. Raises RuntimeError if
    LibreOffice is unavailable, the subprocess fails, or the output is empty.
    """
    return await asyncio.to_thread(_convert_sync, docx_bytes)


def _convert_sync(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir: Path = Path(tmp_dir_str)
        docx_path: Path = tmp_dir / "input.docx"
        docx_path.write_bytes(docx_bytes)
        pdf_path: Path | None = convert_to_pdf_libreoffice(docx_path, tmp_dir)
        if pdf_path is None or not pdf_path.exists():
            raise RuntimeError("LibreOffice failed to produce a PDF from the docx bytes")
        return pdf_path.read_bytes()
