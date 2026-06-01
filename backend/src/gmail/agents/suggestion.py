from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    suggestion_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_SUGGESTION_GMAIL,
)


# Called by: service.generate_payload_suggestion_for_session_gmail (L2)
#   -> routes/service_stream.py
class GmailMotionSuggestionAgent:
    def __init__(
        self,
        session_id: Optional[str] = None,
        memory_saver: MemorySaver = None,
    ):
        """
        Initialize the Claude-backed Motion Suggestion Agent for suggestion motion payload.
        Uses:
        - Gmail vectorstore (gmail_<session_id>) for: case_number (with judge initial)
        - Petition vectorstore (bankruptcy_knowledge_<session_id>) for: debtor_name, date_filed, case_number (PDF fallback)
        """
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.session_id = session_id
        self.memory_saver = memory_saver or MemorySaver()

        self.llm = init_chat_model(
            CLAUDE_MODEL_STANDARD,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE,
        )

        # Petition-based fields
        self.pdf_fields = [
            "debtor_name_suggestion",
            "district_suggestion",
            "creditor_suggestion",
            "date_filed_suggestion",
            "court_agency_suggestion",
            "vs_case_no_suggestion",
        ]
        # Gmail-based fields (case number with judge initial)
        self.gmail_fields = [
            "case_number_suggestion",
        ]
    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "case_number_suggestion": "Case number with judge initial from emails",
            "case_number_suggestion_pdf": "Case number if known",
            "debtor_name_suggestion": "Your full name Debtor 1",
            "district_suggestion": "United States Bankruptcy Court for the",
            "creditor_suggestion": "Identify Legal Actions Repossessions Foreclosures case title plaintiff vs defendant",
            "date_filed_suggestion": "date filed filing date petition",
            "court_agency_suggestion": "Court or Agency Name",
            "vs_case_no_suggestion": "Case Number under the Versus case between Debtor and Creditor",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = suggestion_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_SUGGESTION_GMAIL[field_name],
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
                                content = message.content
                                # Claude with tool use returns a list of content blocks, not a plain string
                                if isinstance(content, list):
                                    text_parts = [
                                        block.text for block in content
                                        if hasattr(block, "text")
                                    ]
                                    content = " ".join(text_parts)
                                ai_messages.append(content)
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
                    print(f"  Recursion error for {field_name}, retrying with different approach...")
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
        Extract suggestion motion payload using Gmail + petition vectorstores via Claude Sonnet.
        """
        try:
            print("Starting Claude-backed sequential field extraction for motion suggestion...")

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

            # Case number from Gmail already includes judge initial (e.g., "25-14980-PDR")
            case_number = gmail_results.get("case_number_suggestion", "N/A")
            # PDF fallback: if case_number is N/A, extract from petition
            if not case_number or case_number == "N/A":
                print("  case_number_suggestion N/A from Gmail, falling back to PDF...")
                case_number = self._extract_single_field(
                    "case_number_suggestion_pdf",
                    self._get_optimized_query("case_number_suggestion_pdf"),
                )
                print(f"    case_number_suggestion (PDF fallback): {case_number}")


            final_payload = {
                "CaseNumberVS": pdf_results.get("vs_case_no_suggestion", "N/A"), #not 25-21322 should be CACE22014610
                "CaseNumber": case_number, #25-21322 as an example
                "DebtorName": pdf_results.get("debtor_name_suggestion", "N/A"),
                "Creditor": pdf_results.get("creditor_suggestion", "N/A"),
                "CourtAgency":pdf_results.get("court_agency_suggestion", "N/A"),
                "County": "N/A",
                "CircuitNumber": "N/A",
                "District": pdf_results.get("district_suggestion", "N/A"),
                "DateFiled": pdf_results.get("date_filed_suggestion", "N/A"),
            }

            all_results = {**pdf_results, **gmail_results}

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Claude-backed Suggestion payload: {final_payload}")
            print(f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)")

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "claude_motion_suggestion_agent_sequential",
                "field_results": all_results,
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Claude Motion suggestion payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "claude_motion_suggestion_agent_sequential",
            }
