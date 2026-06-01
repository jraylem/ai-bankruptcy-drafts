from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    order_reinstate_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_ORDER_REINSTATE_GMAIL,
)


# Called by: service/order_reinstate.py → generate_payload_reinstate_from_hearing_for_session_gmail
#   -> tasks/extractors.py → OrderReinstateExtractor
class GmailOrderReinstateAgent:
    """
    Claude-backed Order Reinstate Agent.

    Dedicated agent for the Order on Motion to Reinstate flow.

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_reinstate, case_number_reinstate
    - Gmail vectorstore (gmail_<session_id>) for:
      chapter_number_reinstate, judge_initial_reinstate, case_number_reinstate_gmail (fallback)
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
            "debtor_name_reinstate",
            "case_number_reinstate",
        ]
        # Gmail-based fields
        self.gmail_fields = [
            "chapter_number_reinstate",
            "judge_initial_reinstate",
        ]

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "debtor_name_reinstate": "Your full name Debtor 1",
            "case_number_reinstate": "Case number if known",
            "chapter_number_reinstate": "chapter case details",
            "judge_initial_reinstate": "Judge",
            "case_number_reinstate_gmail": "Case number with judge initial from emails",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = order_reinstate_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_ORDER_REINSTATE_GMAIL[field_name],
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
        Extract order reinstate payload using Gmail + petition vectorstores.
        """
        try:
            print("Starting Claude-backed sequential field extraction for order reinstate...")

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

            # Combine judge initials (from Gmail) with base case number (from PDF)
            judge_initial = gmail_results.get("judge_initial_reinstate", "N/A")
            case_number = pdf_results.get("case_number_reinstate", "N/A")

            combined_case_number = case_number
            if judge_initial != "N/A" and judge_initial and case_number != "N/A" and case_number:
                combined_case_number = f"{case_number}-{judge_initial}"
            else:
                # Fallback: try to get the full case number (with judge initial) directly from Gmail
                print("  judge_initial_reinstate N/A from Gmail, falling back to full case number from Gmail...")
                gmail_case_number = self._extract_single_field(
                    "case_number_reinstate_gmail",
                    self._get_optimized_query("case_number_reinstate_gmail"),
                )
                print(f"    case_number_reinstate (Gmail full fallback): {gmail_case_number}")
                if gmail_case_number and gmail_case_number != "N/A":
                    combined_case_number = gmail_case_number

            final_payload = {
                "DebtorName": pdf_results.get("debtor_name_reinstate", "N/A"),
                "CaseNumber": combined_case_number,
                "ChapterNumb": gmail_results.get("chapter_number_reinstate", "N/A"),
            }

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Claude-backed order reinstate payload: {final_payload}")
            print(
                f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)"
            )

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "claude_order_reinstate_agent_sequential",
                "field_results": extracted_fields,
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Claude Order reinstate payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "claude_order_reinstate_agent_sequential",
            }
