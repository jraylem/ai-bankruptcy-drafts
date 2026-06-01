"""
Case ingestion agent.

LLM call site that reads a bankruptcy petition PDF with Claude and returns
structured case metadata (case_number, case_name, chapter, court_district).
Peer of template/agent.py and draft/agent.py — uses the same LangChain
ChatAnthropic + with_structured_output pattern, with the PDF attached as a
document content block on a HumanMessage.
"""

import base64
import logging

from fastapi import HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.core.common.constants import CLAUDE_MODEL_STANDARD

from ..base import Agent
from .prompt_builder import _EXTRACTION_INSTRUCTION

logger = logging.getLogger(__name__)


class CaseMetadata(BaseModel):
    """Structured metadata extracted from a bankruptcy petition PDF."""
    case_number: str | None = Field(
        default=None,
        description=(
            "Case number exactly as it appears on the petition "
            "(e.g. '0:26-bk-10700', '26-bk-10700', or '26-10700'). "
            "Return null when the petition has NOT been filed yet — "
            "voluntary petitions in preparation often have no docket "
            "number assigned, in which case there will be no case-number "
            "line on the cover page. Do not guess or fabricate a number; "
            "null is the authoritative signal for 'unfiled' status."
        )
    )
    debtors: list[str] = Field(
        description=(
            "Ordered list of debtor names from the 'In re:' caption. "
            "For solo filings this is a single-element list "
            "(e.g. ['Judith Schwartz']). For joint filings (spouses / "
            "two debtors) it contains BOTH names in the order they appear "
            "on the petition (e.g. ['Lori Creswell', 'Robert Creswell']). "
            "Preserve punctuation on the last name if present (trailing "
            "comma from the source)."
        )
    )
    chapter: int | None = Field(
        default=None,
        description="Bankruptcy chapter (7, 11, 13, etc.) if visible on the petition.",
    )
    court_district: str | None = Field(
        default=None,
        description="Court district (e.g. 'S.D. Fla.') if visible on the petition.",
    )

    @property
    def case_name(self) -> str:
        """Canonical case_name derived from `debtors`.

        Solo filings → single name unchanged. Joint filings → names joined
        by a literal newline (`\\n`) so the docx engine can render them as
        soft line breaks in the caption placeholder. Downstream display
        surfaces (activity log / dashboard) flatten the newline to ' & '.
        """
        return "\n".join(self.debtors) if self.debtors else ""


class CaseIngestionAgent(Agent[CaseMetadata]):
    """Read a bankruptcy petition PDF and return structured case metadata (case_number, case_name, chapter, court_district)."""

    model = CLAUDE_MODEL_STANDARD
    output_type = CaseMetadata
    max_tokens = 1024
    tags = ["core", "agent", "case_ingestion"]
    cost_kind = "case_ingest"

    @classmethod
    async def run(cls, pdf_bytes: bytes, filename: str) -> CaseMetadata:
        """Read a petition PDF with Claude and return structured case metadata.

        Attaches the PDF inline (base64) as a document content block on a
        HumanMessage — no Files API because this is a one-shot read and the
        bytes are already in memory.
        """
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Empty PDF upload")

        pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

        message = HumanMessage(
            content=[
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {
                    "type": "text",
                    "text": _EXTRACTION_INSTRUCTION.format(filename=filename),
                },
            ]
        )

        try:
            result = await cls._invoke(
                [message],
                run_name="CaseIngestionAgent",
                metadata={"filename": filename},
            )
        except Exception as e:
            logger.error(f"Case ingestion agent LLM error: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"Case metadata extraction failed: {e}",
            )

        if result is None:
            raise HTTPException(
                status_code=422,
                detail="Could not extract case metadata from PDF (empty LLM result)",
            )

        return result
