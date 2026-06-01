from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    motion_delay_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_DELAY_GMAIL,
)


# Called by: service.generate_payload_delay_for_session_gmail (L2)
#   -> routes/service_stream.py
class GmailMotionDelayAgent:
    """
    Gmail-backed Motion Delay Agent.

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_delay, case_number_delay, date_filed_delay, vehicle_delay, vin_delay,
      house_delay, address_delay, creditors_delay
    - Gmail vectorstore (gmail_<session_id>) for:
      chapter_number_delay, judge_initial_delay, concluded_meeting_date_delay
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
            "debtor_name_delay",
            "case_number_delay",
            "date_filed_delay",
            "vehicle_delay",
            "vin_delay",
            "house_delay",
            "address_delay",
            "creditors_delay",
        ]
        # Gmail-based fields (chapter, judge initial, concluded meeting date)
        self.gmail_fields = [
            "chapter_number_delay",
            "judge_initial_delay",
            "concluded_meeting_date_delay",
        ]

        # Static fields for delay motion
        self.static_fields = {
            "ReasonForDelay": "N/A",
            "IfReaffirmation": "N/A",
            "ReaffirmationNeeded": "N/A",
        }

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "debtor_name_delay": "Your full name Debtor 1",
            "case_number_delay": "Case number if known",
            "date_filed_delay": "date filed petition",
            "vehicle_delay": "vehicle make model year car",
            "vin_delay": "VIN# or vehicle identification number",
            "house_delay": "local property identification number",
            "address_delay": "street address, city, state, zip code, county Part 1 Schedule A/B property",
            "creditors_delay": "creditor's name",
            "chapter_number_delay": "chapter case details",
            "judge_initial_delay": "Judge",
            "concluded_meeting_date_delay": "meeting of creditors concluded date",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = motion_delay_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_DELAY_GMAIL[field_name],
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

    def _extract_current_date(self) -> str:
        try:
            from datetime import datetime

            return datetime.now().strftime("%B %d, %Y")
        except Exception as e:
            print(f"Error getting current date: {str(e)}")
            return "N/A"

    def extract_payload(self, user_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract motion delay payload using Gmail + petition vectorstores.
        """
        try:
            print("Starting Gmail-backed sequential field extraction for motion delay...")

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

            print("Extracting current date...")
            current_date = self._extract_current_date()
            print(f"    current_date: {current_date}")

            # Combine judge initials with case number (from PDF)
            judge_initial = gmail_results.get("judge_initial_delay", "N/A")
            case_number = pdf_results.get("case_number_delay", "N/A")

            # Create combined case number if judge initial is available and case number exists
            combined_case_number = case_number
            if judge_initial != "N/A" and judge_initial and case_number != "N/A" and case_number:
                combined_case_number = f"{case_number}-{judge_initial}"

            # Generate delay reason recommendations (for non-reaffirmation cases)
            print("Generating delay reason recommendations...")
            from ...motion_filling.fill_motion_delay import generate_delay_reason_recommendations
            delay_reason_recommendations = generate_delay_reason_recommendations()
            print(f"    Generated {len(delay_reason_recommendations)} recommendations")

            # Create final JSON payload
            final_payload = {
                "DebtorName": pdf_results.get("debtor_name_delay", "N/A"),
                "CaseNumber": combined_case_number,
                "ChapterNumb": gmail_results.get("chapter_number_delay", "N/A"),
                "District": "SOUTHERN",  # Default to Southern District of Florida
                "DateFiled": pdf_results.get("date_filed_delay", "N/A"),
                "ConcludedMeetingDate": gmail_results.get("concluded_meeting_date_delay", "N/A"),
                "ReasonForDelay": self.static_fields["ReasonForDelay"],
                "IfReaffirmation": self.static_fields["IfReaffirmation"],
                "CurrentDate": current_date,
                "Vehicle": pdf_results.get("vehicle_delay", "N/A"),
                "VIN": pdf_results.get("vin_delay", "N/A"),
                "House": pdf_results.get("house_delay", "N/A"),
                "Address": pdf_results.get("address_delay", "N/A"),
                "Creditors": pdf_results.get("creditors_delay", "N/A"),
                "ReaffirmationNeeded": self.static_fields["ReaffirmationNeeded"],
                "DelayReasonRecommendations": delay_reason_recommendations,
            }

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Gmail-backed delay payload: {final_payload}")
            print(f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)")

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "gmail_motion_delay_agent_sequential",
                "field_results": {
                    **extracted_fields,
                    "current_date": current_date,
                },
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Gmail Motion delay payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "gmail_motion_delay_agent_sequential",
            }


