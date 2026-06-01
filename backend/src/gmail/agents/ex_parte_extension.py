from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    motion_ex_parte_extension_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_EX_PARTE_EXTENSION_GMAIL,
)


# Called by: service.generate_payload_ex_parte_extension_for_session_gmail (L2)
#   -> routes/service_stream.py
class GmailMotionExParteExtensionAgent:
    """
    Gmail-backed Ex Parte Motion for Extension Agent.

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_ex_parte_extension, case_number_ex_parte_extension, date_filed_ex_parte_extension
    - Gmail vectorstore (gmail_<session_id>) for:
      chapter_number_ex_parte_extension, judge_ex_parte_extension, meeting_date_ex_parte_extension

    Output payload shape matches the CourtDrive-based ex parte extension payload.
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
            "debtor_name_ex_parte_extension",
            "case_number_ex_parte_extension",
            "date_filed_ex_parte_extension",
        ]
        # Gmail-based fields
        self.gmail_fields = [
            "chapter_number_ex_parte_extension",
            "judge_ex_parte_extension",
            "meeting_date_ex_parte_extension",
        ]

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "debtor_name_ex_parte_extension": "Your full name Debtor 1",
            "case_number_ex_parte_extension": "Case number if known",
            "date_filed_ex_parte_extension": "date filed petition",
            "chapter_number_ex_parte_extension": "chapter case details",
            "judge_ex_parte_extension": "Judge",
            "meeting_date_ex_parte_extension": "meeting of creditors date",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = motion_ex_parte_extension_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_EX_PARTE_EXTENSION_GMAIL[field_name],
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

    def _extract_current_date(self) -> str:
        from datetime import datetime

        return datetime.now().strftime("%B %d %Y")

    def _calculate_date_filed_plus_fourteen(self, date_filed: str) -> str:
        from datetime import timedelta
        from dateutil.parser import parse

        try:
            parsed_date = parse(date_filed)
            new_date = parsed_date + timedelta(days=14)
            return new_date.strftime("%B %d %Y")
        except Exception as e:
            print(f"Error calculating date_filed_plus_fourteen: {str(e)}")
            return "N/A"

    def extract_payload(self, user_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract ex parte extension payload using Gmail + petition vectorstores.
        """
        try:
            print("Starting Gmail-backed sequential field extraction for ex parte motion for extension...")

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

            debtor_name = pdf_results.get("debtor_name_ex_parte_extension", "N/A")
            case_number = pdf_results.get("case_number_ex_parte_extension", "N/A")
            judge_initial = gmail_results.get("judge_ex_parte_extension", "N/A")
            chapter_number = gmail_results.get("chapter_number_ex_parte_extension", "N/A")
            date_filed = pdf_results.get("date_filed_ex_parte_extension", "N/A")
            meeting_date = gmail_results.get("meeting_date_ex_parte_extension", "N/A")

            case_number_judge = case_number
            if judge_initial != "N/A" and judge_initial and case_number != "N/A" and case_number:
                case_number_judge = f"{case_number}-{judge_initial}"

            date_filed_plus_fourteen = self._calculate_date_filed_plus_fourteen(date_filed)
            current_date = self._extract_current_date()

            final_payload = {
                "DebtorName": debtor_name,
                "CaseNumber": case_number_judge,
                "ChapterNumber": chapter_number,
                "DateFiled": date_filed,
                "DateFiledPlusFourteen": date_filed_plus_fourteen,
                "MeetingDate": meeting_date,
                "CurrentDate": current_date,
            }

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Gmail-backed ex parte extension payload: {final_payload}")
            print(
                f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)"
            )

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "gmail_motion_ex_parte_extension_agent_sequential",
                "field_results": {**extracted_fields, "current_date": current_date},
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Gmail Ex Parte extension payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "gmail_motion_ex_parte_extension_agent_sequential",
            }


