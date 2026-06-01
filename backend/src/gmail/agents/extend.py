"""
Gmail Motion Extend Agent - Revamped

Extracts payload for Motion to Extend Automatic Stay using:
- Petition vectorstore for current case info + dismissed case number (page 3, item 9)
- Gmail search for Order Dismissing Case email (trustees_reason, docket_entry_no, dismissal_date)
- AI recommendations for user input fields (dismissal_reason, change_in_circum)

Follows the combined extraction pattern from modify.py for efficiency.
"""

from typing import Optional, Dict, Any, List, Tuple
import json
import re
import base64
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import motion_extend_gmail_tool
from ..prompts import INDIVIDUAL_FIELD_PROMPTS_EXTEND_GMAIL
from ..extractor import search_and_extract_subject_email
from ..auth import get_gmail_service
from ...chatbot.vectorestore import search_vectorstore


class DismissedCaseExtraction(BaseModel):
    """Extracted fields from Order Dismissing Case email."""
    trustees_reason: Optional[str] = Field(default=None, description="Reason for dismissal from Docket Text")
    docket_entry_no: Optional[str] = Field(default=None, description="Document Number of the dismissal order")
    dismissal_date: Optional[str] = Field(default=None, description="Date case was dismissed, format: 'Month DD, YYYY'")


class Chapter13PlanExtraction(BaseModel):
    """Extracted fields from Chapter 13 Plan document."""
    plan_payment_amount: Optional[str] = Field(default=None, description="Monthly plan payment amount")
    plan_duration: Optional[str] = Field(default=None, description="Plan duration in months")


class PetitionDismissedCaseExtraction(BaseModel):
    """Extracted dismissed case info from petition page 3, item 9."""
    dismissed_case_number: Optional[str] = Field(default=None, description="Prior dismissed case number (e.g., '25-19062')")
    dismissed_district: Optional[str] = Field(default=None, description="District of prior case")
    dismissed_date: Optional[str] = Field(default=None, description="Date of prior filing")
    has_prior_case: bool = Field(description="Whether debtor has filed bankruptcy in last 8 years")


class ExtendAIRecommendations(BaseModel):
    """AI-generated recommendations for user input fields."""
    dismissal_reason_chips: List[str] = Field(default_factory=list, description="3 recommendation chips for dismissal reason")
    change_in_circum_chips: List[str] = Field(default_factory=list, description="3 recommendation chips for change in circumstances")
    has_old_petition: bool = Field(default=False)
    has_chapter_13_plan: bool = Field(default=False)
    context_warnings: List[str] = Field(default_factory=list)


class GmailMotionExtendAgent:
    """
    Gmail-backed Motion Extend Agent (Revamped).

    New extraction flow:
    1. Extract current case info from petition vectorstore
    2. Extract dismissed case number from petition page 3, item 9
    3. Search Gmail for Order Dismissing Case email using dismissed case number
    4. Extract trustees_reason, docket_entry_no, dismissal_date from email
    5. Gather context for AI recommendations (old petition, Chapter 13 plan)
    6. Generate AI recommendation chips for user input fields
    """

    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"

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

        self.pdf_fields = [
            "court_district_extend",
            "debtor_name_extend",
            "petition_date_extend",
        ]

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "court_district_extend": "United States Bankruptcy Court for the",
            "debtor_name_extend": "Your full name Debtor 1",
            "petition_date_extend": "Executed on signature",
            "case_number_extend": "Case number with judge initial from emails",
            "chapter_extend": "chapter case details",
            "court_division_extend": "hearing notices courthouse address division",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                tools = motion_extend_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_EXTEND_GMAIL[field_name],
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
                    print(f"  Recursion error for {field_name}, retrying...")
                    query = f"{field_name}"
                    continue
                else:
                    print(f"Error extracting {field_name}: {str(e)}")
                    if attempt < max_retries:
                        continue
                    return "N/A"

        return "N/A"

    def _extract_dismissed_case_from_petition(self) -> Dict[str, Any]:
        """
        Extract dismissed case number from petition page 3, item 9.
        Question: "Have you filed for bankruptcy within the last 8 years?"
        """
        print(f"\n{self.CYAN}[STEP 2] Extracting dismissed case number from petition (page 3, item 9)...{self.RESET}")

        pdf_collection = f"bankruptcy_knowledge_{self.session_id}"
        query = "Have you filed for bankruptcy within the last 8 years case number district"

        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=20)
        if not pdf_docs:
            print(f"{self.YELLOW}  No relevant passages found for item 9{self.RESET}")
            return {"status": "needs_input", "dismissed_case_number": None}

        context = "\n\n".join(
            f"Content: {doc.page_content}" for doc in pdf_docs
        )

        prompt = f"""You are extracting information from a bankruptcy petition.

Look for the section about prior bankruptcy filings (usually page 3, item 9):
"Have you filed for bankruptcy within the last 8 years?"

{context}

Extract:
1. has_prior_case: Did the debtor answer "Yes" to having filed bankruptcy in the last 8 years?
2. dismissed_case_number: The case number of the prior case (e.g., "25-19062")
3. dismissed_district: The district of the prior case (e.g., "Southern District of FLA")
4. dismissed_date: The date of the prior filing (e.g., "8/5/25")

If the debtor answered "No" or the information is not present, set has_prior_case to false.
Extract only the base case number without judge initials (e.g., "25-19062" not "25-19062-SMG")."""

        try:
            structured_llm = self.llm.with_structured_output(PetitionDismissedCaseExtraction)
            result = structured_llm.invoke(prompt)

            if result.has_prior_case and result.dismissed_case_number:
                base_match = re.search(r'(\d{2}-\d{4,5})', result.dismissed_case_number)
                case_num = base_match.group(1) if base_match else result.dismissed_case_number

                print(f"{self.GREEN}  ✓ Found prior case: {case_num}{self.RESET}")
                print(f"{self.GREEN}    District: {result.dismissed_district}{self.RESET}")
                print(f"{self.GREEN}    Date: {result.dismissed_date}{self.RESET}")

                return {
                    "status": "success",
                    "dismissed_case_number": case_num,
                    "dismissed_district": result.dismissed_district,
                    "dismissed_date": result.dismissed_date,
                }
            else:
                print(f"{self.YELLOW}  No prior case found in petition{self.RESET}")
                return {"status": "needs_input", "dismissed_case_number": None}

        except Exception as e:
            print(f"{self.RED}  Error extracting from petition: {e}{self.RESET}")
            return {"status": "needs_input", "dismissed_case_number": None}

    def _extract_email_body(self, payload: dict) -> str:
        """Extract plain text body from email payload."""
        def get_body_from_parts(parts):
            for part in parts:
                mime_type = part.get("mimeType", "")
                if mime_type == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                if "parts" in part:
                    result = get_body_from_parts(part.get("parts", []))
                    if result:
                        return result
            return ""

        body_data = payload.get("body", {}).get("data", "")
        if body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")

        parts = payload.get("parts", [])
        if parts:
            return get_body_from_parts(parts)

        return ""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError,)),
    )
    def _search_gmail_with_retry(self, query: str, max_results: int = 10) -> List[Dict]:
        """Search Gmail with automatic retry on transient failures."""
        gmail_service = get_gmail_service()
        response = gmail_service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        return response.get("messages", []) or []

    def _search_order_dismissing_with_fallback(self, dismissed_case_number: str) -> Optional[Dict[str, Any]]:
        """Search for Order Dismissing Case email with multiple fallback strategies."""
        print(f"\n{self.CYAN}[STEP 3] Searching Gmail for Order Dismissing Case...{self.RESET}")

        email = search_and_extract_subject_email(
            case_number=dismissed_case_number,
            subject_title="Order Dismissing Case",
            oldest=False,
        )
        if email:
            print(f"{self.GREEN}  ✓ Found via primary search: {email.get('subject', '')[:60]}...{self.RESET}")
            return email

        print(f"{self.YELLOW}  Primary search failed, trying fallback...{self.RESET}")
        email = search_and_extract_subject_email(
            case_number=dismissed_case_number,
            subject_title="Dismissing Case",
            oldest=False,
        )
        if email:
            print(f"{self.GREEN}  ✓ Found via fallback: {email.get('subject', '')[:60]}...{self.RESET}")
            return email

        print(f"{self.YELLOW}  Fallback failed, trying direct Gmail search...{self.RESET}")
        return self._direct_gmail_search_dismissal(dismissed_case_number)

    def _direct_gmail_search_dismissal(self, dismissed_case_number: str) -> Optional[Dict[str, Any]]:
        """Direct Gmail API search as last resort."""
        try:
            gmail_service = get_gmail_service()
            query = f'"{dismissed_case_number}" (subject:"Order Dismissing" OR subject:"Dismissal")'
            print(f"{self.MAGENTA}  Query: {query}{self.RESET}")

            response = gmail_service.users().messages().list(
                userId="me", q=query, maxResults=10
            ).execute()

            message_refs = response.get("messages", []) or []
            if not message_refs:
                print(f"{self.RED}  ✗ No emails found{self.RESET}")
                return None

            for msg_ref in message_refs:
                msg = gmail_service.users().messages().get(
                    userId="me", id=msg_ref.get("id"), format="full"
                ).execute()

                payload = msg.get("payload", {}) or {}
                headers = payload.get("headers", []) or []

                subject = ""
                date_str = ""
                for h in headers:
                    name = h.get("name", "").lower()
                    if name == "subject":
                        subject = h.get("value", "")
                    elif name == "date":
                        date_str = h.get("value", "")

                body = self._extract_email_body(payload)
                if body and ("dismissing" in subject.lower() or "dismissal" in body.lower()):
                    print(f"{self.GREEN}  ✓ Found: {subject[:60]}...{self.RESET}")
                    return {
                        "email_id": msg_ref.get("id"),
                        "subject": subject,
                        "date": date_str,
                        "body": body,
                        "case_number": dismissed_case_number,
                    }

            return None

        except Exception as e:
            print(f"{self.RED}  Error in direct search: {e}{self.RESET}")
            return None

    def _extract_from_order_dismissing_email(self, email: Dict[str, Any]) -> Dict[str, str]:
        """Extract trustees_reason, docket_entry_no, dismissal_date from Order Dismissing Case email."""
        print(f"\n{self.CYAN}[STEP 4] Extracting fields from Order Dismissing email...{self.RESET}")

        subject = email.get("subject", "")
        body = email.get("body", "")
        email_date = email.get("date", "")

        email_context = f"""
════════════════════════════════════════════════════════════════
EMAIL TYPE: Order Dismissing Case
PURPOSE: Extract trustees_reason (from Docket Text), docket_entry_no (Document Number), dismissal_date
════════════════════════════════════════════════════════════════
SUBJECT: {subject}
DATE: {email_date}

BODY:
{body[:3000]}
"""

        prompt = f"""You are extracting information from an "Order Dismissing Case" court email.

{email_context}

Extract these fields:
1. trustees_reason: The reason for dismissal from the "Docket Text" field. Start with "due to..." or extract the core reason.
   Example: "due to denial of confirmation of plan" or "due to payment failure"
2. docket_entry_no: The "Document Number" of this dismissal order
3. dismissal_date: The date the case was dismissed, format as "Month DD, YYYY" (e.g., "November 17, 2025")
   Look for "entered on MM/DD/YYYY"

If a field cannot be found, use empty string ""."""

        try:
            structured_llm = self.llm.with_structured_output(DismissedCaseExtraction)
            result = structured_llm.invoke(prompt)

            trustees_reason = result.trustees_reason.strip() or "N/A"
            docket_entry_no = result.docket_entry_no.strip() or "N/A"
            dismissal_date = result.dismissal_date.strip() or "N/A"

            print(f"{self.GREEN}  ✓ trustees_reason: {trustees_reason[:50]}...{self.RESET}")
            print(f"{self.GREEN}  ✓ docket_entry_no: {docket_entry_no}{self.RESET}")
            print(f"{self.GREEN}  ✓ dismissal_date: {dismissal_date}{self.RESET}")

            return {
                "trustees_reason": trustees_reason,
                "docket_entry_no": docket_entry_no,
                "dismissal_date": dismissal_date,
            }

        except Exception as e:
            print(f"{self.RED}  Error extracting from email: {e}{self.RESET}")
            return {
                "trustees_reason": "N/A",
                "docket_entry_no": "N/A",
                "dismissal_date": "N/A",
            }

    def _find_case_number_from_gmail(self, debtor_name: str) -> str:
        """Fallback: Find case number from Gmail using debtor name."""
        print(f"{self.CYAN}[FALLBACK] Finding case number from Gmail using debtor name...{self.RESET}")

        if not debtor_name or debtor_name == "N/A":
            print(f"{self.YELLOW}  No debtor name available{self.RESET}")
            return "N/A"

        try:
            gmail_service = get_gmail_service()
            queries = [
                f'from:uscourts.gov "{debtor_name}"',
                f'"{debtor_name}"',
            ]

            message_refs = []
            for query in queries:
                print(f"{self.CYAN}  Query: {query}{self.RESET}")
                response = gmail_service.users().messages().list(
                    userId="me", q=query, maxResults=5
                ).execute()
                message_refs = response.get("messages", []) or []
                if message_refs:
                    print(f"{self.GREEN}  Found {len(message_refs)} emails{self.RESET}")
                    break
                print(f"{self.YELLOW}  No results, trying fallback...{self.RESET}")

            if not message_refs:
                print(f"{self.YELLOW}  No emails found{self.RESET}")
                return "N/A"

            for msg_ref in message_refs:
                msg = gmail_service.users().messages().get(
                    userId="me", id=msg_ref.get("id"), format="metadata",
                    metadataHeaders=["Subject"]
                ).execute()

                headers = msg.get("payload", {}).get("headers", [])
                subject = ""
                for h in headers:
                    if h.get("name", "").lower() == "subject":
                        subject = h.get("value", "")
                        break

                case_match = re.search(r"(\d{2}-\d{4,5}-[A-Z]{2,3})", subject)
                if case_match:
                    case_no = case_match.group(1)
                    print(f"{self.GREEN}  Found case number: {case_no}{self.RESET}")
                    return case_no

            print(f"{self.YELLOW}  No case number found in email subjects{self.RESET}")
            return "N/A"

        except Exception as e:
            print(f"{self.YELLOW}  Error: {e}{self.RESET}")
            return "N/A"

    def _get_chapter_13_plan_context(self, case_number: str) -> Tuple[str, bool]:
        """Extract Chapter 13 Plan payment details from Gmail."""
        print(f"\n{self.CYAN}[CONTEXT] Searching for Chapter 13 Plan...{self.RESET}")

        try:
            gmail_service = get_gmail_service()
            query = f'"{case_number}" subject:"Chapter 13 Plan"'
            print(f"{self.MAGENTA}  Query: {query}{self.RESET}")

            response = gmail_service.users().messages().list(
                userId="me", q=query, maxResults=10
            ).execute()

            message_refs = response.get("messages", []) or []
            if not message_refs:
                print(f"{self.YELLOW}  No Chapter 13 Plan emails found{self.RESET}")
                return ("", False)

            for msg_ref in message_refs:
                msg = gmail_service.users().messages().get(
                    userId="me", id=msg_ref.get("id"), format="full"
                ).execute()

                payload = msg.get("payload", {}) or {}
                headers = payload.get("headers", []) or []

                subject = ""
                for h in headers:
                    if h.get("name", "").lower() == "subject":
                        subject = h.get("value", "")
                        break

                if "order confirming" in subject.lower() or "order granting" in subject.lower():
                    continue

                body = self._extract_email_body(payload)
                if body:
                    print(f"{self.GREEN}  ✓ Found Chapter 13 Plan: {subject[:50]}...{self.RESET}")
                    return (body[:2000], True)

            return ("", False)

        except Exception as e:
            print(f"{self.YELLOW}  Error finding Chapter 13 Plan: {e}{self.RESET}")
            return ("", False)

    def _get_current_petition_schedule_context(self) -> str:
        """Extract Schedule I and J from current petition for AI recommendations."""
        print(f"\n{self.CYAN}[CONTEXT] Extracting Schedule I & J from current petition...{self.RESET}")

        pdf_collection = f"bankruptcy_knowledge_{self.session_id}"
        query = "Schedule I income Schedule J expenses monthly net income"

        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=25)
        if not pdf_docs:
            print(f"{self.YELLOW}  No Schedule I/J passages found{self.RESET}")
            return ""

        context = "\n\n".join(
            f"Content: {doc.page_content}" for doc in pdf_docs
        )

        print(f"{self.GREEN}  ✓ Found {len(pdf_docs)} relevant passages{self.RESET}")
        return context[:4000]

    def _get_old_petition_from_db(self, dismissed_case_number: str) -> Tuple[str, bool]:
        """
        Step 1: Check if old petition exists in DB (via ChatThread case_number -> vectorstore).
        """
        print(f"{self.CYAN}  [DB CHECK] Looking for old petition in database...{self.RESET}")

        try:
            from ...chatbot.models import ChatThread
            from ...chatbot.database import get_db_session

            # Query ChatThread by case_number to find session_id
            with get_db_session() as db:
                # Search for threads with matching case number (partial match)
                threads = db.query(ChatThread).filter(
                    ChatThread.case_number.ilike(f"%{dismissed_case_number}%")
                ).all()

                if not threads:
                    print(f"{self.YELLOW}    No session found in DB for case {dismissed_case_number}{self.RESET}")
                    return ("", False)

                # Try each matching session's vectorstore
                for thread in threads:
                    old_session_id = thread.session_id
                    print(f"{self.GREEN}    Found session {old_session_id} for case {dismissed_case_number}{self.RESET}")

                    # Search vectorstore for Schedule I/J
                    old_pdf_collection = f"bankruptcy_knowledge_{old_session_id}"
                    query = "Schedule I income Schedule J expenses monthly net income"

                    old_docs = search_vectorstore(query, collection_name=old_pdf_collection, k=15)
                    if old_docs:
                        context = "\n\n".join(f"Content: {doc.page_content}" for doc in old_docs)
                        print(f"{self.GREEN}    ✓ Found old petition in DB: {len(old_docs)} passages{self.RESET}")
                        return (context[:4000], True)

                print(f"{self.YELLOW}    Session found but no petition data in vectorstore{self.RESET}")
                return ("", False)

        except Exception as e:
            print(f"{self.YELLOW}    DB check failed: {e}{self.RESET}")
            return ("", False)

    def _get_old_petition_from_gmail(self, dismissed_case_number: str) -> Tuple[str, bool]:
        """
        Step 2: Search Gmail for old petition if not found in DB.
        """
        print(f"{self.CYAN}  [GMAIL CHECK] Searching Gmail for old petition...{self.RESET}")

        try:
            gmail_service = get_gmail_service()

            # Search for Voluntary Petition email with the dismissed case number
            queries = [
                f'"{dismissed_case_number}" subject:"Voluntary Petition"',
                f'"{dismissed_case_number}" subject:"Chapter 13 Voluntary Petition"',
                f'"{dismissed_case_number}" (subject:petition OR subject:"case filed")',
            ]

            for query in queries:
                print(f"{self.MAGENTA}    Query: {query}{self.RESET}")

                response = gmail_service.users().messages().list(
                    userId="me", q=query, maxResults=5
                ).execute()

                message_refs = response.get("messages", []) or []
                if message_refs:
                    print(f"{self.GREEN}    Found {len(message_refs)} potential emails{self.RESET}")

                    for msg_ref in message_refs:
                        msg = gmail_service.users().messages().get(
                            userId="me", id=msg_ref.get("id"), format="full"
                        ).execute()

                        payload = msg.get("payload", {}) or {}
                        headers = payload.get("headers", []) or []

                        subject = ""
                        for h in headers:
                            if h.get("name", "").lower() == "subject":
                                subject = h.get("value", "")
                                break

                        body = self._extract_email_body(payload)
                        if body and len(body) > 500:  # Substantial content
                            print(f"{self.GREEN}    ✓ Found old petition email: {subject[:50]}...{self.RESET}")
                            return (body[:5000], True)

            print(f"{self.YELLOW}    ✗ Old petition not found in Gmail{self.RESET}")
            return ("", False)

        except Exception as e:
            print(f"{self.RED}    Error searching Gmail: {e}{self.RESET}")
            return ("", False)

    def _get_old_petition_context(self, dismissed_case_number: str) -> Tuple[str, bool]:
        """
        Get Schedule I/J context from the OLD petition (previous dismissed case).

        Flow (as per ticket):
        1. First, check if it's in the DB (via case_number -> session -> vectorstore)
        2. If not in DB, search Gmail for Voluntary Petition email
        3. If still not found, return empty (user can upload it)

        Returns:
            Tuple of (context_string, found_boolean)
        """
        print(f"\n{self.CYAN}[CONTEXT] Searching for OLD petition (dismissed case: {dismissed_case_number})...{self.RESET}")

        if not dismissed_case_number or dismissed_case_number == "N/A":
            print(f"{self.YELLOW}  No dismissed case number provided{self.RESET}")
            return ("", False)

        # Step 1: Check DB first
        context, found = self._get_old_petition_from_db(dismissed_case_number)
        if found:
            return (context, True)

        # Step 2: Try Gmail as fallback
        context, found = self._get_old_petition_from_gmail(dismissed_case_number)
        if found:
            return (context, True)

        # Step 3: Not found - user may upload
        print(f"{self.YELLOW}  ✗ Old petition not found in DB or Gmail{self.RESET}")
        print(f"{self.YELLOW}    Recommendation chips will not be as robust.{self.RESET}")
        print(f"{self.YELLOW}    User may upload the old petition for better recommendations.{self.RESET}")
        return ("", False)

    def _calculate_petition_date_plus_30(self, petition_date: str) -> str:
        """Calculate petition date + 30 calendar days."""
        try:
            for fmt in ["%m/%d/%Y", "%B %d, %Y", "%Y-%m-%d", "%m/%d/%y"]:
                try:
                    dt = datetime.strptime(petition_date, fmt)
                    result = dt + timedelta(days=30)
                    return result.strftime("%B %d, %Y")
                except ValueError:
                    continue
            return "N/A"
        except Exception:
            return "N/A"

    def generate_recommendations(
        self,
        trustees_reason: str,
        current_petition_context: str,
        chapter_13_plan_context: str,
        dismissed_case_number: str = "",
    ) -> ExtendAIRecommendations:
        """
        Generate AI recommendation chips for DismissalReason and ChangeInCircum.

        Flow (as per ticket):
        1. Get old petition context (from Gmail using dismissed_case_number)
        2. Generate ChangeInCircum FIRST (needs: current petition, old petition, Chapter 13 plan)
        3. Generate DismissalReason SECOND (needs: trustees_reason + change_in_circum as context)
        """
        print(f"\n{self.CYAN}╔══════════════════════════════════════════════════════════════╗{self.RESET}")
        print(f"{self.CYAN}║  GENERATING AI RECOMMENDATIONS                               ║{self.RESET}")
        print(f"{self.CYAN}╚══════════════════════════════════════════════════════════════╝{self.RESET}")
        print(f"{self.GREEN}[FLOW] Step 1: Generate ChangeInCircum chips (needs petition context){self.RESET}")
        print(f"{self.GREEN}[FLOW] Step 2: Generate DismissalReason chips (needs TrusteeReason + ChangeInCircum){self.RESET}")
        print(f"{self.GREEN}{'─' * 60}{self.RESET}")
        print(f"{self.GREEN}[INPUT] Trustees Reason: {trustees_reason}{self.RESET}")
        print(f"{self.GREEN}[INPUT] Current Petition Context: {'Found' if current_petition_context else 'NOT FOUND'}{self.RESET}")
        print(f"{self.GREEN}[INPUT] Chapter 13 Plan Context: {'Found' if chapter_13_plan_context else 'NOT FOUND'}{self.RESET}")
        print(f"{self.GREEN}[INPUT] Dismissed Case Number (for old petition lookup): {dismissed_case_number or 'N/A'}{self.RESET}")

        context_warnings = []
        has_chapter_13_plan = bool(chapter_13_plan_context)

        # Step 1: Get old petition context from Gmail
        old_petition_context, has_old_petition = self._get_old_petition_context(dismissed_case_number)
        print(f"{self.GREEN}[INPUT] Previous Case Petition (from Gmail): {'FOUND ✓' if has_old_petition else 'NOT FOUND - user may upload for better recommendations'}{self.RESET}")

        if not has_chapter_13_plan:
            context_warnings.append("Chapter 13 Plan not found - recommendations may be less accurate")

        if not has_old_petition:
            context_warnings.append("Previous case petition not found in Gmail - you may upload it for better recommendations")

        # Build context for ChangeInCircum (needs: current petition, old petition, Chapter 13 plan, trustees_reason)
        change_in_circum_context = f"""
CURRENT PETITION (Schedule I & J):
{current_petition_context[:3000] if current_petition_context else "Not available"}

{"OLD PETITION (Previous Dismissed Case):" + chr(10) + old_petition_context[:2500] if old_petition_context else "OLD PETITION: Not available - could not find previous case petition in Gmail"}

{"CHAPTER 13 PLAN:" + chr(10) + chapter_13_plan_context[:1500] if chapter_13_plan_context else "CHAPTER 13 PLAN: Not available"}

TRUSTEE'S REASON FOR DISMISSAL (Technical Reason):
{trustees_reason}
"""

        # Step 2: Generate ChangeInCircum FIRST
        change_chips = self._generate_change_in_circum_chips(change_in_circum_context, trustees_reason)

        # Step 3: Generate DismissalReason SECOND (use trustees_reason + change_in_circum as context)
        dismissal_chips = self._generate_dismissal_reason_chips(trustees_reason, change_chips)

        return ExtendAIRecommendations(
            dismissal_reason_chips=dismissal_chips,
            change_in_circum_chips=change_chips,
            has_old_petition=has_old_petition,
            has_chapter_13_plan=has_chapter_13_plan,
            context_warnings=context_warnings,
        )

    def _generate_change_in_circum_chips(self, context: str, trustees_reason: str) -> List[str]:
        """
        Generate change in circumstances recommendation chips.

        Context includes: current petition (Schedule I/J), old petition, Chapter 13 plan, trustees_reason.
        This is generated FIRST, before DismissalReason.
        """
        print(f"\n{self.CYAN}{'=' * 70}{self.RESET}")
        print(f"{self.YELLOW}[AI] Generating ChangeInCircum recommendations (STEP 1)...{self.RESET}")
        print(f"{self.CYAN}{'=' * 70}{self.RESET}")
        has_old_petition = 'OLD PETITION' in context and 'Not available' not in context
        has_ch13_plan = 'CHAPTER 13 PLAN:' in context and 'Not available' not in context

        print(f"{self.GREEN}[CONTEXT SOURCES FOR CHANGE IN CIRCUM]{self.RESET}")
        print(f"{self.GREEN}  • Current Petition (bankruptcy_knowledge): Schedule I & J income/expenses{self.RESET}")
        print(f"{self.GREEN}  • Previous Case Petition (checked DB then Gmail): {'FOUND ✓' if has_old_petition else 'NOT FOUND - recommendations may be less robust'}{self.RESET}")
        print(f"{self.GREEN}  • Chapter 13 Plan (from Gmail): {'FOUND ✓' if has_ch13_plan else 'NOT FOUND'}{self.RESET}")
        print(f"{self.GREEN}  • Total context length: {len(context)} chars{self.RESET}")

        prompt = f"""{context}

You are a bankruptcy attorney drafting the "Change in Circumstances" section for a Motion to Extend Automatic Stay. Your response must be DETAILED and DATA-DRIVEN, citing specific numbers from the petitions and plan.

CRITICAL FORMAT REQUIREMENTS:
- DO NOT prefix with "Recommendation 1:", "Option A:", "(Income Focus):", or any labels
- Each statement should be DIRECTLY USABLE in a legal motion without any editing
- Start each statement directly with "The debtor's..." or "Since the prior case filing..."

CRITICAL INSTRUCTIONS - Be specific with numbers:
1. COMPARE INCOME: Extract and compare the debtor's monthly income from Schedule I in both the CURRENT and OLD petitions. State the exact dollar amounts (e.g., "Since the prior case filing, the debtor's monthly income has increased from approximately $3,200 to an estimated $4,500, reflecting a $1,300 monthly increase").

2. COMPARE EXPENSES: Extract and compare monthly expenses from Schedule J. Identify specific expense categories that changed (e.g., "Monthly rent decreased from $1,800 to $1,400, and car payment was eliminated, reducing total expenses by $650 per month").

3. CALCULATE NET DISPOSABLE INCOME: Show the math - Current Income minus Current Expenses = Net Disposable Income. Compare to the prior case.

4. REFERENCE THE PLAN PAYMENT: Use the exact plan payment amount from the Chapter 13 Plan and demonstrate mathematically how the debtor can now afford it (e.g., "With a net disposable income of $850/month, the debtor can comfortably afford the proposed plan payment of $750/month with a $100 cushion").

5. If specific numbers are not available in the context, use reasonable estimates based on available information, but clearly frame them as approximations.

FORMAT: Each recommendation should be 3-5 sentences, include at least 2-3 specific dollar amounts, and demonstrate clear mathematical reasoning for why circumstances have improved.

Generate exactly 3 recommendation options, each taking a slightly different analytical angle (income focus, expense focus, overall financial stability).
Return as a JSON array of exactly 3 strings."""

        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            json_match = re.search(r'\[.*?\]', content, re.DOTALL)
            if json_match:
                chips = json.loads(json_match.group())
                if isinstance(chips, list) and len(chips) >= 3:
                    print(f"{self.GREEN}  ✓ Generated {len(chips[:3])} ChangeInCircum chips:{self.RESET}")
                    for i, chip in enumerate(chips[:3]):
                        print(f"{self.GREEN}    [{i + 1}] {chip}{self.RESET}")
                    return chips[:3]

            return [
                "The debtor's financial circumstances have materially changed since the dismissal of the prior case, with stable employment income now sufficient to fund the proposed Chapter 13 plan.",
                "The debtor has secured consistent employment and restructured household expenses, resulting in adequate disposable income to maintain timely plan payments.",
                "The debtor's current financial situation demonstrates improved stability, with monthly income and reduced expenses providing sufficient funds to successfully complete the proposed plan.",
            ]

        except Exception as e:
            print(f"{self.RED}  Error generating ChangeInCircum chips: {e}{self.RESET}")
            return [
                "The debtor's financial circumstances have materially changed since the dismissal of the prior case, with stable employment income now sufficient to fund the proposed Chapter 13 plan.",
                "The debtor has secured consistent employment and restructured household expenses, resulting in adequate disposable income to maintain timely plan payments.",
                "The debtor's current financial situation demonstrates improved stability, with monthly income and reduced expenses providing sufficient funds to successfully complete the proposed plan.",
            ]

    def _generate_dismissal_reason_chips(self, trustees_reason: str, change_in_circum_chips: List[str]) -> List[str]:
        """
        Generate dismissal reason recommendation chips.

        This is generated SECOND, using:
        - trustees_reason (technical reason for dismissal)
        - change_in_circum_chips (already generated, to ensure alignment)

        The prompt: "Provided to you is the technical reason why the last case was dismissed,
        please come up with 3 reasons why our firm would say this happened to the Debtor..."
        """
        print(f"\n{self.CYAN}{'=' * 70}{self.RESET}")
        print(f"{self.YELLOW}[AI] Generating DismissalReason recommendations (STEP 2)...{self.RESET}")
        print(f"{self.CYAN}{'=' * 70}{self.RESET}")
        print(f"{self.GREEN}[DISMISSAL REASON CHIPS - DERIVED FROM]{self.RESET}")
        print(f"{self.GREEN}  • TrusteeReason (technical reason): {trustees_reason}{self.RESET}")
        print(f"{self.GREEN}  • ChangeInCircum chips (for alignment): {len(change_in_circum_chips)} chips generated in Step 1{self.RESET}")
        print(f"{self.GREEN}[PROMPT] \"Provided to you is the technical reason why the last case was dismissed,{self.RESET}")
        print(f"{self.GREEN}         please come up with 3 reasons why our firm would say this happened to the Debtor...\"{self.RESET}")

        # Format change in circum chips for context
        change_context = "\n".join([f"- {chip}" for chip in change_in_circum_chips])

        prompt = f"""TECHNICAL REASON FOR DISMISSAL (from Trustee):
{trustees_reason}

CHANGE IN CIRCUMSTANCES (use as context to ensure alignment):
{change_context}

Provided to you is the technical reason why the last case was dismissed, please come up with 3 reasons why our firm would say this happened to the Debtor.

For example:
- Their income had decreased
- They lost their job
- They were simply unable to keep up with their expenses due to low income

Something that aligns with an excuse for the technical reason.

Make sure the dismissal reasons work well with the Change in Circumstances provided above (they should be consistent - if circumstances improved, explain why they were worse before).

Generate exactly 3 brief recommendation options (2-4 sentences max each).
Return as a JSON array of exactly 3 strings."""

        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            json_match = re.search(r'\[.*?\]', content, re.DOTALL)
            if json_match:
                chips = json.loads(json_match.group())
                if isinstance(chips, list) and len(chips) >= 3:
                    print(f"{self.GREEN}  ✓ Generated {len(chips[:3])} DismissalReason chips:{self.RESET}")
                    for i, chip in enumerate(chips[:3]):
                        print(f"{self.GREEN}    [{i + 1}] {chip}{self.RESET}")
                    return chips[:3]

            return [
                "The debtor experienced a temporary reduction in income that prevented plan payments.",
                "The debtor faced unexpected expenses that disrupted their ability to maintain payments.",
                "The debtor's employment situation changed, causing a temporary financial hardship.",
            ]

        except Exception as e:
            print(f"{self.RED}  Error generating DismissalReason chips: {e}{self.RESET}")
            return [
                "The debtor experienced a temporary reduction in income that prevented plan payments.",
                "The debtor faced unexpected expenses that disrupted their ability to maintain payments.",
                "The debtor's employment situation changed, causing a temporary financial hardship.",
            ]

    def extract_payload(
        self,
        user_hint: Optional[str] = None,
        prefilled: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Extract motion extend payload using the new optimized flow.

        Args:
            user_hint: Optional hint for extraction.
            prefilled: Optional dict with pre-filled values from user input.
                       Used when resuming extraction after intermediate input.
                       Keys: dismissed_case_number, trustees_reason

        Returns:
            Dict with status and payload/error information.
            status can be: "success", "needs_input", "failed"
        """
        prefilled = prefilled or {}
        print(f"\n{self.BLUE}╔══════════════════════════════════════════════════════════════╗{self.RESET}")
        print(f"{self.BLUE}║  MOTION TO EXTEND - PAYLOAD EXTRACTION                       ║{self.RESET}")
        print(f"{self.BLUE}╚══════════════════════════════════════════════════════════════╝{self.RESET}")

        try:
            pdf_results: Dict[str, str] = {}
            print(f"\n{self.CYAN}[STEP 1] Extracting petition (PDF) fields...{self.RESET}")
            for field in self.pdf_fields:
                print(f"  Extracting {field}...")
                query = self._get_optimized_query(field, user_hint)
                result = self._extract_single_field(field, query)
                pdf_results[field] = result
                print(f"    {field}: {result}")

            debtor_name = pdf_results.get("debtor_name_extend", "N/A")
            case_no = self._extract_single_field("case_number_extend", "Case number with judge initial")
            if case_no == "N/A":
                case_no = self._find_case_number_from_gmail(debtor_name)
            print(f"  case_number: {case_no}")

            chapter = self._extract_single_field("chapter_extend", "chapter case details")
            print(f"  chapter: {chapter}")

            court_division = self._extract_single_field("court_division_extend", "hearing notices courthouse division")
            print(f"  court_division: {court_division}")

            # Check if dismissed_case_number was provided via prefilled (user input)
            if prefilled.get("dismissed_case_number"):
                dismissed_case_number = prefilled["dismissed_case_number"]
                print(f"{self.GREEN}  Dismissed case number (user provided): {dismissed_case_number}{self.RESET}")
            else:
                dismissed_result = self._extract_dismissed_case_from_petition()

                if dismissed_result.get("status") == "needs_input":
                    return {
                        "status": "needs_input",
                        "missing_field": "prior_case_info",
                        "missing_fields": ["dismissed_case_number", "docket_entry_no", "dismissal_date"],
                        "message": "We were unable to locate a prior bankruptcy for this client. Please provide the prior case details.",
                        "partial_payload": {
                            "court_district": pdf_results.get("court_district_extend", "N/A"),
                            "petition_date": pdf_results.get("petition_date_extend", "N/A"),
                            "debtor_name": debtor_name,
                            "case_no": case_no,
                            "chapter": chapter,
                            "court_division": court_division,
                        },
                    }

                dismissed_case_number = dismissed_result.get("dismissed_case_number")
                print(f"{self.GREEN}  Dismissed case number: {dismissed_case_number}{self.RESET}")

            # Check if trustees_reason was provided via prefilled (user input)
            if prefilled.get("trustees_reason"):
                print(f"{self.GREEN}  Trustees reason (user provided): {prefilled['trustees_reason']}{self.RESET}")
                extracted_fields = {
                    "dismissal_date": prefilled.get("dismissal_date", "N/A"),
                    "trustees_reason": prefilled["trustees_reason"],
                    "docket_entry_no": prefilled.get("docket_entry_no", "N/A"),
                }
            else:
                order_dismissing_email = self._search_order_dismissing_with_fallback(dismissed_case_number)

                if not order_dismissing_email:
                    return {
                        "status": "needs_input",
                        "missing_field": "trustees_reason",
                        "message": "It looks like we couldn't find this dismissed case in your courtmail. It's likely that you didn't represent this client in their previous case. Please let us know what the trustee put as the reason for dismissal.",
                        "partial_payload": {
                            "court_district": pdf_results.get("court_district_extend", "N/A"),
                            "petition_date": pdf_results.get("petition_date_extend", "N/A"),
                            "debtor_name": debtor_name,
                            "case_no": case_no,
                            "chapter": chapter,
                            "court_division": court_division,
                            "dismissed_case_number": dismissed_case_number,
                            "docket_entry_no": prefilled.get("docket_entry_no", "N/A"),
                            "dismissal_date": prefilled.get("dismissal_date", "N/A"),
                        },
                    }

                extracted_fields = self._extract_from_order_dismissing_email(order_dismissing_email)

            petition_date = pdf_results.get("petition_date_extend", "N/A")
            petition_date_plus_30 = self._calculate_petition_date_plus_30(petition_date)

            final_payload = {
                "court_district": pdf_results.get("court_district_extend", "N/A"),
                "petition_date": petition_date,
                "debtor_name": debtor_name,
                "case_no": case_no,
                "chapter": chapter,
                "court_division": court_division,
                "dismissed_case_number": dismissed_case_number,
                "dismissal_date": extracted_fields.get("dismissal_date", "N/A"),
                "trustees_reason": extracted_fields.get("trustees_reason", "N/A"),
                "docket_entry_no": extracted_fields.get("docket_entry_no", "N/A"),
                "dismissal_reason": "N/A",
                "change_in_circum": "N/A",
                "extension_type": "regular",
                "petition_date_plus_30": petition_date_plus_30,
            }

            print(f"\n{self.GREEN}╔══════════════════════════════════════════════════════════════╗{self.RESET}")
            print(f"{self.GREEN}║  EXTRACTION COMPLETE                                         ║{self.RESET}")
            print(f"{self.GREEN}╚══════════════════════════════════════════════════════════════╝{self.RESET}")
            print(f"{self.GREEN}Final payload: {json.dumps(final_payload, indent=2)}{self.RESET}")

            return {
                "status": "success",
                "payload": final_payload,
                "agent_type": "gmail_motion_extend_agent_revamped",
            }

        except Exception as e:
            print(f"{self.RED}ERROR: {str(e)}{self.RESET}")
            return {
                "status": "failed",
                "error": str(e),
                "message": "Error during motion extend payload extraction",
                "agent_type": "gmail_motion_extend_agent_revamped",
            }

    def extract_payload_with_recommendations(self, user_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract payload AND generate AI recommendations in one call.
        This is the main entry point for the new extend flow.
        """
        payload_result = self.extract_payload(user_hint)

        if payload_result.get("status") != "success":
            return payload_result

        payload = payload_result.get("payload", {})
        trustees_reason = payload.get("trustees_reason", "N/A")
        case_no = payload.get("case_no", "")
        dismissed_case_number = payload.get("dismissed_case_number", "")

        current_petition_context = self._get_current_petition_schedule_context()
        chapter_13_plan_context, has_plan = self._get_chapter_13_plan_context(case_no)

        recommendations = self.generate_recommendations(
            trustees_reason=trustees_reason,
            current_petition_context=current_petition_context,
            chapter_13_plan_context=chapter_13_plan_context,
            dismissed_case_number=dismissed_case_number,
        )

        return {
            "status": "success",
            "payload": payload,
            "recommendations": {
                "dismissal_reason_chips": recommendations.dismissal_reason_chips,
                "change_in_circum_chips": recommendations.change_in_circum_chips,
                "has_old_petition": recommendations.has_old_petition,
                "has_chapter_13_plan": recommendations.has_chapter_13_plan,
                "context_warnings": recommendations.context_warnings,
            },
            "agent_type": "gmail_motion_extend_agent_revamped",
        }
