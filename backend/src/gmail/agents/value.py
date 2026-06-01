from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    motion_value_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_VALUE_GMAIL,
)


# Called by: service.generate_payload_value_for_session_gmail (L2)
#   -> routes/service_stream.py, routes/order_stream.py (via generate_order_value_payload)
class GmailMotionValueAgent:
    """
    Gmail-backed Motion Value Agent.

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_value, creditor_value, car_model_value, vin_model_value,
      odometer_value, value_amount_value, value_method_value
    - Gmail vectorstore (gmail_<session_id>) for:
      case_number_value (with judge initial)
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
            "debtor_name_value",
            "car_model_value",   # extracted before creditor so its value can enrich the creditor query
            "vin_model_value",   # extracted before creditor so its value can enrich the creditor query
            "creditor_value",
            "odometer_value",
            "value_amount_value",
            "value_method_value",
        ]
        # Gmail-based fields (case number with judge initial, chapter)
        self.gmail_fields = ["case_number_value", "chapter_value"]

        # Static fields for value motion
        self.static_fields = {
            "Percent": "N/A",
            "Price": "N/A",
        }

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "case_number_value": "Case number with judge initial from emails",
            "case_number_value_pdf": "Case number if known",
            "chapter_value": "chapter case details",
            "chapter_value_pdf": "chapter case details",
            "debtor_name_value": "Your full name Debtor 1",
            "creditor_value": "creditor secured claim vehicle financing",
            "car_model_value": "vehicle make model car",
            "vin_model_value": "VIN vehicle identification number",
            "odometer_value": "odometer mileage reading",
            "value_amount_value": "vehicle value current value",
            "value_method_value": "valuation method KBB NADA appraisal",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = motion_value_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_VALUE_GMAIL[field_name],
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
        Extract motion value payload using Gmail + petition vectorstores.
        """
        try:
            print("Starting Gmail-backed sequential field extraction for motion value...")

            pdf_results: Dict[str, str] = {}
            print("Extracting petition (PDF) fields...")
            for field in self.pdf_fields:
                print(f"  Extracting {field}...")
                if field == "creditor_value":
                    # Enrich query with already-extracted car model and VIN so the
                    # vectorstore retrieves the correct Schedule D entry (not Schedule G).
                    # Replace newlines with spaces so multi-vehicle values stay on one query line.
                    car_model = pdf_results.get("car_model_value", "").replace("\n", " ")
                    vin = pdf_results.get("vin_model_value", "").replace("\n", " ")
                    vehicle_info = " ".join(filter(None, [car_model, vin])).strip()
                    query = f"Schedule D creditor secured claim {vehicle_info}".strip()
                    if user_hint:
                        query = f"{query} {user_hint}"
                elif field in ("odometer_value", "value_amount_value"):
                    # Enrich query with already-extracted VIN so the vectorstore retrieves
                    # the correct Schedule A/B entry when multiple vehicles exist on the same page.
                    vin = pdf_results.get("vin_model_value", "").replace("\n", " ")
                    base = "Schedule A/B approximate mileage" if field == "odometer_value" else "Schedule A/B current value"
                    query = f"{base} {vin}".strip() if vin else self._get_optimized_query(field, user_hint)
                    if user_hint:
                        query = f"{query} {user_hint}"
                else:
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

            # Combine all results
            all_results = {**pdf_results, **gmail_results, **self.static_fields}

            # Case number from Gmail already includes judge initial (e.g., "25-14980-PDR")
            case_number = gmail_results.get("case_number_value", "N/A")
            # PDF fallback: if case_number is N/A, extract from petition
            if not case_number or case_number == "N/A":
                print("  case_number_value N/A from Gmail, falling back to PDF...")
                case_number = self._extract_single_field(
                    "case_number_value_pdf",
                    self._get_optimized_query("case_number_value_pdf"),
                )
                print(f"    case_number_value (PDF fallback): {case_number}")

            chapter = gmail_results.get("chapter_value", "N/A")
            if not chapter or chapter == "N/A":
                print("  chapter_value N/A from Gmail, falling back to PDF...")
                chapter = self._extract_single_field(
                    "chapter_value_pdf",
                    self._get_optimized_query("chapter_value_pdf"),
                )
                print(f"    chapter_value (PDF fallback): {chapter}")

            # Create final JSON payload with the exact structure requested
            final_payload = {
                "CaseNumber": case_number,
                "ChapterNumber": chapter,
                "DebtorName": pdf_results.get("debtor_name_value", "N/A"),
                "Creditor": pdf_results.get("creditor_value", "N/A"),
                "CarModel": pdf_results.get("car_model_value", "N/A"),
                "VinModel": pdf_results.get("vin_model_value", "N/A"),
                "Odometer": pdf_results.get("odometer_value", "N/A"),
                "Value": pdf_results.get("value_amount_value", "N/A"),
                "ValueMethod": pdf_results.get("value_method_value", "N/A"),
                "Percent": self.static_fields["Percent"],
                "Price": self.static_fields["Price"],
            }

            extracted_fields = {**pdf_results, **gmail_results}
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in extracted_fields.values() if value and value != "N/A"
            )
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0

            print(f"Final Gmail-backed value payload: {final_payload}")
            print(f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)")

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "gmail_motion_value_agent_sequential",
                "field_results": all_results,
                "success_rate": success_rate,
            }

        except Exception as e:
            return {
                "payload": f"Gmail Motion value payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "gmail_motion_value_agent_sequential",
            }
