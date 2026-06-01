from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import motion_objection_sustain_no_upload_gmail_tool
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_OBJECTION_SUSTAIN_NO_UPLOAD_GMAIL,
    INDIVIDUAL_FIELD_PROMPTS_OBJECTION_SUSTAIN_GMAIL,
)


# Called by: service/order_sustaining_objection.py → generate_payload_objection_sustain_no_upload_for_session_gmail
#   -> tasks/extractors.py
class GmailMotionObjectionSustainNoUploadAgent:
    """
    Claude-backed Order Sustaining Objection Agent (No Upload).

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_objection_sustain, case_number_objection_sustain
    - Gmail vectorstore (gmail_<session_id>) for:
      chapter_number_objection_sustain, judge_initial_objection_sustain,
      case_number_objection_sustain_gmail (fallback)
    """

    def __init__(self, session_id: Optional[str] = None, memory_saver: MemorySaver = None):
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.session_id = session_id
        self.memory_saver = memory_saver or MemorySaver()

        self.llm = init_chat_model(
            CLAUDE_MODEL_FAST,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE,
        )

        # Petition-based fields
        self.pdf_fields = [
            "debtor_name_objection_sustain",
            "case_number_objection_sustain",
        ]
        # Gmail-based fields
        self.gmail_fields = [
            "chapter_number_objection_sustain",
            "judge_initial_objection_sustain",
        ]

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "debtor_name_objection_sustain":         "Your full name Debtor 1",
            "case_number_objection_sustain":         "Case number if known",
            "chapter_number_objection_sustain":      "chapter case details",
            "judge_initial_objection_sustain":       "Judge",
            "case_number_objection_sustain_gmail":   "Case number with judge initial from emails",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = motion_objection_sustain_no_upload_gmail_tool(session_id=self.session_id)
                field_tool = None

                for tool in tools:
                    if tool.name == f"extract_{field_name}":
                        field_tool = tool
                        break

                if not field_tool:
                    return f"Tool for {field_name} not found"

                agent_executor = create_react_agent(
                    tools=[field_tool],
                    model=self.llm,
                    prompt=INDIVIDUAL_FIELD_PROMPTS_OBJECTION_SUSTAIN_NO_UPLOAD_GMAIL[field_name],
                )

                response = agent_executor.invoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Return ONLY the extracted value for: {field_name}. Query: {query}. No explanation. No summaries. No markdown. Return only the value(s) or N/A.",
                            }
                        ]
                    },
                    config={
                        "configurable": {
                            "thread_id": f"{self.session_id}_{field_name}_{attempt}"
                        },
                        "recursion_limit": 50,
                    },
                )

                ai_response = ""
                if "messages" in response:
                    ai_messages = []
                    for message in response["messages"]:
                        if hasattr(message, "content") and hasattr(message, "__class__"):
                            if "AIMessage" in str(message.__class__):
                                ai_messages.append(message.content)
                    if ai_messages:
                        ai_response = ai_messages[-1].strip()

                if ai_response and ai_response != "N/A":
                    return ai_response
                elif attempt < max_retries:
                    print(f"  Retrying {field_name} (attempt {attempt + 1})...")
                    continue
                else:
                    return "N/A"

            except Exception as e:
                if "recursion limit" in str(e).lower() and attempt < max_retries:
                    print(
                        f"  Recursion error for {field_name}, retrying with different approach..."
                    )
                    query = f"{field_name}"
                    continue
                else:
                    print(f"Error extracting {field_name}: {str(e)}")
                    if attempt < max_retries:
                        continue
                    return "N/A"

        return "N/A"

    def extract_payload(self, user_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract order sustaining objection payload using Gmail + petition vectorstores (no upload).
        """
        try:
            print("Starting Claude-backed sequential field extraction for order sustaining objection (no upload)...")

            pdf_results: Dict[str, str] = {}
            print("Extracting petition (PDF) fields...")
            for field in self.pdf_fields:
                print(f"  Extracting {field}...")
                query = self._get_optimized_query(field, user_hint)
                result = self._extract_single_field(field, query)
                pdf_results[field] = result
                print(f"    {field}: {result}")

            gmail_results: Dict[str, str] = {}
            print("Extracting Gmail-backed fields...")
            for field in self.gmail_fields:
                print(f"  Extracting {field}...")
                query = self._get_optimized_query(field, user_hint)
                result = self._extract_single_field(field, query)
                gmail_results[field] = result
                print(f"    {field}: {result}")

            # Combine judge initial (from Gmail) with base case number (from PDF)
            judge_initial = gmail_results.get("judge_initial_objection_sustain", "N/A")
            case_number = pdf_results.get("case_number_objection_sustain", "N/A")

            combined_case_number = case_number
            if judge_initial != "N/A" and judge_initial and case_number != "N/A" and case_number:
                combined_case_number = f"{case_number}-{judge_initial}"
            else:
                # Fallback: try to get the full case number (with judge initial) directly from Gmail
                print("  judge_initial_objection_sustain N/A from Gmail, falling back to full case number from Gmail...")
                gmail_case_number = self._extract_single_field(
                    "case_number_objection_sustain_gmail",
                    self._get_optimized_query("case_number_objection_sustain_gmail"),
                )
                print(f"    case_number_objection_sustain (Gmail full fallback): {gmail_case_number}")
                if gmail_case_number and gmail_case_number != "N/A":
                    combined_case_number = gmail_case_number

            final_payload = {
                "DebtorName": pdf_results.get("debtor_name_objection_sustain", "N/A"),
                "CaseNo":     combined_case_number,
                "Chapter":    gmail_results.get("chapter_number_objection_sustain", "N/A"),
            }

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Claude-backed order sustaining objection (no upload) payload: {final_payload}")
            print(
                f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)"
            )

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "claude_order_sustaining_objection_no_upload_agent_sequential",
                "field_results": extracted_fields,
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Claude Order sustaining objection (no upload) payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "claude_order_sustaining_objection_no_upload_agent_sequential",
            }


# Called by: service/order_sustaining_objection.py → generate_payload_objection_sustain_for_session_gmail
#   -> routes/stream.py, tasks/extractors.py → OrderSustainingObjectionExtractor
class GmailMotionObjectionSustainAgent:
    """
    Claude-backed Order Sustaining Objection Agent (With Upload).

    Only extracts SlotNumb and Creditor from the uploaded objection PDF
    (objection_pdf_<session_id>). All other fields come from the no-upload
    path (petition PDF + Gmail) in the service layer.
    """

    def __init__(self, session_id: Optional[str] = None, memory_saver: MemorySaver = None):
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.session_id = session_id
        self.memory_saver = memory_saver or MemorySaver()

        self.llm = init_chat_model(
            CLAUDE_MODEL_FAST,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE,
        )

    def extract_upload_fields(self, user_hint: Optional[str] = None) -> Dict[str, str]:
        """
        Extract only SlotNumb and Creditor from the uploaded objection PDF.

        Uses one direct LLM call per field with prompts from
        INDIVIDUAL_FIELD_PROMPTS_OBJECTION_SUSTAIN_GMAIL. Each prompt enforces
        a bare-value response (_STRICT), so no JSON parsing is needed.

        Returns a plain dict with keys 'SlotNumb' and 'Creditor'.
        """
        import time as _time
        from ...chatbot.vectorestore import search_vectorstore

        print("Extracting SlotNumb + Creditor from uploaded objection PDF (direct extraction)...")

        objection_collection = f"objection_pdf_{self.session_id}"
        docs = search_vectorstore(
            "objection to claim slot number creditor filed by",
            collection_name=objection_collection,
            k=15,
        )
        if not docs:
            print(f"  No documents found in {objection_collection}")
            return {"SlotNumb": "N/A", "Creditor": "N/A"}

        pdf_text = "\n\n".join(doc.page_content for doc in docs)

        field_map = {
            "slot_numb_objection_sustain": "SlotNumb",
            "creditor_objection_sustain":  "Creditor",
        }

        max_attempts = 3
        results: Dict[str, str] = {}

        for field_key, output_key in field_map.items():
            full_prompt = (
                INDIVIDUAL_FIELD_PROMPTS_OBJECTION_SUSTAIN_GMAIL[field_key]
                + f"\n\nPDF text:\n{pdf_text}"
            )
            raw = None
            for attempt in range(max_attempts):
                try:
                    response = self.llm.invoke(full_prompt)
                    raw = response.content.strip()
                    break
                except Exception as e:
                    is_overloaded = "529" in str(e) or "overloaded" in str(e).lower()
                    if is_overloaded and attempt < max_attempts - 1:
                        wait = 5 * (2 ** attempt)
                        print(f"[warn] extract_upload_fields: API overloaded (attempt {attempt + 1}/{max_attempts}), retrying in {wait}s...")
                        _time.sleep(wait)
                        continue
                    print(f"[error] extract_upload_fields: LLM call failed for {field_key}: {e}")
                    raw = None
                    break

            value = raw if raw and raw != "N/A" else "N/A"
            results[output_key] = value
            print(f"  {output_key}: {value}")

        return results
