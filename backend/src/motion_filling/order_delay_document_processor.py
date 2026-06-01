"""
Order Delay Document Processor

Handles processing of an uploaded Motion to Delay PDF/DOCX when Schedule D
creditor data cannot be found automatically. Extracts text from the document,
stores it temporarily in Redis, and uses Claude to generate WhyExtensionNeeded
chip suggestions from the document content.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import redis
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain.chat_models import init_chat_model

from ..ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER
from ..config import settings
from ..tasks.redis_client import make_sync_redis


ORDER_DELAY_DOC_PREFIX = "order_delay_doc:"
ORDER_DELAY_DOC_TTL = 3600  # 1 hour


_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = make_sync_redis()
    return _redis_client


def _redis_key(session_id: str, task_id: str) -> str:
    return f"{ORDER_DELAY_DOC_PREFIX}{session_id}:{task_id}"


# -------------------- text extraction --------------------

def extract_text_from_file(file_path: str, filename: str) -> str:
    """
    Extract raw text from a PDF or DOCX file.

    Args:
        file_path: Absolute path to the file.
        filename:  Original filename (used to determine type by extension).

    Returns:
        Extracted text string, or "" on failure.
    """
    ext = Path(file_path).suffix.lower()
    try:
        if ext == ".pdf":
            loader = PyPDFLoader(file_path)
            documents = loader.load()
            return "\n\n".join(doc.page_content for doc in documents)
        elif ext in (".docx", ".doc"):
            loader = Docx2txtLoader(file_path)
            documents = loader.load()
            return "\n\n".join(doc.page_content for doc in documents)
        else:
            print(f"[order_delay_processor] Unsupported file type: {ext}")
            return ""
    except Exception as e:
        print(f"[order_delay_processor] extract_text_from_file error ({filename}): {e}")
        return ""


# -------------------- Redis storage --------------------

def store_doc_in_redis(session_id: str, task_id: str, content: str) -> bool:
    """
    Store extracted document text in Redis.

    Key:  order_delay_doc:{session_id}:{task_id}
    TTL:  ORDER_DELAY_DOC_TTL seconds (1 hour)

    Returns True if stored successfully.
    """
    try:
        r = _get_redis()
        r.setex(_redis_key(session_id, task_id), ORDER_DELAY_DOC_TTL, content)
        return True
    except Exception as e:
        print(f"[order_delay_processor] store_doc_in_redis error: {e}")
        return False


def retrieve_doc_from_redis(session_id: str, task_id: str) -> Optional[str]:
    """
    Retrieve extracted document text from Redis.

    Returns the text string, or None if the key is not found / has expired.
    """
    try:
        r = _get_redis()
        return r.get(_redis_key(session_id, task_id))
    except Exception as e:
        print(f"[order_delay_processor] retrieve_doc_from_redis error: {e}")
        return None


def cleanup_doc(session_id: str, task_id: str) -> bool:
    """
    Delete the Redis key after document generation completes.

    Returns True if deleted successfully (or key did not exist).
    """
    try:
        r = _get_redis()
        r.delete(_redis_key(session_id, task_id))
        return True
    except Exception as e:
        print(f"[order_delay_processor] cleanup_doc error: {e}")
        return False


# -------------------- main processor --------------------

def process_order_delay_motion_doc(
    file_paths: list[tuple[str, str]],
    session_id: str,
    task_id: str,
) -> dict:
    """
    Extract text from uploaded Motion to Delay file(s) and store in Redis.

    Args:
        file_paths: List of (abs_file_path, original_filename) tuples.
                    Typically contains exactly 1 file.
        session_id: Session identifier.
        task_id:    Task identifier.

    Returns:
        {'success': bool, 'processed_count': int, 'errors': list | None}
    """
    errors = []
    all_text_parts: list[str] = []

    for file_path, filename in file_paths:
        text = extract_text_from_file(file_path, filename)
        if text:
            all_text_parts.append(f"--- {filename} ---\n{text}")
        else:
            errors.append({"filename": filename, "error": "No text could be extracted"})

    combined_text = "\n\n".join(all_text_parts)

    if combined_text:
        store_doc_in_redis(session_id, task_id, combined_text)

    return {
        "success": len(errors) == 0 and bool(combined_text),
        "processed_count": len(all_text_parts),
        "errors": errors if errors else None,
    }


# -------------------- chip generation --------------------

def generate_chips_from_uploaded_doc(
    doc_content: str,
    motion_payload: dict,
) -> list[str]:
    """
    Use Claude to generate up to 3 WhyExtensionNeeded chip suggestions from the
    text of an uploaded Motion to Delay document.

    The suggestions follow the same format as generate_extension_explanation_suggestions()
    in fill_motion_order_delay.py so the frontend chip component works identically.

    Returns a list of up to 3 strings, or [] if no relevant data is found or on any error.
    """
    if not doc_content or not doc_content.strip():
        print("[order_delay_processor] generate_chips_from_uploaded_doc — empty doc_content")
        return []

    try:
        debtor_name = (motion_payload or {}).get("DebtorName", "")
        debtor_ref = debtor_name if debtor_name and debtor_name != "N/A" else "[Debtor Name]"

        model = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.2,
        )

        prompt = (
            "You are extracting secured creditor and collateral information from a Motion to Delay "
            "document filed in a bankruptcy case.\n\n"
            "The document may contain references to:\n"
            "  - Secured creditor names (lenders, banks, finance companies)\n"
            "  - Collateral descriptions: vehicles (Year Make Model + VIN#) or real property (address)\n"
            "  - Reaffirmation agreements\n\n"
            "IMPORTANT: Each creditor name belongs ONLY to its own collateral entry. "
            "Do not mix creditor names across different entries.\n\n"
            "Task:\n"
            "1. Find EVERY secured creditor + collateral pair mentioned in the document.\n"
            "   Deduplication: if two entries share the same property address OR the same VIN, "
            "keep only one.\n"
            "2. For each unique creditor+asset pair extract:\n"
            "   - Vehicle: Year, Make, Model, VIN#\n"
            "   - Real property: street address + city + state + zip only (no legal descriptions)\n"
            "3. Write sentences that ALWAYS combine ALL unique pairs into a single sentence per style. "
            "No period at the end of any sentence. No separate per-pair sentences.\n"
            "   Produce exactly 3 sentence styles, each chaining ALL pairs together:\n\n"
            "   Style 1 — 'directs' (use 'and directs' to join additional pairs):\n"
            f'      "Debtor, {debtor_ref}, directs NR/SMS/CAL (Creditor) to file a Reaffirmation '
            "Agreement for the Debtor's property located at 10646 North Lago Vista Circle, Parkland, FL 33076, "
            "and directs USAA FSB (Creditor) to file a Reaffirmation Agreement for the Debtor's vehicle, "
            'a 2023 Tesla Model Y, VIN #7SAYGAEE3PF674540\"\n\n'
            "   Style 2 — 'requests that' (use 'and that' to join additional pairs):\n"
            f'      "Debtor {debtor_ref} requests that NR/SMS/CAL (Creditor) file a Reaffirmation '
            "Agreement for the property at 10646 North Lago Vista Circle, Parkland, FL 33076, "
            "and that USAA FSB (Creditor) file a Reaffirmation Agreement for the Debtor's vehicle, "
            'a 2023 Tesla Model Y (VIN #7SAYGAEE3PF674540)\"\n\n'
            "   Style 3 — chaining (use 'and' to join additional pairs):\n"
            f'      "Debtor, {debtor_ref}, NR/SMS/CAL (Creditor) to file the Reaffirmation '
            "Agreement for the Debtor's Property at 10646 North Lago Vista Circle, Parkland, FL 33076, "
            "and USAA FSB (Creditor) to file the Reaffirmation Agreement for the Debtor's "
            'Vehicle, 2023 Tesla Model Y with Vin# 7SAYGAEE3PF674540 (Vehicle)\"\n\n'
            "   If only 1 pair found, write the same 3 styles but for that single pair only (no joining needed).\n"
            "4. Return exactly 3 strings in a JSON array. "
            "If no secured creditor / collateral data is found in the document, return [].\n"
            "Return ONLY a valid JSON array of strings, nothing else.\n\n"
            f"Motion to Delay document content:\n{doc_content}"
        )

        print(f"[order_delay_processor] Invoking Claude to generate chips "
              f"(doc_content length={len(doc_content)} chars)...")
        response = model.invoke(prompt)
        result = (response.content or "").strip()
        print(f"[order_delay_processor] Claude raw response: {result[:300]!r}")

        match = re.search(r"\[.*\]", result, re.DOTALL)
        if match:
            suggestions = json.loads(match.group())
            if isinstance(suggestions, list) and all(isinstance(s, str) for s in suggestions):
                print(f"[order_delay_processor] Parsed {len(suggestions)} chip(s)")
                return suggestions[:3]

        print("[order_delay_processor] WARNING: Could not parse chips from Claude response")
        return []

    except Exception as e:
        print(f"[order_delay_processor] generate_chips_from_uploaded_doc error: {e}")
        return []
