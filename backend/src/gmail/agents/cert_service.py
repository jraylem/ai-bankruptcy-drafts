from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    cert_service_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_CERT_SERVICE_GMAIL,
)


# Called by: service/cert_service.py → generate_payload_service_for_session_gmail
#   -> tasks/extractors.py + all _with_service_ composite functions (L3A, L3B, L3C)
class GmailMotionServiceAgent:
    """
    Claude-backed Motion Service Agent.

    Extracts base certificate of service fields only:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>):
      court_district_cert_service, debtor_name_cert_service
    - Gmail vectorstore (gmail_<session_id>):
      case_number_cert_service (with judge initial), chapter_cert_service

    Trustee info, Notice of Hearing, and MiscMailListings are handled
    in service/cert_service.py via search_and_extract_subject_email.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        memory_saver: MemorySaver = None,
    ):
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
            "court_district_cert_service",
            "debtor_name_cert_service",
        ]
        # Gmail-based fields (case number with judge initial, chapter)
        self.gmail_fields = [
            "case_number_cert_service",
            "chapter_cert_service",
        ]

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "court_district_cert_service": "United States Bankruptcy Court for the",
            "debtor_name_cert_service": "Your full name Debtor 1",
            "case_number_cert_service": "Case number with judge initial from emails",
            "case_number_cert_service_pdf": "Case number if known",
            "chapter_cert_service": "chapter case details from emails",
            "chapter_cert_service_pdf": "chapter case details",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = cert_service_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_CERT_SERVICE_GMAIL[field_name],
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

                # Reject verbose/markdown responses — Claude sometimes explains
                # why it can't find a value instead of returning "N/A" directly.
                # A valid extracted value is a single short line with no markdown.
                is_verbose = (
                    "\n" in ai_response
                    or "|" in ai_response
                    or ai_response.startswith("#")
                    or len(ai_response) > 200
                )
                if is_verbose:
                    print(f"  Verbose response detected for {field_name}, treating as N/A")
                    ai_response = "N/A"

                if ai_response and ai_response != "N/A":
                    return ai_response
                elif attempt < max_retries:
                    print(f"  Retrying {field_name} (attempt {attempt + 1})...")
                    continue
                else:
                    return "N/A"

            except Exception as e:
                if "recursion limit" in str(e).lower() and attempt < max_retries:
                    print(f"  Recursion error for {field_name}, retrying with different approach...")
                    query = f"{field_name}"
                    continue
                else:
                    print(f"Error extracting {field_name}: {str(e)}")
                    if attempt < max_retries:
                        continue
                    return "N/A"

        return "N/A"

    def _get_ordinal_suffix(self, day: int) -> str:
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return suffix

    def _extract_current_date(self) -> str:
        try:
            from datetime import datetime
            now = datetime.now()
            day = now.day
            suffix = self._get_ordinal_suffix(day)
            month = now.strftime("%B")
            year = now.year
            return f"{day}{suffix} day of {month}, {year}"
        except Exception as e:
            print(f"Error getting current date: {str(e)}")
            return "N/A"

    def extract_payload(self, user_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract base certificate of service fields from Gmail + petition vectorstores.
        Trustee/hearing fields are resolved in service/cert_service.py.
        """
        try:
            print("Starting Claude-backed sequential field extraction for cert service (base fields)...")

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

            # Always extract case number from PDF (used as CaseNumberPDF and as fallback for CaseNumber)
            print("  Extracting case_number_cert_service_pdf from petition...")
            case_number_pdf = self._extract_single_field(
                "case_number_cert_service_pdf",
                self._get_optimized_query("case_number_cert_service_pdf"),
            )
            print(f"    case_number_cert_service_pdf: {case_number_pdf}")

            # Case number from Gmail already includes judge initial (e.g., "25-14980-PDR")
            case_number = gmail_results.get("case_number_cert_service", "N/A")
            # PDF fallback: if case_number is N/A, reuse already-extracted PDF value
            if not case_number or case_number == "N/A":
                print("  case_number_cert_service N/A from Gmail, falling back to PDF...")
                case_number = case_number_pdf
                print(f"    case_number_cert_service (PDF fallback): {case_number}")

            chapter = gmail_results.get("chapter_cert_service", "N/A")
            if not chapter or chapter == "N/A":
                print("  chapter_cert_service N/A from Gmail, falling back to PDF...")
                chapter = self._extract_single_field(
                    "chapter_cert_service_pdf",
                    self._get_optimized_query("chapter_cert_service_pdf"),
                )
                print(f"    chapter_cert_service (PDF fallback): {chapter}")

            print("Extracting current date...")
            current_date = self._extract_current_date()
            print(f"    current_date: {current_date}")

            final_payload = {
                "CaseNumber":    case_number,
                "CaseNumberPDF": case_number_pdf,
                "DebtorName":    pdf_results.get("debtor_name_cert_service", "N/A"),
                "CourtDistrict": pdf_results.get("court_district_cert_service", "N/A"),
                "Chapter":       chapter,
                "CurrentDate":   current_date,
            }

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Claude-backed CoS base payload: {final_payload}")
            print(f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)")

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "claude_motion_service_agent_sequential",
                "field_results": {
                    **extracted_fields,
                    "current_date": current_date,
                },
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Gmail Motion service payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "claude_motion_service_agent_sequential",
            }
