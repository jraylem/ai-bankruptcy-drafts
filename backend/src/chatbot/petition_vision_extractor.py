import base64
from pathlib import Path
from typing import Optional

import anthropic

from ..config import settings


_VISION_MODEL = "claude-sonnet-4-6"

_PETITION_QUERY_SYSTEM_PROMPT = """You are answering questions about a U.S. bankruptcy petition PDF on behalf of an attorney's chat assistant.

The attached PDF includes the Voluntary Petition (Form 101), Statement of Financial Affairs (Form 107), Schedules (A/B–J), Means Test (122 series), and signature pages. Pure text extraction misses checkbox marks and filled-in form fields, so you must read the PDF visually.

When you answer:
- For yes/no checkbox fields, ALWAYS state both options and which is checked. Use ☑ for checked and ☐ for unchecked. Example: "Q9 SOFA — Lawsuits/court actions in last year: ☑ No  ☐ Yes (page 5)."
- Cite the page number whenever it's clear.
- If a field is blank or illegible, say so explicitly. Do NOT guess.
- Be concise. The attorney needs the answer, not a summary of the document.
- If the question is ambiguous (e.g. "did they answer yes?" without specifying which question), ask for clarification rather than guessing."""


def query_petition_pdf(file_path: str, query: str) -> Optional[str]:
    """Send the petition PDF to Claude with a query and return the answer text.

    Used by the `read_petition_pdf` chat tool. The PDF document block carries
    `cache_control: ephemeral` so subsequent queries against the same PDF
    within ~5 minutes hit the prompt cache (~0.1× input cost).

    Returns the answer text on success, None on failure. Failures are logged
    but never raised — the caller surfaces a friendly error to the agent.
    """
    pdf_path = Path(file_path)
    if not pdf_path.exists() or not pdf_path.is_file():
        print(f"⚠️ query_petition_pdf: file not found at {file_path}")
        return None

    try:
        with pdf_path.open("rb") as f:
            pdf_b64 = base64.standard_b64encode(f.read()).decode("utf-8")
    except Exception as e:
        print(f"⚠️ query_petition_pdf: failed to read {file_path}: {e}")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_VISION_MODEL,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=[{
                "type": "text",
                "text": _PETITION_QUERY_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": query,
                    },
                ],
            }],
        )
    except anthropic.APIError as e:
        print(f"⚠️ query_petition_pdf API error for {pdf_path.name}: {e}")
        return None
    except Exception as e:
        print(f"⚠️ query_petition_pdf unexpected error for {pdf_path.name}: {e}")
        return None

    answer = "".join(b.text for b in response.content if b.type == "text").strip()
    if not answer:
        print(f"⚠️ query_petition_pdf returned empty output for {pdf_path.name}")
        return None

    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
    print(
        f"✅ query_petition_pdf {pdf_path.name}: "
        f"input={response.usage.input_tokens}, output={response.usage.output_tokens}, "
        f"cache_read={cache_read}, cache_create={cache_create}"
    )
    return answer
