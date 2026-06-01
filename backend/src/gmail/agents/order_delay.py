from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_STANDARD, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import order_delay_gmail_tool
from ..prompts import INDIVIDUAL_FIELD_PROMPTS_ORDER_DELAY


# Called by: service.generate_order_delay_payload_for_session_gmail (routes/order_stream.py)
class GmailOrderDelayAgent:
    """
    Claude Sonnet-backed Order Delay Agent.

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_delay
    - Gmail vectorstore (gmail_<session_id>) for:
      case_number_delay (with judge initial), chapter_delay
    """

    def __init__(self, session_id: Optional[str] = None, memory_saver: MemorySaver = None):
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

        self.pdf_fields = ["court_district_delay", "debtor_name_delay"]
        self.gmail_fields = ["case_number_delay", "chapter_delay"]

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "court_district_delay": "United States Bankruptcy Court for the",
            "debtor_name_delay": "Your full name Debtor 1",
            "case_number_delay": "Case number with judge initial from emails",
            "case_number_delay_pdf": "Case number if known",
            "chapter_delay": "chapter case details",
            "chapter_delay_pdf": "chapter case details",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = order_delay_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_ORDER_DELAY[field_name],
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
        Extract order delay payload using Gmail + petition vectorstores.
        """
        try:
            print("Starting sequential field extraction for order delay...")

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
            case_number = gmail_results.get("case_number_delay", "N/A")
            if not case_number or case_number == "N/A":
                print("  case_number_delay N/A from Gmail, falling back to PDF...")
                case_number = self._extract_single_field(
                    "case_number_delay_pdf",
                    self._get_optimized_query("case_number_delay_pdf"),
                )
                print(f"    case_number_delay (PDF fallback): {case_number}")

            chapter = gmail_results.get("chapter_delay", "N/A")
            if not chapter or chapter == "N/A":
                print("  chapter_delay N/A from Gmail, falling back to PDF...")
                chapter = self._extract_single_field(
                    "chapter_delay_pdf",
                    self._get_optimized_query("chapter_delay_pdf"),
                )
                print(f"    chapter_delay (PDF fallback): {chapter}")

            final_payload = {
                "CaseNumber":    case_number,
                "ChapterNumber": chapter,
                "DebtorName":    pdf_results.get("debtor_name_delay", "N/A"),
                "CourtDistrict": pdf_results.get("court_district_delay", "N/A"),
            }

            all_results = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in all_results.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final order delay base payload: {final_payload}")
            print(f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)")

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "gmail_order_delay_agent_sequential",
                "field_results": all_results,
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Order delay payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "gmail_order_delay_agent_sequential",
            }
