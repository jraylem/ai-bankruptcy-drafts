from typing import Optional, Dict, Any, List
import json
from pydantic import BaseModel, Field
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model


# ============================================================================
# MOTION TO MODIFY - Structured Output Schemas
# ============================================================================

# Single creditor from POC email
class CreditorClaim(BaseModel):
    """Single creditor extracted from a Proof of Claim email."""
    creditor_name: str = Field(description="The name of the creditor/company filing the claim")
    claim_number: str = Field(description="The POC/Claim number (e.g., '5' or '12')")
    amount_claimed: str = Field(description="The total amount claimed (e.g., '$12,500.00')")


# List of creditors (used for fallback extraction)
class CreditorClaimList(BaseModel):
    """List of creditors extracted from POC emails."""
    creditors: List[CreditorClaim] = Field(default_factory=list, description="All creditors found in POC emails")


# Order Confirming email details (used for separate extraction)
class OrderConfirmingDetails(BaseModel):
    """Details extracted from Order Confirming Chapter 13 Plan email."""
    docket_confirm: Optional[str] = Field(default=None, description="Document Number of the Order Confirming email itself")
    docket_plan: Optional[str] = Field(default=None, description="Docket number of the Plan being confirmed, from [XX] brackets in Docket Text")
    confirm_date: Optional[str] = Field(default=None, description="Date order was entered, format: 'Month DD, YYYY'")


# Combined extraction for ALL Gmail fields in ONE call
class ModifyGmailExtraction(BaseModel):
    """All fields extracted from Gmail emails for Motion to Modify."""
    # From any court email
    case_no: str = Field(description="Case number with judge initials (e.g., '25-13263-SMG')")
    chapter: str = Field(description="Bankruptcy chapter number (e.g., '13')")
    court_division: str = Field(description="Court division (e.g., 'Miami Division')")

    # From "Order Confirming Chapter 13 Plan" email
    docket_confirm: Optional[str] = Field(default=None, description="Document Number of the Order Confirming email itself")
    docket_plan: Optional[str] = Field(default=None, description="Docket number of the Plan being confirmed, found in brackets like [33] in Docket Text")
    confirm_date: Optional[str] = Field(default=None, description="Date order was entered, format: 'Month DD, YYYY'")

    # From "Notice of Delinquency" email (if applicable)
    date_delinquent: Optional[str] = Field(default=None, description="Date from Notice of Delinquency, format: 'Month DD, YYYY'")
    docket_notice: Optional[str] = Field(default=None, description="Document Number from Notice of Delinquency email")

    # From "Proof of Claim" emails
    creditors: List[CreditorClaim] = Field(default_factory=list, description="All creditors from POC emails")

# ============================================================================

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    motion_modify_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_MODIFY_GMAIL,
)
from ..extractor import search_and_extract_proof_of_claim_emails, search_and_extract_subject_email


# Called by: service.generate_payload_modify_for_session_gmail (L2)
#   -> routes/service_stream.py
class GmailMotionModifyAgent:
    """
    Gmail-backed Motion Modify Agent.

    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for district/debtor
    - Gmail vectorstore (gmail_<session_id>) for case number (with judge initial),
      chapter, confirm date, docket entries, delinquency info.

    Supports three modification types:
    - delinquent: Debtor fell behind on plan payments
    - creditor_alteration: Creditor(s) altered terms
    - both: Combination of delinquent and creditor alteration
    """

    def __init__(self, session_id: Optional[str] = None, memory_saver: MemorySaver = None, modification_type: str = "delinquent"):
        self.api_key = settings.ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("Anthropic API key not found in config. Please check your .env file.")

        self.session_id = session_id
        self.memory_saver = memory_saver or MemorySaver()
        self.modification_type = modification_type

        self.llm = init_chat_model(
            CLAUDE_MODEL_FAST,
            model_provider=CLAUDE_PROVIDER,
            api_key=self.api_key,
            temperature=CLAUDE_TEMPERATURE,
        )

        # Petition-based fields (always extracted via vectorstore)
        self.pdf_fields = ["court_district_modify", "debtor_name_modify"]

        # Gmail-based fields extracted via vectorstore (basic case info)
        self.common_gmail_fields = [
            "case_no_modify",
            "court_division_modify",
            "chapter_modify",
            "confirm_date_modify",
            "docket_confirm_modify",
            "docket_plan_modify",
        ]

        # Delinquent-specific fields
        self.delinquent_gmail_fields = [
            "date_delinquent_modify",
            "docket_notice_modify",
        ]

        # Build gmail_fields based on modification_type
        self.gmail_fields = list(self.common_gmail_fields)
        if self.modification_type in ("delinquent", "both"):
            self.gmail_fields.extend(self.delinquent_gmail_fields)

        # Static fields for modify motion
        self.static_fields = {
            "delinquent_reason": "N/A",
            "creditors": "N/A",
            "claim_slot": "N/A",
            "has_have": "has",
            "s_plural": "",
        }

    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "court_district_modify": "United States Bankruptcy Court for the",
            "debtor_name_modify": "Your full name Debtor 1",
            "case_no_modify": "Case number with judge initial from emails",
            "court_division_modify": "hearing notices courthouse address",
            "chapter_modify": "chapter case details",
            "confirm_date_modify": "Order Confirming Chapter 13 Plan",
            "docket_confirm_modify": "Order Confirming Chapter 13 Plan docket number",
            "docket_plan_modify": "Chapter 13 Plan docket number",
            "date_delinquent_modify": "delinquent date plan payments",
            "docket_notice_modify": "Trustee's Notice of Delinquency docket number",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query

    def _extract_single_field(self, field_name: str, query: str) -> str:
        max_retries = 2

        for attempt in range(max_retries + 1):
            try:
                tools = motion_modify_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_MODIFY_GMAIL[field_name],
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

    def _find_case_number_from_gmail(self, debtor_name: str) -> str:
        """
        Fallback: Find case number from Gmail using debtor name.
        Searches for court emails containing the debtor name and extracts case number.
        """
        import re
        from ..auth import get_gmail_service

        CYAN = "\033[96m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RESET = "\033[0m"

        print(f"{CYAN}[FALLBACK] Finding case number from Gmail using debtor name...{RESET}")

        if not debtor_name or debtor_name == "N/A":
            print(f"{YELLOW}  No debtor name available{RESET}")
            return "N/A"

        try:
            gmail_service = get_gmail_service()

            # Try direct court emails first, then fallback to all emails (for forwarded)
            queries = [
                f'from:uscourts.gov "{debtor_name}"',  # Direct court emails
                f'"{debtor_name}"',                     # Fallback: forwarded emails
            ]

            message_refs = []
            for query in queries:
                print(f"{CYAN}  Query: {query}{RESET}")
                response = gmail_service.users().messages().list(
                    userId="me", q=query, maxResults=5
                ).execute()
                message_refs = response.get("messages", []) or []
                if message_refs:
                    print(f"{GREEN}  Found {len(message_refs)} emails{RESET}")
                    break
                print(f"{YELLOW}  No results, trying fallback...{RESET}")

            if not message_refs:
                print(f"{YELLOW}  No emails found{RESET}")
                return "N/A"

            # Check each email for case number pattern
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

                # Extract case number pattern: XX-XXXXX-XXX (e.g., 24-21679-SMG)
                case_match = re.search(r"(\d{2}-\d{4,5}-[A-Z]{2,3})", subject)
                if case_match:
                    case_no = case_match.group(1)
                    print(f"{GREEN}  Found case number: {case_no}{RESET}")
                    return case_no

            print(f"{YELLOW}  No case number found in email subjects{RESET}")
            return "N/A"

        except Exception as e:
            print(f"{YELLOW}  Error: {e}{RESET}")
            return "N/A"

    def _compare_order_emails(self, case_number: str) -> Dict[str, Any]:
        """
        Compare "Order Confirming Chapter 13 Plan" vs "Order on Motion to Modify Plan"
        to determine which template to use and extract appropriate data.

        Uses direct Gmail search WITHOUT fallbacks to ensure exact matching.

        Returns:
            {
                "use_granting_template": bool,  # True if "Order on Motion to Modify" is more recent
                "winning_email": dict,          # The more recent email
                "winning_type": str,            # "confirming" or "granting"
            }
        """
        from email.utils import parsedate_to_datetime
        from ..auth import get_gmail_service

        BLUE = "\033[94m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RED = "\033[91m"
        RESET = "\033[0m"

        print(f"\n{BLUE}╔══════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{BLUE}║  TEMPLATE SELECTION - Comparing Order Emails                 ║{RESET}")
        print(f"{BLUE}╚══════════════════════════════════════════════════════════════╝{RESET}")

        gmail_service = get_gmail_service()

        def fetch_order_email(subject_title: str) -> tuple:
            """Fetch order email with exact subject match (no fallback)."""
            query = f'"{case_number}" subject:"{subject_title}"'
            print(f"{YELLOW}  Query: {query}{RESET}")

            response = gmail_service.users().messages().list(
                userId="me", q=query, maxResults=10
            ).execute()

            message_refs = response.get("messages", []) or []
            if not message_refs:
                return None, None

            # Get most recent (first in list)
            msg = gmail_service.users().messages().get(
                userId="me", id=message_refs[0]["id"], format="full"
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
            email_data = {"subject": subject, "date": date_str, "body": body}

            try:
                parsed_date = parsedate_to_datetime(date_str)
            except Exception:
                parsed_date = None

            return email_data, parsed_date

        # Fetch "Order Confirming Chapter 13 Plan" (exact match)
        print(f"{YELLOW}[1] Searching for 'Order Confirming Chapter 13 Plan'...{RESET}")
        confirming_email, confirming_date = fetch_order_email("Order Confirming Chapter 13 Plan")
        if confirming_email:
            print(f"{GREEN}  ✓ Found: {confirming_email.get('subject', '')[:60]}...{RESET}")
            print(f"{GREEN}  Date: {confirming_date}{RESET}")
        else:
            print(f"{RED}  ✗ Not found{RESET}")

        # Fetch "Order on Motion to Modify Plan" (exact match)
        print(f"{YELLOW}[2] Searching for 'Order on Motion to Modify Plan'...{RESET}")
        granting_email, granting_date = fetch_order_email("Order on Motion to Modify Plan")
        if granting_email:
            print(f"{GREEN}  ✓ Found: {granting_email.get('subject', '')[:60]}...{RESET}")
            print(f"{GREEN}  Date: {granting_date}{RESET}")
        else:
            print(f"{RED}  ✗ Not found{RESET}")

        # Determine which is more recent
        use_granting = False
        winning_email = None
        winning_type = "confirming"

        if granting_email and granting_date:
            if confirming_email and confirming_date:
                # Both exist - compare dates
                if granting_date > confirming_date:
                    use_granting = True
                    winning_email = granting_email
                    winning_type = "granting"
                    print(f"{BLUE}[RESULT] 'Order on Motion to Modify' is MORE RECENT → using GRANTING template{RESET}")
                else:
                    winning_email = confirming_email
                    winning_type = "confirming"
                    print(f"{BLUE}[RESULT] 'Order Confirming' is MORE RECENT → using REGULAR template{RESET}")
            else:
                # Only granting exists
                use_granting = True
                winning_email = granting_email
                winning_type = "granting"
                print(f"{BLUE}[RESULT] Only 'Order on Motion to Modify' found → using GRANTING template{RESET}")
        elif confirming_email:
            # Only confirming exists
            winning_email = confirming_email
            winning_type = "confirming"
            print(f"{BLUE}[RESULT] Only 'Order Confirming' found → using REGULAR template{RESET}")
        else:
            print(f"{YELLOW}[RESULT] No order emails found{RESET}")

        print(f"{BLUE}══════════════════════════════════════════════════════════════{RESET}")

        return {
            "use_granting_template": use_granting,
            "winning_email": winning_email,
            "winning_type": winning_type,
        }

    def _find_most_recent_plan_filed_by_debtor(self, case_number: str) -> str:
        """
        Find the most recent "Chapter 13 Plan Filed by Debtor" email and extract its docket number.
        Used when "Order on Motion to Modify" is the most recent order (doesn't contain plan docket).

        Extracts docket from body: "Document Number: XX"
        """
        import re
        from ..auth import get_gmail_service

        MAGENTA = "\033[95m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RESET = "\033[0m"

        print(f"\n{MAGENTA}[PLAN SEARCH] Finding most recent 'Chapter 13 Plan Filed by Debtor'...{RESET}")

        try:
            gmail_service = get_gmail_service()
            query = f'"{case_number}" subject:"Chapter 13 Plan"'
            print(f"{MAGENTA}  Query: {query}{RESET}")

            response = gmail_service.users().messages().list(
                userId="me", q=query, maxResults=30
            ).execute()

            message_refs = response.get("messages", []) or []
            print(f"{MAGENTA}  Found {len(message_refs)} emails{RESET}")

            if not message_refs:
                return "N/A"

            valid_plans = []
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

                # Skip order emails
                subject_lower = subject.lower()
                if "order confirming" in subject_lower or "order granting" in subject_lower or "order on motion" in subject_lower:
                    print(f"{YELLOW}  Skipping order email: {subject[:50]}...{RESET}")
                    continue

                body = self._extract_email_body(payload)
                if not body:
                    print(f"{YELLOW}  Skipping (no body): {subject[:50]}...{RESET}")
                    continue

                # Extract docket from body: "Document Number: XX" or "*Document Number:* XX"
                internal_date = int(msg.get("internalDate", 0))
                doc_match = re.search(r"Document\s*Number\D*(\d+)", body, re.IGNORECASE)
                if doc_match:
                    docket_num = doc_match.group(1)
                    valid_plans.append({
                        "subject": subject,
                        "docket": docket_num,
                        "internal_date": internal_date,
                    })
                    print(f"{GREEN}  ✓ Valid plan: {subject[:60]}... → Docket: {docket_num}{RESET}")
                else:
                    print(f"{YELLOW}  No Document Number in body: {subject[:50]}...{RESET}")

            if not valid_plans:
                print(f"{YELLOW}  ✗ No valid plan emails found{RESET}")
                return "N/A"

            # Sort by date descending (most recent first)
            valid_plans.sort(key=lambda x: x["internal_date"], reverse=True)
            most_recent = valid_plans[0]
            print(f"{GREEN}  ★ Most recent plan: {most_recent['subject'][:50]}... → Docket: {most_recent['docket']}{RESET}")

            return most_recent["docket"]

        except Exception as e:
            print(f"{YELLOW}  ✗ Error finding plan: {e}{RESET}")
            return "N/A"

    def _extract_all_gmail_fields_combined(self, case_number: str) -> Dict[str, Any]:
        """
        Extract ALL Gmail fields in ONE LLM call by collecting relevant emails
        and passing them with labels to the LLM.

        Now includes template selection logic:
        - Compares "Order Confirming Chapter 13 Plan" vs "Order on Motion to Modify Plan"
        - Uses most recent for extraction
        - If "Order on Motion to Modify" is most recent, separately finds plan docket

        Returns dict with: case_no, chapter, court_division, docket_confirm, docket_plan,
        confirm_date, date_delinquent, docket_notice, creditors (list), use_granting_template (bool)
        """
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        YELLOW = "\033[93m"
        RESET = "\033[0m"

        print(f"\n{CYAN}╔══════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{CYAN}║  COMBINED GMAIL EXTRACTION - With Template Selection         ║{RESET}")
        print(f"{CYAN}╚══════════════════════════════════════════════════════════════╝{RESET}")

        # 1. Compare order emails to determine template type
        order_comparison = self._compare_order_emails(case_number)
        use_granting_template = order_comparison["use_granting_template"]
        winning_email = order_comparison["winning_email"]
        winning_type = order_comparison["winning_type"]

        emails_context = []

        # 2. Add the winning order email to context
        if winning_email:
            if winning_type == "confirming":
                emails_context.append(f"""
════════════════════════════════════════════════════════════════
EMAIL TYPE: Order Confirming Chapter 13 Plan
PURPOSE: Extract docket_confirm (Document Number of this email), docket_plan (number in [XX] brackets - the plan being confirmed), confirm_date, case_no, chapter
════════════════════════════════════════════════════════════════
SUBJECT: {winning_email.get('subject', '')}
DATE: {winning_email.get('date', '')}

BODY:
{winning_email.get('body', '')[:2000]}
""")
            else:  # granting
                emails_context.append(f"""
════════════════════════════════════════════════════════════════
EMAIL TYPE: Order Granting Motion to Modify Plan
PURPOSE: Extract docket_confirm (Document Number of this email), confirm_date, case_no, chapter
NOTE: docket_plan will be extracted separately from "Chapter 13 Plan Filed by Debtor" email
════════════════════════════════════════════════════════════════
SUBJECT: {winning_email.get('subject', '')}
DATE: {winning_email.get('date', '')}

BODY:
{winning_email.get('body', '')[:2000]}
""")

        # 3. Fetch "Notice of Delinquency" email (if delinquent or both)
        if self.modification_type in ("delinquent", "both"):
            print(f"{YELLOW}[3] Fetching Notice of Delinquency email...{RESET}")
            delinquency_email = search_and_extract_subject_email(
                case_number=case_number,
                subject_title="Notice of Delinquency",
                oldest=False,
            )
            if delinquency_email:
                emails_context.append(f"""
════════════════════════════════════════════════════════════════
EMAIL TYPE: Notice of Delinquency
PURPOSE: Extract date_delinquent (date entered), docket_notice (Document Number)
════════════════════════════════════════════════════════════════
SUBJECT: {delinquency_email.get('subject', '')}
DATE: {delinquency_email.get('date', '')}

BODY:
{delinquency_email.get('body', '')[:1500]}
""")
                print(f"{GREEN}  ✓ Found: {delinquency_email.get('subject', '')[:50]}...{RESET}")
            else:
                print(f"{YELLOW}  ✗ Not found{RESET}")

        if not emails_context:
            print(f"{YELLOW}[!] No emails found, returning defaults{RESET}")
            return {
                "case_no": "N/A", "chapter": "N/A", "court_division": "N/A",
                "docket_confirm": "N/A", "docket_plan": "N/A", "confirm_date": "N/A",
                "date_delinquent": "N/A", "docket_notice": "N/A", "creditors": [],
                "use_granting_template": False
            }

        # 4. Build combined prompt based on order type
        all_emails = "\n".join(emails_context)

        if winning_type == "confirming":
            prompt = f"""You are extracting information from bankruptcy court emails for a Motion to Modify Plan.

{all_emails}

════════════════════════════════════════════════════════════════
EXTRACTION TASK
════════════════════════════════════════════════════════════════
Extract the following fields from the emails above:

FROM ANY COURT EMAIL:
- case_no: Case number with judge initials (e.g., "25-13263-SMG")
- chapter: Bankruptcy chapter (e.g., "13")
- court_division: Court division (e.g., "Miami Division")

FROM "Order Confirming Chapter 13 Plan" EMAIL:
- docket_confirm: The Document Number of the Order Confirming email itself
- docket_plan: The docket number of the Plan BEING CONFIRMED (found in brackets like [33] in Docket Text, e.g., "Order Confirming (Re: [33] First Amended Chapter 13 Plan...)" means docket_plan = "33")
- confirm_date: Date the order was entered, format as "Month DD, YYYY" (e.g., "July 02, 2025")

FROM "Notice of Delinquency" EMAIL (if present):
- date_delinquent: Date entered, format as "Month DD, YYYY"
- docket_notice: Document Number

Use empty string "" for fields not found. Leave creditors as empty list (extracted separately)."""
        else:
            # Granting type - don't extract docket_plan from this email (we'll get it separately)
            prompt = f"""You are extracting information from bankruptcy court emails for a Motion to Modify Plan.

{all_emails}

════════════════════════════════════════════════════════════════
EXTRACTION TASK
════════════════════════════════════════════════════════════════
Extract the following fields from the emails above:

FROM ANY COURT EMAIL:
- case_no: Case number with judge initials (e.g., "25-13263-SMG")
- chapter: Bankruptcy chapter (e.g., "13")
- court_division: Court division (e.g., "Miami Division")

FROM "Order Granting Motion to Modify Plan" EMAIL:
- docket_confirm: The Document Number of this order email itself
- confirm_date: Date the order was entered, format as "Month DD, YYYY" (e.g., "July 02, 2025")
- docket_plan: Leave empty (will be extracted separately)

FROM "Notice of Delinquency" EMAIL (if present):
- date_delinquent: Date entered, format as "Month DD, YYYY"
- docket_notice: Document Number

Use empty string "" for fields not found. Leave creditors as empty list (extracted separately)."""

        print(f"{CYAN}[LLM] Sending combined context to LLM...{RESET}")

        try:
            structured_llm = self.llm.with_structured_output(ModifyGmailExtraction)
            result = structured_llm.invoke(prompt)

            extracted = {
                "case_no": result.case_no.strip() or "N/A",
                "chapter": result.chapter.strip() or "N/A",
                "court_division": result.court_division.strip() or "N/A",
                "docket_confirm": (result.docket_confirm or "").strip() or "N/A",
                "docket_plan": (result.docket_plan or "").strip() or "N/A",
                "confirm_date": (result.confirm_date or "").strip() or "N/A",
                "date_delinquent": (result.date_delinquent or "").strip() or "N/A",
                "docket_notice": (result.docket_notice or "").strip() or "N/A",
                "creditors": [
                    {"creditor_name": c.creditor_name, "claim_number": c.claim_number, "amount_claimed": c.amount_claimed}
                    for c in result.creditors
                ] if result.creditors else [],
                "use_granting_template": use_granting_template,
            }

            # If granting type, we need to find docket_plan separately
            if use_granting_template:
                print(f"{YELLOW}[4] Granting template - finding docket_plan from 'Chapter 13 Plan Filed by Debtor'...{RESET}")
                docket_plan = self._find_most_recent_plan_filed_by_debtor(case_number)
                extracted["docket_plan"] = docket_plan
                print(f"{GREEN}  docket_plan (from plan filing): {docket_plan}{RESET}")

            print(f"{GREEN}[LLM] ✓ Extraction complete:{RESET}")
            print(f"{GREEN}  case_no={extracted['case_no']}, chapter={extracted['chapter']}, division={extracted['court_division']}{RESET}")
            print(f"{GREEN}  docket_confirm={extracted['docket_confirm']}, docket_plan={extracted['docket_plan']}, confirm_date={extracted['confirm_date']}{RESET}")
            print(f"{GREEN}  use_granting_template={extracted['use_granting_template']}{RESET}")
            if self.modification_type in ("delinquent", "both"):
                print(f"{GREEN}  date_delinquent={extracted['date_delinquent']}, docket_notice={extracted['docket_notice']}{RESET}")
            if extracted['creditors']:
                print(f"{GREEN}  creditors: {len(extracted['creditors'])} found{RESET}")
                for c in extracted['creditors']:
                    print(f"{GREEN}    • {c['creditor_name']} | POC #{c['claim_number']} | {c['amount_claimed']}{RESET}")

            print(f"{CYAN}══════════════════════════════════════════════════════════════{RESET}")
            return extracted

        except Exception as e:
            print(f"Error in combined extraction: {e}")
            return {
                "case_no": "N/A", "chapter": "N/A", "court_division": "N/A",
                "docket_confirm": "N/A", "docket_plan": "N/A", "confirm_date": "N/A",
                "date_delinquent": "N/A", "docket_notice": "N/A", "creditors": [],
                "use_granting_template": False
            }

    def _fetch_poc_emails(self, case_number: str) -> List[Dict[str, str]]:
        """Fetch Proof of Claim emails for combined extraction."""
        from ..auth import get_gmail_service

        MAGENTA = "\033[95m"
        GREEN = "\033[92m"
        RED = "\033[91m"
        RESET = "\033[0m"

        try:
            gmail_service = get_gmail_service()
            query = f'"{case_number}"'
            print(f"{MAGENTA}  [POC-FETCH] Gmail query: {query}{RESET}")

            response = gmail_service.users().messages().list(
                userId="me", q=query, maxResults=50
            ).execute()

            message_refs = response.get("messages", []) or []
            print(f"{MAGENTA}  [POC-FETCH] Found {len(message_refs)} emails with case number{RESET}")

            if not message_refs:
                print(f"{RED}  [POC-FETCH] ✗ No emails found{RESET}")
                return []

            poc_emails = []

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

                if "proof of claim" not in subject.lower():
                    continue

                print(f"{GREEN}  [POC-FETCH] ✓ POC email: {subject[:60]}...{RESET}")
                body = self._extract_email_body(payload)
                if body:
                    poc_emails.append({"subject": subject, "body": body})
                else:
                    print(f"{RED}  [POC-FETCH] ✗ No body for: {subject[:50]}{RESET}")

            print(f"{MAGENTA}  [POC-FETCH] Total POC emails collected: {len(poc_emails)}{RESET}")
            return poc_emails

        except Exception as e:
            print(f"{RED}  [POC-FETCH] ✗ Error: {e}{RESET}")
            return []

    def _extract_available_creditors(self, case_number: str) -> List[Dict[str, str]]:
        """
        Extract available creditors from Proof of Claim emails.
        Uses shared extractor first, falls back to direct Gmail search if needed.
        """
        # ANSI color codes
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        CYAN = "\033[96m"
        RESET = "\033[0m"

        # Try shared extractor first
        try:
            print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
            print(f"{CYAN}[POC EXTRACTION] Starting for case: {case_number}{RESET}")
            print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")

            print(f"{YELLOW}[POC] Trying shared extractor (vectorstore)...{RESET}")
            claims = search_and_extract_proof_of_claim_emails(case_number)
            if claims:
                result = [
                    {
                        "creditor_name": c.get("creditor_name", ""),
                        "claim_number": c.get("claim_number", ""),
                        "amount_claimed": c.get("amount_claimed", ""),
                    }
                    for c in claims
                    if c.get("creditor_name")
                ]
                if result:
                    print(f"{GREEN}[POC] ✓ Found {len(result)} creditors via shared extractor{RESET}")
                    for i, c in enumerate(result):
                        print(f"{GREEN}  [{i+1}] {c.get('creditor_name')} | POC #{c.get('claim_number')} | {c.get('amount_claimed')}{RESET}")
                    print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
                    return result
            print(f"{YELLOW}[POC] Shared extractor returned nothing{RESET}")
        except Exception as e:
            print(f"{RED}[POC] ✗ Shared extractor failed: {e}{RESET}")

        # Fallback: Direct Gmail search with body validation
        print(f"{RED}[POC] ▶ FALLBACK: Direct Gmail search for POC emails...{RESET}")
        return self._fallback_extract_creditors(case_number)

    def _fallback_extract_creditors(self, case_number: str) -> List[Dict[str, str]]:
        """Fallback direct Gmail search for POC emails - passes all to LLM agent."""
        import json
        from ..auth import get_gmail_service

        # ANSI color codes
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        CYAN = "\033[96m"
        MAGENTA = "\033[95m"
        RESET = "\033[0m"

        try:
            gmail_service = get_gmail_service()
            # Search by case number only, filter by subject in code (case-insensitive)
            query = f'"{case_number}"'
            print(f"{MAGENTA}[POC-FALLBACK] Gmail query: {query}{RESET}")

            response = gmail_service.users().messages().list(
                userId="me", q=query, maxResults=50
            ).execute()

            message_refs = response.get("messages", []) or []
            print(f"{MAGENTA}[POC-FALLBACK] Found {len(message_refs)} emails with case number{RESET}")

            if not message_refs:
                print(f"{RED}[POC-FALLBACK] ✗ No POC emails found{RESET}")
                print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
                return []

            # Collect all POC emails with full context
            poc_emails = []
            for i, msg_ref in enumerate(message_refs):
                try:
                    msg = gmail_service.users().messages().get(
                        userId="me", id=msg_ref.get("id"), format="full"
                    ).execute()

                    payload = msg.get("payload", {}) or {}
                    headers = payload.get("headers", []) or []

                    subject = ""
                    date = ""
                    for h in headers:
                        name = h.get("name", "").lower()
                        if name == "subject":
                            subject = h.get("value", "")
                        elif name == "date":
                            date = h.get("value", "")

                    # Filter by subject: must contain "proof of claim" (case-insensitive)
                    if "proof of claim" not in subject.lower():
                        continue

                    body = self._extract_email_body(payload)
                    if not body:
                        print(f"{RED}[POC-FALLBACK] Skipping (no body): {subject[:50]}{RESET}")
                        continue

                    print(f"{YELLOW}[POC-FALLBACK] ✓ POC Email {i+1}: {subject[:60]}...{RESET}")
                    print(f"{CYAN}[POC-FALLBACK] Email {i+1} BODY:{RESET}")
                    print(f"{CYAN}{body[:1500]}{RESET}")
                    print(f"{CYAN}{'─' * 50}{RESET}")
                    poc_emails.append({
                        "email_number": i + 1,
                        "subject": subject,
                        "date": date,
                        "body": body[:2500]  # Limit body size
                    })

                except Exception as e:
                    print(f"{RED}[POC-FALLBACK] Error reading email: {e}{RESET}")
                    continue

            if not poc_emails:
                print(f"{RED}[POC-FALLBACK] ✗ No emails with readable content{RESET}")
                print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
                return []

            # Build formatted email content for agent
            emails_text = f"These are {len(poc_emails)} Proof of Claim emails found that might be related:\n\n"
            for email in poc_emails:
                emails_text += f"""
════════════════════════════════════════════════════════
EMAIL #{email['email_number']}
════════════════════════════════════════════════════════
SUBJECT: {email['subject']}
DATE: {email['date']}

BODY:
{email['body']}
"""

            print(f"{MAGENTA}[POC-FALLBACK] Sending {len(poc_emails)} emails to LLM for extraction...{RESET}")

            # Send to LLM agent with structured output
            prompt = f"""{emails_text}

════════════════════════════════════════════════════════
TASK
════════════════════════════════════════════════════════
From the emails above, extract ALL creditors with their Proof of Claim details.

For each creditor found, extract:
- creditor_name: The name of the creditor/company filing the claim
- claim_number: The POC/Claim number (just the number like "5" or "12")
- amount_claimed: The total amount claimed (with $ sign like "$12,500.00")

If a field is not found in an email, use empty string "".
Extract all unique creditors - do not include duplicates."""

            structured_llm = self.llm.with_structured_output(CreditorClaimList)
            result = structured_llm.invoke(prompt)

            # Convert Pydantic models to dicts
            creditors = [
                {
                    "creditor_name": c.creditor_name.strip(),
                    "claim_number": c.claim_number.strip(),
                    "amount_claimed": c.amount_claimed.strip(),
                }
                for c in result.creditors
                if c.creditor_name.strip()
            ]

            if creditors:
                print(f"{GREEN}[POC-FALLBACK] ✓ LLM extracted {len(creditors)} creditors:{RESET}")
                for c in creditors:
                    print(f"{GREEN}  • {c.get('creditor_name')} | POC #{c.get('claim_number')} | {c.get('amount_claimed')}{RESET}")
            else:
                print(f"{RED}[POC-FALLBACK] ✗ LLM found no creditors{RESET}")

            print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
            return creditors

        except Exception as e:
            print(f"{RED}[POC-FALLBACK] ✗ Failed: {e}{RESET}")
            print(f"{CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
            return []

    def _extract_email_body(self, payload: dict) -> str:
        """Extract plain text body from email payload."""
        import base64

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

        # Try direct body first
        body_data = payload.get("body", {}).get("data", "")
        if body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")

        # Try parts
        parts = payload.get("parts", [])
        if parts:
            return get_body_from_parts(parts)

        return ""

    def _extract_order_confirming_details(self, case_number: str) -> Dict[str, str]:
        """
        Extract ConfirmDate, DocketNumbConfirm, and DocketNumbPlan from the most recent
        'Order Confirming Chapter 13 Plan' email using LLM with structured output.

        The Order Confirming email contains:
        - Document Number: 40 (the order itself = docket_confirm)
        - Docket Text: "Order Confirming (Re: [33] Chapter 13 Plan..." = docket_plan (the plan being confirmed)
        """
        BLUE = "\033[94m"
        RESET = "\033[0m"

        try:
            email = search_and_extract_subject_email(
                case_number=case_number,
                subject_title="Order Confirming Chapter 13 Plan",
                oldest=False,
            )
            if not email:
                print(f"{BLUE}[ORDER CONFIRMING] No email found{RESET}")
                return {"confirm_date": "N/A", "docket_confirm": "N/A", "docket_plan": "N/A"}

            subject = email.get("subject", "")
            body = email.get("body", "")
            email_date = email.get("date", "")

            print(f"{BLUE}[ORDER CONFIRMING] Found email: {subject[:60]}...{RESET}")
            print(f"{BLUE}[ORDER CONFIRMING] Sending to LLM for extraction...{RESET}")

            prompt = f"""Extract the following information from this "Order Confirming Chapter 13 Plan" court email:

SUBJECT: {subject}
DATE: {email_date}

EMAIL BODY:
{body[:2500]}

Extract these fields:
1. docket_confirm: The "Document Number" of THIS email (the Order Confirming document itself). Look for "Document Number: XX"
2. docket_plan: The docket number of the Chapter 13 Plan that is BEING CONFIRMED. This is usually in the Docket Text in brackets like "[33]" referring to the original plan filing. Example: "Order Confirming (Re: [33] First Amended Chapter 13 Plan..." means docket_plan = "33"
3. confirm_date: The date the order was entered, formatted as "Month DD, YYYY" (e.g., "July 02, 2025"). Look for "entered on MM/DD/YYYY"

If a field cannot be found, use empty string ""."""

            structured_llm = self.llm.with_structured_output(OrderConfirmingDetails)
            result = structured_llm.invoke(prompt)

            docket_confirm = (result.docket_confirm or "").strip() or "N/A"
            docket_plan = (result.docket_plan or "").strip() or "N/A"
            confirm_date = (result.confirm_date or "").strip() or "N/A"

            print(f"{BLUE}[ORDER CONFIRMING] LLM extracted: docket_confirm={docket_confirm}, docket_plan={docket_plan}, confirm_date={confirm_date}{RESET}")
            return {"confirm_date": confirm_date, "docket_confirm": docket_confirm, "docket_plan": docket_plan}

        except Exception as e:
            print(f"Error extracting Order Confirming details: {e}")
            return {"confirm_date": "N/A", "docket_confirm": "N/A", "docket_plan": "N/A"}

    def _extract_chapter_13_plan_docket(self, case_number: str) -> str:
        """
        Extract DocketNumbPlan from the most recent 'Chapter 13 Plan Filed' email.
        Must have "Chapter 13 Plan Filed by" in body (not "Order Confirming").
        """
        import re
        from ..auth import get_gmail_service

        BLUE = "\033[94m"
        RESET = "\033[0m"

        try:
            gmail_service = get_gmail_service()
            query = f'"{case_number}" subject:"Chapter 13 Plan"'
            print(f"{BLUE}[PLAN DOCKET] Gmail query: {query}{RESET}")

            response = gmail_service.users().messages().list(
                userId="me", q=query, maxResults=20
            ).execute()

            message_refs = response.get("messages", []) or []
            print(f"{BLUE}[PLAN DOCKET] Found {len(message_refs)} emails with 'Chapter 13 Plan' in subject{RESET}")

            if not message_refs:
                return "N/A"

            # Find emails with "Chapter 13 Plan Filed by" in body (not Order Confirming)
            valid_emails = []
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

                # Skip if it's an "Order Confirming" email
                if "order confirming" in subject.lower():
                    print(f"{BLUE}[PLAN DOCKET] Skipping (Order Confirming): {subject[:50]}{RESET}")
                    continue

                body = self._extract_email_body(payload)
                if not body:
                    continue

                # Must have "Chapter 13 Plan Filed by" in body
                if "chapter 13 plan filed by" not in body.lower():
                    print(f"{BLUE}[PLAN DOCKET] Skipping (no 'Filed by' in body): {subject[:50]}{RESET}")
                    continue

                # Extract internal date for sorting
                internal_date = int(msg.get("internalDate", 0))
                print(f"{BLUE}[PLAN DOCKET] ✓ Valid Plan email: {subject[:50]}{RESET}")
                valid_emails.append({
                    "body": body,
                    "internal_date": internal_date,
                    "subject": subject
                })

            if not valid_emails:
                print(f"{BLUE}[PLAN DOCKET] No valid Chapter 13 Plan emails found{RESET}")
                return "N/A"

            # Sort by internal_date descending (most recent first)
            valid_emails.sort(key=lambda x: x["internal_date"], reverse=True)
            most_recent = valid_emails[0]
            print(f"{BLUE}[PLAN DOCKET] Using most recent: {most_recent['subject'][:50]}{RESET}")

            # Extract docket number
            doc_match = re.search(r"Document\s*Number[:\s]*(\d+)", most_recent["body"], re.IGNORECASE)
            if doc_match:
                docket_num = doc_match.group(1)
                print(f"{BLUE}[PLAN DOCKET] Extracted docket: {docket_num}{RESET}")
                return docket_num

            return "N/A"

        except Exception as e:
            print(f"Error extracting Chapter 13 Plan docket: {e}")
            return "N/A"

    def _extract_delinquency_notice_details(self, case_number: str) -> Dict[str, str]:
        """
        Extract DateDelinquent and DocketNumbNotice from the most recent
        'Notice of Delinquency' email using direct Gmail search.
        """
        import re
        try:
            email = search_and_extract_subject_email(
                case_number=case_number,
                subject_title="Notice of Delinquency",
                oldest=False,
            )
            if not email:
                print("[info] No 'Notice of Delinquency' email found")
                return {"date_delinquent": "N/A", "docket_notice": "N/A"}

            body = email.get("body", "")
            email_date = email.get("date", "")

            docket_num = "N/A"
            doc_match = re.search(r"Document\s*Number[:\s]*(\d+)", body, re.IGNORECASE)
            if doc_match:
                docket_num = doc_match.group(1)

            date_delinquent = "N/A"
            date_match = re.search(r"entered\s+on\s+([\d/]+)\s+at", body, re.IGNORECASE)
            if date_match:
                raw_date = date_match.group(1)
                try:
                    from datetime import datetime
                    dt = datetime.strptime(raw_date, "%m/%d/%Y")
                    date_delinquent = dt.strftime("%B %d, %Y")
                except ValueError:
                    date_delinquent = raw_date
            elif email_date:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(email_date)
                    date_delinquent = dt.strftime("%B %d, %Y")
                except Exception:
                    date_delinquent = email_date

            print(f"[info] Notice of Delinquency extracted: date={date_delinquent}, docket={docket_num}")
            return {"date_delinquent": date_delinquent, "docket_notice": docket_num}

        except Exception as e:
            print(f"Error extracting Notice of Delinquency details: {e}")
            return {"date_delinquent": "N/A", "docket_notice": "N/A"}

    def extract_payload(self, user_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract motion modify payload using OPTIMIZED approach:
        - PDF fields: 2 LLM calls (court_district, debtor_name from petition)
        - Gmail fields: 1 LLM call (combined extraction from labeled emails)

        Total: 3 LLM calls instead of 10+
        """
        try:
            print(f"Starting OPTIMIZED extraction for motion modify (type: {self.modification_type})...")

            # ================================================================
            # STEP 1: Extract PDF fields (2 LLM calls)
            # ================================================================
            pdf_results: Dict[str, str] = {}
            print("Extracting petition (PDF) fields...")
            for field in self.pdf_fields:
                print(f"  Extracting {field}...")
                query = self._get_optimized_query(field, user_hint)
                result = self._extract_single_field(field, query)
                pdf_results[field] = result
                print(f"    {field}: {result}")

            # ================================================================
            # STEP 2: Get case number first (needed for Gmail search)
            # We do a quick vectorstore lookup just for case_no
            # ================================================================
            print("Extracting case number for Gmail search...")
            case_no = self._extract_single_field("case_no_modify", "Case number with judge initial")
            print(f"    case_no: {case_no}")

            # Fallback: If vectorstore didn't find case_no, try Gmail with debtor name
            if case_no == "N/A":
                debtor_name = pdf_results.get("debtor_name_modify", "N/A")
                case_no = self._find_case_number_from_gmail(debtor_name)
                print(f"    case_no (from Gmail fallback): {case_no}")

            # ================================================================
            # STEP 3: Combined Gmail extraction (1 LLM call)
            # Fetches all relevant emails and extracts everything at once
            # ================================================================
            gmail_combined = self._extract_all_gmail_fields_combined(case_no)

            print("Extracting current date...")
            current_date = self._extract_current_date()
            print(f"    current_date: {current_date}")

            # Use combined extraction results, with case_no from vectorstore as fallback
            final_case_no = gmail_combined.get("case_no", "N/A")
            if final_case_no == "N/A":
                final_case_no = case_no

            # Build base payload (common fields)
            use_granting = gmail_combined.get("use_granting_template", False)
            final_payload = {
                "court_district": pdf_results.get("court_district_modify", "N/A"),
                "court_division": gmail_combined.get("court_division", "N/A"),
                "debtor_name": pdf_results.get("debtor_name_modify", "N/A"),
                "case_no": final_case_no,
                "chapter": gmail_combined.get("chapter", "N/A"),
                "confirm_date": gmail_combined.get("confirm_date", "N/A"),
                "docket_confirm": gmail_combined.get("docket_confirm", "N/A"),
                "docket_plan": gmail_combined.get("docket_plan", "N/A"),
                "current_date": current_date,
                "modification_type": self.modification_type,
                "use_granting_template": use_granting,
            }

            # Add delinquent fields if applicable
            if self.modification_type in ("delinquent", "both"):
                final_payload.update({
                    "date_delinquent": gmail_combined.get("date_delinquent", "N/A"),
                    "docket_notice": gmail_combined.get("docket_notice", "N/A"),
                    "delinquent_reason": self.static_fields["delinquent_reason"],
                })

            # Add creditor alteration fields if applicable
            if self.modification_type in ("creditor_alteration", "both"):
                # Use dedicated creditor extraction (more reliable than combined)
                print("Extracting creditors via dedicated POC extraction...")
                available_creditors = self._extract_available_creditors(case_no)

                final_payload.update({
                    "creditors": self.static_fields["creditors"],
                    "claim_slot": self.static_fields["claim_slot"],
                    "has_have": self.static_fields["has_have"],
                    "s_plural": self.static_fields["s_plural"],
                    "available_creditors": json.dumps(available_creditors),
                })

            llm_calls = 4 if self.modification_type not in ("creditor_alteration", "both") else 5
            print(f"\nFinal payload: {final_payload}")
            print(f"LLM calls: 2 (PDF) + 1 (case_no) + 1 (combined Gmail) + {1 if self.modification_type in ('creditor_alteration', 'both') else 0} (creditors) = {llm_calls} total")

            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "gmail_motion_modify_agent_optimized",
                "field_results": {
                    **pdf_results,
                    **gmail_combined,
                    "current_date": current_date,
                },
            }

        except Exception as e:
            return {
                "payload": f"Gmail Motion modify payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "gmail_motion_modify_agent_optimized",
            }


