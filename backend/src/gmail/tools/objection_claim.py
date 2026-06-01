from typing import Optional, Dict
from langchain_core.tools import tool
from ...chatbot.vectorestore import search_vectorstore

# Called by: extract_all_claim_fields_for_session (same file)
def _get_case_number_for_claims(session_id: Optional[str]) -> Optional[str]:
    """Helper function to get case number for searching Proof of Claim emails."""
    if not session_id:
        return None
    
    from ...chatbot.agent import CaseNumberAgent
    
    # Try to extract from petition first (faster)
    try:
        case_agent = CaseNumberAgent(session_id=session_id)
        case_result = case_agent.extract_case_number()
        if case_result.get("status") == "completed" and case_result.get("case_number"):
            return case_result.get("case_number", "").strip()
    except Exception as e:
        print(f"[warn] Could not extract case number from petition: {e}")
    
    # Fallback: try to extract from Gmail vectorstore
    try:
        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore("case number", collection_name=gmail_collection, k=5)
        if gmail_docs:
            # Try to extract case number from email content (simple regex)
            import re
            for doc in gmail_docs:
                # Look for case number pattern like "25-14980" or "25-14980-PDR"
                match = re.search(r'(\d{2}-\d{5})(?:-([A-Z]{2,4}))?', doc.page_content)
                if match:
                    base_case = match.group(1)
                    return base_case  # Return base case number for searching
    except Exception as e:
        print(f"[warn] Could not extract case number from Gmail: {e}")
    
    return None

# Called by: GmailMotionObjectionSustainAgent (agents/objection_sustain.py)
def extract_all_claim_fields_for_session(session_id: Optional[str]) -> Dict[str, str]:
    """
    Extract all three claim fields (slot, claimant_name, claim_amount) at once.
    Returns deduplicated results where duplicates are exact matches of all three fields.
    
    This is a module-level function that can be called directly from the agent.
    
    Returns:
        Dictionary with keys: "slot", "claimant_name", "claim_amount"
        Each value is a newline-separated string of values
    """
    from ..extractor import get_gmail_claims_as_documents
    
    if not session_id:
        return {"slot": "N/A", "claimant_name": "N/A", "claim_amount": "N/A"}
    
    case_number = _get_case_number_for_claims(session_id)
    if not case_number:
        return {"slot": "N/A", "claimant_name": "N/A", "claim_amount": "N/A"}
    
    gmail_claim_docs = get_gmail_claims_as_documents(session_id, case_number)
    if not gmail_claim_docs:
        return {"slot": "N/A", "claimant_name": "N/A", "claim_amount": "N/A"}
    
    # Extract all claims with their paired fields
    claims = []
    for doc in gmail_claim_docs:
        slot = doc.metadata.get("claim_number", "").strip()
        creditor_name = doc.metadata.get("creditor_name", "").strip()
        amount = doc.metadata.get("amount_claimed", "").strip()
        
        # Only include if all three fields are present and valid
        if slot and slot != "N/A" and creditor_name and creditor_name != "N/A" and amount and amount != "N/A":
            claims.append({
                "slot": slot,
                "creditor_name": creditor_name,
                "amount": amount
            })
    
    if not claims:
        return {"slot": "N/A", "claimant_name": "N/A", "claim_amount": "N/A"}
    
    # Deduplicate: remove exact duplicates where all three fields match exactly
    seen = set()
    unique_claims = []
    for claim in claims:
        # Create a tuple key for deduplication (all three fields must match)
        key = (claim["slot"], claim["creditor_name"], claim["amount"])
        if key not in seen:
            seen.add(key)
            unique_claims.append(claim)
    
    # Sort by slot (claim number) in descending order
    unique_claims.sort(key=lambda x: int(x["slot"]) if x["slot"].isdigit() else 0, reverse=True)
    
    # Extract into separate lists
    slots = [c["slot"] for c in unique_claims]
    creditor_names = [c["creditor_name"] for c in unique_claims]
    amounts = [c["amount"] for c in unique_claims]
    
    return {
        "slot": "\n".join(slots) if slots else "N/A",
        "claimant_name": "\n".join(creditor_names) if creditor_names else "N/A",
        "claim_amount": "\n".join(amounts) if amounts else "N/A"
    }


# Called by: GmailMotionObjectionClaimAgent (agents/objection_claim.py)
def motion_objection_claim_gmail_tool(session_id: Optional[str] = None):
    """
    Individual tools for motion objection claim payload extraction using Gmail + petition.
    
    - Petition (bankruptcy_knowledge_<session_id>) for:
      debtor_name_objection, case_number_objection (base)
    - Gmail (gmail_<session_id>) for:
      case_number_objection (with judge initial), judge_initial_objection
    - Gmail Proof of Claim emails for:
      slot_objection, claimant_name_objection, claim_amount_objection
    """
    def _extract_all_claim_fields() -> Dict[str, str]:
        """
        Extract all three claim fields (slot, claimant_name, claim_amount) at once.
        Uses the module-level function for consistency.
        """
        return extract_all_claim_fields_for_session(session_id)

    @tool()
    def extract_debtor_name_objection(query: str):
        """Extract debtor name from bankruptcy petition PDFs"""
        if not session_id:
            return "No session_id available. Please start a session or upload a PDF first."
        
        pdf_collection = f"bankruptcy_knowledge_{session_id}"
        pdf_docs = search_vectorstore(query, collection_name=pdf_collection, k=15)
        if not pdf_docs:
            return f"No relevant passages found in collection '{pdf_collection}'."
        
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in pdf_docs
        )
        return serialized

    @tool()
    def extract_case_number_objection(query: str):
        """
        Extract case number (with judge initial) from Gmail emails for this case.
        
        Expects a collection named gmail_<session_id> to contain
        case-related emails (subjects and bodies).
        The case number should include the judge initial suffix (e.g., "25-14980-PDR").
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."
        
        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."
        
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    @tool()
    def extract_slot_objection(query: str):
        """
        Extract slot (claim number) from Gmail Proof of Claim emails.
        
        Returns all claim numbers separated by newlines, sorted in descending order.
        No AI processing - directly extracted from systematically parsed emails.
        Uses cached extraction results if available.
        """
        result = _extract_all_claim_fields()
        return result.get("slot", "N/A")

    @tool()
    def extract_claimant_name_objection(query: str):
        """
        Extract claimant name (creditor name) from Gmail Proof of Claim emails.
        
        Returns all creditor names separated by newlines, in the same order as claim numbers.
        No AI processing - directly extracted from systematically parsed emails.
        Uses cached extraction results if available.
        """
        result = _extract_all_claim_fields()
        return result.get("claimant_name", "N/A")

    @tool()
    def extract_claim_amount_objection(query: str):
        """
        Extract claim amount from Gmail Proof of Claim emails.
        
        Returns all claim amounts separated by newlines, in the same order as claim numbers.
        No AI processing - directly extracted from systematically parsed emails.
        Uses cached extraction results if available.
        """
        result = _extract_all_claim_fields()
        return result.get("claim_amount", "N/A")

    @tool()
    def extract_judge_initial_objection(query: str):
        """
        Extract judge initial from Gmail emails (extracted from case number with judge initial).
        
        Expects a collection named gmail_<session_id> to contain
        case-related emails with case number including judge initial (e.g., "25-14980-PDR").
        """
        if not session_id:
            return "No session_id available. Please start a session or ingest Gmail emails first."
        
        gmail_collection = f"gmail_{session_id}"
        gmail_docs = search_vectorstore(query, collection_name=gmail_collection, k=15)
        if not gmail_docs:
            return f"No relevant passages found in collection '{gmail_collection}'."
        
        serialized = "\n\n".join(
            (f"Source: {doc.metadata}\nContent: {doc.page_content}")
            for doc in gmail_docs
        )
        return serialized

    return [
        extract_debtor_name_objection,
        extract_case_number_objection,
        extract_slot_objection,
        extract_claimant_name_objection,
        extract_claim_amount_objection,
        extract_judge_initial_objection,
    ]


