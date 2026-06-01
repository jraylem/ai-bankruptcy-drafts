import re
import json
import time
from typing import Dict

from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE


# Called by: service.generate_payload_withdraw_from_hearing_for_session_gmail (L3A)
#   -> routes/order_stream.py
class GmailHearingExtractAgent:
    """
    Lightweight Claude Haiku agent for extracting specific fields from a
    pre-fetched email body.

    No vectorstore, no tools, no ReAct loop — just a single structured
    extraction call. Reusable for any motion type by passing a different
    fields dict (defined in prompts/hearing_extract.py).
    """

    def __init__(self):
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found. Check your .env file.")

        self.model = init_chat_model(
            CLAUDE_MODEL_FAST,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE,
            max_retries=5,
        )

    def extract(self, email_body: str, fields: Dict[str, str]) -> Dict[str, str]:
        """
        Extract specified fields from a plain-text email body.

        Args:
            email_body: Plain text content of the email.
            fields:     Dict of { field_name: extraction_instruction } — defined
                        in prompts/hearing_extract.py per motion type.

        Returns:
            Dict of { field_name: extracted_value } — falls back to "N/A" for
            any field Haiku could not find or that failed to parse.
        """
        if not email_body or not fields:
            return {k: "N/A" for k in fields}

        field_lines = "\n".join(
            f'- "{name}": {instruction}'
            for name, instruction in fields.items()
        )

        prompt = (
            "You are a precise legal assistant extracting specific fields "
            "from a court notice email.\n\n"
            "Extract the following fields from the email body below and return "
            "ONLY a valid JSON object with these exact keys:\n"
            f"{field_lines}\n\n"
            "Return null for any field you cannot find. "
            "Return ONLY the JSON object, no explanation.\n\n"
            f"Email body:\n{email_body}"
        )

        max_attempts = 3
        raw = None
        for attempt in range(max_attempts):
            try:
                response = self.model.invoke(prompt)
                raw = response.content.strip()
                break
            except Exception as e:
                is_overloaded = "529" in str(e) or "overloaded" in str(e).lower()
                if is_overloaded and attempt < max_attempts - 1:
                    wait = 5 * (2 ** attempt)  # 5s, 10s
                    print(f"[warn] GmailHearingExtractAgent: API overloaded (attempt {attempt + 1}/{max_attempts}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                print(f"[error] GmailHearingExtractAgent: invoke failed after {attempt + 1} attempts: {e}")
                return {k: "N/A" for k in fields}

        if raw is None:
            return {k: "N/A" for k in fields}

        # Strip markdown code fence if the model wraps the JSON
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        try:
            result = json.loads(raw)
        except Exception:
            print(f"[warn] GmailHearingExtractAgent: could not parse JSON: {raw}")
            result = {}

        return {k: result.get(k) or "N/A" for k in fields}
