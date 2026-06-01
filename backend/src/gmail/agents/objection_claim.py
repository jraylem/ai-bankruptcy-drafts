from typing import Optional, Dict, Any
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain.chat_models import init_chat_model

from ...config import settings
from ...ai_models import CLAUDE_MODEL_FAST, CLAUDE_PROVIDER, CLAUDE_TEMPERATURE
from ..tools import (
    motion_objection_claim_gmail_tool,
)
from ..prompts import (
    INDIVIDUAL_FIELD_PROMPTS_OBJECTION_CLAIM_GMAIL,
)


# Called by: service.generate_payload_objection_claim_for_session_gmail (L3C)
#   -> routes/service_stream.py
class GmailMotionObjectionClaimAgent:
    """
    Gmail-backed Motion Objection Claim Agent.
    
    Uses:
    - Petition vectorstore (bankruptcy_knowledge_<session_id>) for:
      debtor_name_objection, case_number_objection (base)
    - Gmail vectorstore (gmail_<session_id>) for:
      case_number_objection (with judge initial), judge_initial_objection
    - Gmail Proof of Claim emails for:
      slot_objection, claimant_name_objection, claim_amount_objection
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
        self.pdf_fields = ["debtor_name_objection", "case_number_objection"]
        # Gmail-based fields (case number with judge, claim details, judge initial)
        self.gmail_fields = [
            "case_number_objection",
            "slot_objection",
            "claimant_name_objection",
            "claim_amount_objection",
            "judge_initial_objection",
        ]
        
        # Static fields for objection claim motion
        self.static_fields = {
            "basis": "N/A"
        }
    
    def _get_optimized_query(self, field_name: str, user_hint: str = None) -> str:
        field_queries = {
            "debtor_name_objection": "Your full name Debtor 1",
            "case_number_objection": "Case number with judge initial from emails",
            "slot_objection": "claim # claim number",
            "claimant_name_objection": "creditor name claimant",
            "claim_amount_objection": "amount claimed",
            "judge_initial_objection": "Judge initial from case number",
        }
        base_query = field_queries.get(field_name, field_name)
        if user_hint:
            return f"{base_query} {user_hint}"
        return base_query
    
    def _extract_claim_fields_together(self) -> Dict[str, str]:
        """
        Extract all three claim fields (slot, claimant_name, claim_amount) at once.
        This avoids redundant extraction calls and ensures proper pairing with deduplication.
        
        Returns:
            Dictionary with keys: "slot_objection", "claimant_name_objection", "claim_amount_objection"
        """
        try:
            from ..tools import extract_all_claim_fields_for_session
            
            # Extract all three fields at once (with deduplication)
            result = extract_all_claim_fields_for_session(self.session_id)
            
            return {
                "slot_objection": result.get("slot", "N/A"),
                "claimant_name_objection": result.get("claimant_name", "N/A"),
                "claim_amount_objection": result.get("claim_amount", "N/A")
            }
            
        except Exception as e:
            print(f"Error extracting claim fields together: {str(e)}")
            return {
                "slot_objection": "N/A",
                "claimant_name_objection": "N/A",
                "claim_amount_objection": "N/A"
            }
    
    def _extract_single_field(self, field_name: str, query: str) -> str:
        # For claim fields (slot, claimant_name, claim_amount), use cached extraction
        # These are systematically extracted and already properly paired
        direct_extraction_fields = ["slot_objection", "claimant_name_objection", "claim_amount_objection"]
        
        if field_name in direct_extraction_fields:
            # This will be handled by _extract_claim_fields_together in extract_payload
            # For now, return placeholder - actual extraction happens in extract_payload
            return "N/A"
        
        # For other fields, use AI agent (debtor_name, case_number, judge_initial)
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            try:
                tools = motion_objection_claim_gmail_tool(session_id=self.session_id)
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
                    prompt=INDIVIDUAL_FIELD_PROMPTS_OBJECTION_CLAIM_GMAIL[field_name],
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
        Extract motion objection claim payload using Gmail + petition vectorstores.
        """
        try:
            print("Starting Gmail-backed sequential field extraction for motion objection claim...")
            
            # Extract PDF fields sequentially
            pdf_results: Dict[str, str] = {}
            print("Extracting petition (PDF) fields...")
            for field in self.pdf_fields:
                print(f"  Extracting {field}...")
                query = self._get_optimized_query(field, user_hint)
                result = self._extract_single_field(field, query)
                pdf_results[field] = result
                print(f"    {field}: {result}")
            
            # Extract Gmail fields sequentially
            # But extract claim fields (slot, claimant_name, claim_amount) together for efficiency
            gmail_results: Dict[str, str] = {}
            print("Extracting Gmail-backed fields...")
            
            # Extract claim fields together (slot, claimant_name, claim_amount)
            claim_fields = ["slot_objection", "claimant_name_objection", "claim_amount_objection"]
            print("  Extracting claim fields together (slot, claimant_name, claim_amount)...")
            claim_field_results = self._extract_claim_fields_together()
            for field in claim_fields:
                gmail_results[field] = claim_field_results.get(field, "N/A")
                print(f"    {field}: {gmail_results[field]}")
            
            # Extract other Gmail fields individually
            for field in self.gmail_fields:
                if field not in claim_fields:  # Skip claim fields, already extracted
                    print(f"  Extracting {field}...")
                    query = self._get_optimized_query(field, user_hint)
                    result = self._extract_single_field(field, query)
                    gmail_results[field] = result
                    print(f"    {field}: {result}")
            
            # Extract current date directly
            print("Extracting current date...")
            current_date = self._extract_current_date()
            print(f"    current_date: {current_date}")
            
            # Combine all results
            all_results = {**pdf_results, **gmail_results, **self.static_fields}
            
            # Case number from Gmail already includes judge initial (e.g., "25-14980-PDR")
            case_number = gmail_results.get("case_number_objection", "N/A")
            
            # If case_number is still N/A, try from PDF results (base case number)
            if case_number == "N/A":
                base_case_number = pdf_results.get("case_number_objection", "N/A")
                judge_initial = gmail_results.get("judge_initial_objection", "N/A")
                if base_case_number != "N/A" and judge_initial != "N/A":
                    case_number = f"{base_case_number}-{judge_initial}"
                elif base_case_number != "N/A":
                    case_number = base_case_number
            
            # Create final JSON payload
            final_payload = {
                "DebtorName": pdf_results.get("debtor_name_objection", "N/A"),
                "CaseNumber": case_number,
                "Slot": gmail_results.get("slot_objection", "N/A"),
                "ClaimantName": gmail_results.get("claimant_name_objection", "N/A"),
                "ClaimAmount": gmail_results.get("claim_amount_objection", "N/A"),
                "Basis": self.static_fields["basis"],
                "Date": current_date
            }
            
            # Calculate success rate
            total_fields = len(self.pdf_fields) + len(self.gmail_fields)
            successful_fields = sum(
                1 for value in all_results.values()
                if value != "N/A" and value not in self.static_fields.values()
            )
            
            success_rate = (successful_fields / total_fields) * 100 if total_fields else 0.0
            
            print(f"Final Gmail-backed objection claim payload: {final_payload}")
            print(f"Success rate: {success_rate:.1f}% ({successful_fields}/{total_fields} fields)")
            
            return {
                "payload": final_payload,
                "status": "completed",
                "agent_type": "gmail_motion_objection_claim_agent_sequential",
                "field_results": all_results,
                "success_rate": success_rate,
            }
        
        except Exception as e:
            return {
                "payload": f"Gmail Motion objection claim payload extraction failed: {str(e)}",
                "status": "failed",
                "error": str(e),
                "agent_type": "gmail_motion_objection_claim_agent_sequential",
            }


