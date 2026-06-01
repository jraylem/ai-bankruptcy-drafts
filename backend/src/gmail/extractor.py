"""
Gmail Email Extractor

Core logic for searching Gmail by case number and extracting email subjects and bodies.
"""

from typing import List, Dict, Any, Optional
import base64
import quopri
import re
from langchain_core.documents import Document
from .auth import get_gmail_service


# Called by: service.ingest_gmail_emails_for_session (L1 -> all routes),
#            service.ingest_dismissed_case_emails_for_session (L1 -> GmailMotionExtendAgent path)
def search_and_extract_emails(case_number: str) -> List[Document]:
    """
    Search Gmail for emails containing the case number and extract all subjects and bodies.
    
    Args:
        case_number: Case number to search for (e.g., "25-14980")
    
    Returns:
        List of Document objects, each containing:
        - page_content: "Subject: <subject>\n\n<body>"
        - metadata: email_id, subject, from, date, case_number
    
    Raises:
        Exception: If Gmail API fails or no emails found
    """
    # Initialize Gmail API service
    gmail_service = get_gmail_service()

    # Build search query - handle both short (26-01938) and full (26-bk-01938) formats
    # If case_number is "26-01938", also search for "26-bk-01938"
    match = re.match(r"^(\d{2})-(\d+)$", case_number)
    if match:
        year, num = match.groups()
        bk_variant = f"{year}-bk-{num}"
        query = f'"{case_number}" OR "{bk_variant}"'
    else:
        query = f'"{case_number}"'
    print(f"[info] Searching Gmail with query: {query}")
    
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = Exception
    
    # Search for emails
    try:
        response = gmail_service.users().messages().list(
            userId="me",
            q=query,
            maxResults=100,
        ).execute()
    except HttpError as e:
        raise Exception(f"Gmail API search error: {e}")
    
    message_refs = response.get("messages", []) or []
    
    if not message_refs:
        print(f"[info] No emails found for case number: {case_number}")
        return []
    
    print(f"[info] Found {len(message_refs)} emails, extracting content...")
    
    # Extract full email content
    documents: List[Document] = []
    
    for msg_ref in message_refs:
        try:
            email_id = msg_ref.get("id")
            msg = (
                gmail_service.users()
                .messages()
                .get(userId="me", id=email_id, format="full")
                .execute()
            )
            
            payload = msg.get("payload", {}) or {}
            headers = payload.get("headers", []) or []
            
            # Extract headers
            def _get_header(name: str) -> str:
                for h in headers:
                    if h.get("name", "").lower() == name.lower():
                        return h.get("value", "")
                return ""
            
            email_subject = _get_header("Subject")
            email_from = _get_header("From")
            email_date = _get_header("Date")
            email_body = _extract_plain_text(payload)
            
            # Combine subject and body for search
            email_content = f"Subject: {email_subject}\n\n{email_body}"
            
            # Create document
            doc = Document(
                page_content=email_content,
                metadata={
                    "source": f"gmail_{email_id}",
                    "document_type": "email",
                    "email_id": email_id,
                    "subject": email_subject,
                    "from": email_from,
                    "date": email_date,
                    "case_number": case_number,
                },
            )
            documents.append(doc)
            
        except Exception as e:
            print(f"[warn] Error processing email {msg_ref.get('id')}: {e}")
            continue
    
    if not documents:
        raise Exception("No emails could be processed successfully")
    
    print(f"[info] Successfully extracted {len(documents)} emails")
    return documents


# Called by: court_mail.fetch_court_mail_pdfs_for_session (court_mail.py),
#            workflow_services.EmailIngestionService (workflow_services.py -> gmail/routes.py)
def _extract_plain_text(payload: Dict[str, Any]) -> str:
    """
    Extract plain-text body from a Gmail message payload.
    
    Handles:
    - Simple messages with body.data
    - Multipart messages with text/plain parts
    - Base64 and quoted-printable encoding
    - HTML content (strips HTML tags)
    
    Args:
        payload: Gmail message payload dictionary
    
    Returns:
        Plain text body content (HTML tags stripped)
    """
    import re
    
    parts = payload.get("parts")
    data = payload.get("body", {}).get("data")
    
    def decode_data(encoded: str) -> str:
        """Decode base64 or quoted-printable encoded data."""
        try:
            # Gmail API uses URL-safe base64
            return base64.urlsafe_b64decode(encoded.encode("utf-8")).decode(
                "utf-8", errors="ignore"
            )
        except Exception:
            try:
                # Fallback: quoted-printable
                return quopri.decodestring(encoded).decode("utf-8", errors="ignore")
            except Exception:
                return ""
    
    def strip_html(html_content: str) -> str:
        """Strip HTML tags and decode HTML entities."""
        if not html_content:
            return ""
        
        # Decode HTML entities like &nbsp;, &amp;, etc.
        import html as html_module
        try:
            text = html_module.unescape(html_content)
        except Exception:
            text = html_content
        
        # Convert <br> and <br/> tags to newlines BEFORE removing other tags
        # This preserves line breaks so we can extract just the first line
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        
        # Remove HTML tags more aggressively (handle self-closing tags, comments, etc.)
        # Remove HTML comments
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        # Remove script and style tags with content
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
        # Remove all HTML tags (including self-closing and closing tags)
        text = re.sub(r'<[^>]+>', '', text)
        # Remove any remaining HTML entity fragments
        text = re.sub(r'&[a-zA-Z]+;', '', text)
        
        # Clean up &nbsp (sometimes not properly decoded) - do this before normalizing whitespace
        text = re.sub(r'&nbsp;?', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'&nbsp', ' ', text, flags=re.IGNORECASE)  # Handle &nbsp without semicolon
        
        # Normalize whitespace (multiple spaces/tabs to single space, but preserve newlines)
        text = re.sub(r'[ \t]+', ' ', text)  # Normalize spaces and tabs only
        text = re.sub(r'[ \t]*\n[ \t]*', '\n', text)  # Normalize newlines (remove spaces around them)
        
        return text.strip()
    
    text_content = ""
    is_html = False
    
    # Simple message with body.data
    if data:
        text_content = decode_data(data)
        # Check if it's HTML
        mime_type = payload.get("mimeType", "")
        if mime_type == "text/html" or ('<' in text_content and '>' in text_content and '<html' in text_content.lower()):
            is_html = True
    elif parts:
        # Prefer text/plain parts
        for part in parts:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain":
                body_data = part.get("body", {}).get("data")
                if body_data:
                    text_content = decode_data(body_data)
                    break
        
        # Fallback: use text/html if no plain text found
        if not text_content:
            for part in parts:
                mime_type = part.get("mimeType", "")
                body_data = part.get("body", {}).get("data")
                if body_data:
                    text_content = decode_data(body_data)
                    if mime_type == "text/html" or ('<' in text_content and '>' in text_content):
                        is_html = True
                    break
    
    # Always strip HTML if HTML tags are detected (even if not marked as HTML)
    if text_content and (is_html or ('<' in text_content and '>' in text_content)):
        text_content = strip_html(text_content)
    
    return text_content


# Called by: get_gmail_claims_as_documents (same file, below)
def search_and_extract_proof_of_claim_emails(case_number: str) -> List[Dict[str, Any]]:
    """
    Search Gmail for emails with subject starting with "Proof of Claim" containing the case number
    and extract claim details systematically (without AI).
    
    Args:
        case_number: Case number to search for (e.g., "25-14980")
    
    Returns:
        List of dictionaries, each containing:
        - email_id: Gmail message ID
        - subject: Email subject
        - date: Email date
        - creditor_name: Extracted creditor name
        - claim_number: Extracted claim number
        - amount_claimed: Extracted amount claimed
        - email_body: Full email body
    
    Raises:
        Exception: If Gmail API fails
    """
    import re
    
    # Initialize Gmail API service
    gmail_service = get_gmail_service()
    
    # Search by case number first, then filter by subject in code
    # This is more reliable than trying to match exact subject patterns
    # since subjects may vary (e.g., "Proof of ClaimCh-13..." vs "Proof of Claim Ch-13...")
    query = f'"{case_number}"'
    print(f"[info] Searching Gmail for emails with case_number={case_number}")
    print(f"[info] Using Gmail search query: {query}")
    
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = Exception
    
    # Search for emails by case number
    try:
        response = gmail_service.users().messages().list(
            userId="me",
            q=query,
            maxResults=500,  # Get enough results to filter
        ).execute()
    except HttpError as e:
        raise Exception(f"Gmail API search error: {e}")
    
    message_refs = response.get("messages", []) or []
    
    if not message_refs:
        print(f"[info] No emails found for case number: {case_number}")
        return []
    
    print(f"[info] Found {len(message_refs)} emails with case number, filtering for Proof of Claim...")
    
    # Extract claim details from each email
    claims: List[Dict[str, Any]] = []
    
    for msg_ref in message_refs:
        try:
            email_id = msg_ref.get("id")
            msg = (
                gmail_service.users()
                .messages()
                .get(userId="me", id=email_id, format="full")
                .execute()
            )
            
            payload = msg.get("payload", {}) or {}
            headers = payload.get("headers", []) or []
            
            # Extract headers
            def _get_header(name: str) -> str:
                for h in headers:
                    if h.get("name", "").lower() == name.lower():
                        return h.get("value", "")
                return ""
            
            email_subject = _get_header("Subject")
            email_date = _get_header("Date")
            
            # Filter: only process emails with "Proof of Claim" phrase in subject (case-insensitive)
            # Handle variations like "Proof of ClaimCh-13..." (no space) or "Proof of Claim Ch-13..."
            subject_lower = email_subject.lower() if email_subject else ""
            if "proof of claim" not in subject_lower:
                # Skip emails that don't have "proof of claim" phrase in subject
                continue

            email_body = _extract_plain_text(payload)

            # Extract claim details from email body
            if not email_body:
                print(f"[warn] Email body is empty for email: {email_subject}")
                continue

            claim_details = _extract_claim_details_from_body(email_body)
            
            if claim_details:
                claim_details.update({
                    "email_id": email_id,
                    "subject": email_subject,
                    "date": email_date,
                    "email_body": email_body,
                })
                claims.append(claim_details)
            
            # Also check for replies/threads in the same email thread
            # Gmail API includes threadId, we can search for other messages in the thread
            thread_id = msg.get("threadId")
            if thread_id:
                try:
                    thread_messages = gmail_service.users().threads().get(
                        userId="me", id=thread_id, format="full"
                    ).execute()
                    
                    thread_parts = thread_messages.get("messages", []) or []
                    # Skip first message (already processed above)
                    for thread_msg in thread_parts[1:]:
                        thread_email_id = thread_msg.get("id")
                        if thread_email_id == email_id:
                            continue  # Already processed
                        
                        thread_payload = thread_msg.get("payload", {}) or {}
                        thread_headers = thread_payload.get("headers", []) or []
                        
                        def _get_thread_header(name: str) -> str:
                            for h in thread_headers:
                                if h.get("name", "").lower() == name.lower():
                                    return h.get("value", "")
                            return ""
                        
                        thread_subject = _get_thread_header("Subject")
                        thread_date = _get_thread_header("Date")
                        
                        # Filter replies: only process if they have "Proof of Claim" phrase in subject
                        thread_subject_lower = thread_subject.lower() if thread_subject else ""
                        if "proof of claim" not in thread_subject_lower:
                            # Skip replies that don't have "proof of claim" phrase in subject
                            continue

                        thread_body = _extract_plain_text(thread_payload)

                        # Extract claim details from reply
                        thread_claim_details = _extract_claim_details_from_body(thread_body)
                        
                        if thread_claim_details:
                            thread_claim_details.update({
                                "email_id": thread_email_id,
                                "subject": thread_subject,
                                "date": thread_date,
                                "email_body": thread_body,
                                "is_reply": True,
                            })
                            claims.append(thread_claim_details)
                
                except Exception as e:
                    print(f"[warn] Error processing thread {thread_id}: {e}")
                    continue
            
        except Exception as e:
            print(f"[warn] Error processing email {msg_ref.get('id')}: {e}")
            continue
    
    if not claims:
        print(f"[info] No Proof of Claim emails found for case number: {case_number} (after filtering by subject)")
    else:
        print(f"[info] Successfully extracted {len(claims)} claim(s) from Proof of Claim emails")
    return claims


# Called by: search_and_extract_proof_of_claim_emails (same file, above)
def _extract_claim_details_from_body(email_body: str) -> Dict[str, str] | None:
    """
    Extract claim details (creditor name, claim number, amount claimed) from email body
    systematically without AI.
    
    Expected format:
    Creditor Name:	Bank of America, N.A.
    PO Box 673033
    Dallas, TX 75267-3033
    Claim Number:	11 &nbsp &nbsp Claims Register
    Amount Claimed: $8550.15
    
    Args:
        email_body: The email body text
    
    Returns:
        Dictionary with creditor_name, claim_number, amount_claimed, or None if not found
    """
    import re
    
    if not email_body:
        return None
    
    result = {
        "creditor_name": None,
        "claim_number": None,
        "amount_claimed": None,
    }
    
    # Extract Creditor Name
    # Extract only the first line after "Creditor Name:"
    # Format example:
    # Creditor Name:	LVNV Funding, LLC
    # Resurgent Capital Services
    # PO Box 10587
    # -> Should extract: "LVNV Funding, LLC"
    creditor_patterns = [
        # Match until "Claim Number:" field
        r'Creditor\s+Name[:\s\t]+(.*?)(?=\s*Claim\s+Number)',
        # Fallback: match until "Amount Claimed" if "Claim Number" not found
        r'Creditor\s+Name[:\s\t]+(.*?)(?=\s*Amount\s+Claimed)',
        # Fallback: match first line (until newline)
        r'Creditor\s+Name[:\s\t]+([^\n\r]+)',
    ]
    
    for pattern in creditor_patterns:
        match = re.search(pattern, email_body, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            creditor_name = match.group(1).strip()
            
            # Split by newlines and take only the first line (handles cases where newlines still exist)
            lines = creditor_name.split('\n')
            if lines:
                creditor_name = lines[0].strip()
            lines = creditor_name.split('\r')
            if lines:
                creditor_name = lines[0].strip()
            
            # Clean up - remove HTML entities
            creditor_name = re.sub(r'&nbsp;?', ' ', creditor_name, flags=re.IGNORECASE)
            
            # Remove extra whitespace
            creditor_name = re.sub(r'\s+', ' ', creditor_name).strip()
            
            # Validate: reject HTML tags or fragments
            if '<' in creditor_name or '>' in creditor_name or creditor_name.startswith('</'):
                continue
            
            # Validate: must have at least 5 chars and contain letters (company name should have letters)
            if len(creditor_name) > 5 and re.search(r'[A-Za-z]', creditor_name):
                result["creditor_name"] = creditor_name
                break
    
    # Extract Claim Number
    # Pattern: "Claim Number:" followed by number (may have &nbsp, tabs, or "Claims Register" text)
    # Example: "Claim Number:	11 &nbsp &nbsp Claims Register"
    # Example: "Claim Number: 14 Claims Register"
    # Example: "Claim Number: 14&nbsp&nbspClaims Register" (no spaces around &nbsp)
    # Clean up any remaining &nbsp in the body first
    email_body_clean = re.sub(r'&nbsp;?', ' ', email_body, flags=re.IGNORECASE)
    
    claim_patterns = [
        # Match "Claim Number:" followed by digits (handle tabs, spaces, &nbsp, "Claims Register")
        # This handles: "Claim Number:\t11 &nbsp &nbsp Claims Register" or "Claim Number: 14 Claims Register"
        r'Claim\s+Number[:\s\t]+(\d+)(?:\s*(?:Claims?\s+Register))?',
        # More flexible: any whitespace/tabs between "Claim Number:" and the number
        r'Claim\s+Number[:\s\t]+(\d+)',
        # Handle "#" notation: "Claim #: 11" or "Claim # 11"
        r'Claim\s+#[:\s\t]*(\d+)',
        # Very permissive: just look for "Claim Number:" and next number
        r'Claim\s+Number[:\s\t]*(\d+)',
    ]
    
    for pattern in claim_patterns:
        match = re.search(pattern, email_body_clean, re.IGNORECASE)
        if match:
            claim_num = match.group(1).strip()
            result["claim_number"] = claim_num
            break
    
    # Extract Amount Claimed
    # Pattern: "Amount Claimed:" followed by dollar amount
    # Example: "Amount Claimed: $8550.15"
    # Example: "Amount Claimed: $5,020.48"
    amount_patterns = [
        # Match "Amount Claimed:" followed by optional whitespace/tabs, optional $, then amount with decimals
        # This handles: "Amount Claimed: $8550.15" or "Amount Claimed:\t$5020.48"
        r'Amount\s+Claimed[:\s\t]+\$?\s*([\d,]+\.\d{2})',
        # Handle amounts without decimals
        r'Amount\s+Claimed[:\s\t]+\$?\s*([\d,]+)',
        # Handle with "USD" prefix
        r'Amount\s+Claimed[:\s\t]+USD\s*\$?\s*([\d,]+\.?\d*)',
        # Match any currency format after "Amount Claimed:"
        r'Amount\s+Claimed[:\s\t]+.*?\$([\d,]+\.?\d*)',
    ]
    
    for pattern in amount_patterns:
        match = re.search(pattern, email_body, re.IGNORECASE)
        if match:
            amount = match.group(1).strip()
            # Remove commas for parsing
            amount_clean = amount.replace(',', '')
            # Format as currency
            try:
                amount_float = float(amount_clean)
                # Format with 2 decimals and commas if >= 1000
                if amount_float >= 1000:
                    result["amount_claimed"] = f"${amount_float:,.2f}"
                else:
                    # Keep 2 decimals for smaller amounts
                    result["amount_claimed"] = f"${amount_float:.2f}"
            except ValueError:
                # Fallback: just add $ if parsing fails
                result["amount_claimed"] = f"${amount}"
            break
    
    # Only return if we found at least creditor name and claim number
    if result["creditor_name"] and result["claim_number"]:
        return result
    
    # If we found some but not all, log for debugging
    if result["creditor_name"] or result["claim_number"]:
        print(f"[warn] Partial extraction - Creditor: {result['creditor_name']}, Claim #: {result['claim_number']}, Amount: {result['amount_claimed']}")
    
    return None


# Called by: tools/objection_claim.extract_all_claim_fields_for_session
#            -> GmailMotionObjectionSustainAgent -> service.generate_payload_objection_sustain_for_session_gmail (L3D)
#            -> routes/stream.py
def get_gmail_claims_as_documents(session_id: str, case_number: str) -> List[Document]:
    """
    Get all claims from Gmail "Proof of Claim" emails as Document objects,
    sorted by claim number in descending order.
    
    Args:
        session_id: Session ID for tracking
        case_number: Case number to search for
    
    Returns:
        List of Document objects, each containing claim information
    """
    # Extract claims from Gmail
    claims = search_and_extract_proof_of_claim_emails(case_number)
    
    if not claims:
        return []
    
    documents = []
    for idx, claim in enumerate(claims):
        # Create a formatted text representation with explicit pairing
        # Each document represents ONE complete claim with slot, creditor name, and amount paired together
        parts = []
        parts.append(f"Claim #: {claim.get('claim_number', 'N/A')}")
        parts.append(f"Creditor Name: {claim.get('creditor_name', 'N/A')}")
        parts.append(f"Amount Claimed: {claim.get('amount_claimed', 'N/A')}")
        parts.append("---")  # Separator to make it clear this is one complete claim
        
        # Include email metadata for reference
        if claim.get('date'):
            parts.append(f"Date: {claim.get('date')}")
        if claim.get('subject'):
            parts.append(f"Email Subject: {claim.get('subject')}")
        if claim.get('is_reply'):
            parts.append(f"Type: Reply/Thread")
        
        # Include full email body for context (optional, may be long)
        # Note: Commented out to keep documents focused on claim details
        # if claim.get('email_body'):
        #     parts.append(f"\nFull Email Body:\n{claim.get('email_body')}")
        
        content = "\n".join([p for p in parts if p])
        
        metadata = {
            "source": f"gmail_{claim.get('email_id', '')}",
            "document_type": "gmail_claim",
            "claim_index": idx,
            "claim_number": claim.get("claim_number", ""),
            "creditor_name": claim.get("creditor_name", ""),
            "amount_claimed": claim.get("amount_claimed", ""),
            "email_id": claim.get("email_id", ""),
            "date": claim.get("date", ""),
            "is_reply": claim.get("is_reply", False),
        }
        
        doc = Document(
            page_content=content,
            metadata=metadata
        )
        documents.append(doc)
    
    # Sort by claim number in descending order (similar to CourtDrive)
    def extract_claim_number(doc: Document) -> int:
        claim_num = doc.metadata.get("claim_number", "")
        try:
            return int(claim_num) if claim_num else 0
        except (ValueError, TypeError):
            return 0
    
    documents.sort(key=extract_claim_number, reverse=True)

    return documents


# Called by: service.generate_payload_withdraw_from_hearing_for_session_gmail (L3A -> routes/order_stream.py)
#            service.generate_order_value_payload_for_session_gmail (L3A -> routes/order_stream.py)
def search_and_extract_subject_email(
    case_number: str,
    subject_title: str,
    docket_text_filter: Optional[str] = None,
    creditor_text_filter: Optional[str] = None,
    body_text_filter: Optional[str] = None,
    oldest: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Search Gmail for an original email matching both case_number and subject_title.

    Strips replies by keeping only the oldest message per thread (the original filing),
    then returns either the most recently filed or the oldest original.

    Args:
        case_number:          Case number to search for (e.g., "25-14980")
        subject_title:        Subject keyword filter (e.g., "Notice of Hearing")
        docket_text_filter:   Optional motion type to match inside the "Docket Text:" section
                              of the email body (e.g., "Motion to Withdraw"). Case-insensitive.
                              If provided, emails whose Docket Text does not mention this string
                              are skipped.
        creditor_text_filter: Optional creditor name to match inside the "Creditor Name:" section
                              of the email body (e.g., "USAA Federal Savings Bank").
                              Case-insensitive. If provided, emails whose Creditor Name section
                              does not mention this string are skipped. Useful for filtering
                              "Proof of Claim" emails by a specific creditor.
        body_text_filter:     Optional string that must appear anywhere in the email body.
                              Case-insensitive. If provided, emails that do not contain this
                              string are skipped (e.g., "The following transaction was received from").
        oldest:               If True, return the oldest matching original instead of the latest.
                              Default is False (returns the most recently filed original).

    Returns:
        Dict with email details and body, or None if no matching email found:
        { "email_id", "thread_id", "subject", "from", "date",
          "body", "case_number", "internal_date" }
    """
    gmail_service = get_gmail_service()

    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = Exception

    def _run_query(q: str):
        try:
            return gmail_service.users().messages().list(
                userId="me",
                q=q,
                maxResults=100,
            ).execute().get("messages", []) or []
        except HttpError as e:
            raise Exception(f"Gmail API search error: {e}")

    # Primary: exact subject phrase (e.g. subject:"Proof of Claim")
    query = f'"{case_number}" subject:"{subject_title}"'
    print(f"[info] Searching Gmail: {query}")
    message_refs = _run_query(query)

    # Fallback 1: single distinctive word in subject (no phrase quotes).
    # Handles concatenated subjects like "Proof of ClaimCH-13 25-24573" where Gmail's
    # phrase tokenizer splits differently.
    if not message_refs:
        words = [w for w in subject_title.split() if len(w) > 3]
        fallback_word = words[-1] if words else subject_title.split()[0]
        fallback_query = f'"{case_number}" subject:{fallback_word}'
        print(f"[info] No results, retrying subject-only fallback: {fallback_query}")
        message_refs = _run_query(fallback_query)

    # Fallback 2: drop subject: constraint, search full text for the phrase.
    # Gmail full-text search matches "Proof of Claim" as a substring of
    # "Proof of ClaimCh-13 25-24573-SMG" even when subject: tokenization fails.
    if not message_refs:
        fulltext_query = f'"{case_number}" "{subject_title}"'
        print(f"[info] No results, retrying full-text fallback: {fulltext_query}")
        message_refs = _run_query(fulltext_query)

    # Fallback 3: partial subject phrase (first 2 words only).
    # Handles cases like "Proof of ClaimCh-13" where Gmail tokenises "ClaimCh-13"
    # as one token — searching subject:"Proof of" still matches because the first
    # two tokens ("Proof", "of") are intact, regardless of what follows.
    # A Python regex post-filter later confirms the full subject_title is present.
    if not message_refs:
        title_words = subject_title.split()
        if len(title_words) >= 3:
            partial_subject = " ".join(title_words[:2])
            partial_query = f'"{case_number}" subject:"{partial_subject}"'
            print(f"[info] No results, retrying partial-subject fallback: {partial_query}")
            message_refs = _run_query(partial_query)

    # Fallback 4 & 5: "Voluntary Petition" bk-format variant.
    # Some VP subjects use the PACER district prefix format, e.g.
    # "3:25-bk-24573 Voluntary Petition (Chapter 7)" where the full token
    # is "3:25-bk-24573" — Gmail treats X:YY-bk-NNNNN as one unit.
    # Quoted phrase search "25-bk-24573" does NOT match "3:25-bk-24573"
    # because the quoted phrase requires an exact contiguous match.
    # Unquoted bk_variant lets Gmail tokenise it into 25 + bk + 24573
    # as individual tokens, each of which appears inside "3:25-bk-24573".
    if not message_refs and subject_title == "Voluntary Petition":
        bk_match = re.match(r"^(\d{2})-(\d+)$", case_number)
        if bk_match:
            year, num = bk_match.groups()
            bk_variant = f"{year}-bk-{num}"  # e.g. "25-bk-24573" (unquoted in queries)

            # Fallback 4: unquoted bk_variant tokens + exact subject phrase
            bk_query = f'{bk_variant} subject:"{subject_title}"'
            print(f"[info] No results, retrying VP bk-format subject fallback: {bk_query}")
            message_refs = _run_query(bk_query)

            # Fallback 5: unquoted bk_variant tokens + full-text subject phrase
            if not message_refs:
                bk_fulltext_query = f'{bk_variant} "{subject_title}"'
                print(f"[info] No results, retrying VP bk-format full-text fallback: {bk_fulltext_query}")
                message_refs = _run_query(bk_fulltext_query)

    if not message_refs:
        print(f"[info] No emails found for case {case_number} with subject '{subject_title}'")
        return None

    print(f"[info] Found {len(message_refs)} messages, fetching details...")

    # Fetch full message details for every ref
    messages: List[Dict[str, Any]] = []
    for ref in message_refs:
        try:
            msg = gmail_service.users().messages().get(
                userId="me",
                id=ref["id"],
                format="full",
            ).execute()

            payload = msg.get("payload", {}) or {}
            headers = payload.get("headers", []) or []

            def _get_hdr(name: str) -> str:
                for h in headers:
                    if h.get("name", "").lower() == name.lower():
                        return h.get("value", "")
                return ""

            messages.append({
                "email_id":      msg["id"],
                "thread_id":     msg["threadId"],
                "internal_date": int(msg.get("internalDate", 0)),
                "subject":       _get_hdr("Subject"),
                "from":          _get_hdr("From"),
                "date":          _get_hdr("Date"),
                "body":          _extract_plain_text(payload),
                "case_number":   case_number,
            })
        except Exception as e:
            print(f"[warn] Error fetching message {ref['id']}: {e}")
            continue

    if not messages:
        return None

    # Python-side subject regex filter.
    # Re.search matches subject_title as a substring of the actual subject, so
    # "Proof of Claim" matches "Proof of ClaimCh-13 25-24573-SMG Jacques Fenelon".
    import re as _re
    subject_pattern = _re.compile(_re.escape(subject_title), _re.IGNORECASE)
    subject_matched = [m for m in messages if subject_pattern.search(m.get("subject", ""))]
    if subject_matched:
        if len(subject_matched) < len(messages):
            print(
                f"[info] Subject regex filter: {len(messages)} → {len(subject_matched)} messages "
                f"(pattern: {subject_title!r})"
            )
        messages = subject_matched
    else:
        print(
            f"[warn] Subject regex filter matched 0 of {len(messages)} messages "
            f"(pattern: {subject_title!r}) — skipping subject filter"
        )

    # Filter by Docket Text content if requested
    if docket_text_filter:
        filter_lower = docket_text_filter.lower()
        filtered = []
        for msg in messages:
            body_lower = (msg.get("body") or "").lower()
            docket_idx = body_lower.find("docket text:")
            if docket_idx == -1:
                print(f"[info] Skipping message {msg['email_id']} subject={msg.get('subject', '(no subject)')!r}: no 'Docket Text:' section found")  # TEMP
                continue
            docket_section = body_lower[docket_idx:]
            if filter_lower in docket_section:
                filtered.append(msg)
            else:
                print(
                    f"[info] Skipping message {msg['email_id']}: "
                    f"'{docket_text_filter}' not found in Docket Text section"
                )
        if not filtered:
            print(f"[info] No emails matched docket_text_filter='{docket_text_filter}'")
            return None
        messages = filtered

    # Filter by Creditor Name content if requested
    if creditor_text_filter:
        filter_lower = creditor_text_filter.lower()
        filtered = []
        for msg in messages:
            body_lower = (msg.get("body") or "").lower()
            creditor_idx = body_lower.find("creditor name:")
            if creditor_idx == -1:
                print(f"[info] Skipping message {msg['email_id']}: no 'Creditor Name:' section found")
                continue
            # Primary: match on the first line only — "Creditor Name:\tUSAA Federal Savings Bank\n"
            # This prevents false matches against the law firm address or notification recipients
            # that appear later in the email body.
            line_end = body_lower.find("\n", creditor_idx)
            creditor_line = body_lower[creditor_idx: line_end if line_end != -1 else creditor_idx + 300]
            if filter_lower in creditor_line:
                filtered.append(msg)
            else:
                # Fallback: check the full creditor block (up to "Claim Number:" or 500 chars)
                # in case the name spans multiple lines or the first-line extraction was incomplete.
                block_end = body_lower.find("claim number:", creditor_idx)
                creditor_block = body_lower[creditor_idx: block_end if block_end != -1 else creditor_idx + 500]
                if filter_lower in creditor_block:
                    print(
                        f"[info] Message {msg['email_id']}: matched '{creditor_text_filter}' "
                        f"in creditor block (not first line)"
                    )
                    filtered.append(msg)
                else:
                    print(
                        f"[info] Skipping message {msg['email_id']}: "
                        f"'{creditor_text_filter}' not found in Creditor Name section"
                    )
        if not filtered:
            print(f"[info] No emails matched creditor_text_filter='{creditor_text_filter}'")
            return None
        messages = filtered

    # Filter by arbitrary body text if requested
    if body_text_filter:
        filter_lower = body_text_filter.lower()
        filtered = [m for m in messages if filter_lower in (m.get("body") or "").lower()]
        if not filtered:
            print(f"[info] No emails matched body_text_filter='{body_text_filter}'")
            return None
        if len(filtered) < len(messages):
            print(f"[info] body_text_filter: {len(messages)} → {len(filtered)} messages (pattern: {body_text_filter!r})")
        messages = filtered

    # Group by thread — keep only the oldest message per thread (original, not replies)
    thread_originals: Dict[str, Dict[str, Any]] = {}
    for msg in messages:
        tid = msg["thread_id"]
        if tid not in thread_originals or msg["internal_date"] < thread_originals[tid]["internal_date"]:
            thread_originals[tid] = msg

    # Sort thread originals — ascending for oldest, descending for latest
    originals = sorted(thread_originals.values(), key=lambda m: m["internal_date"], reverse=not oldest)
    selected = originals[0]

    print(
        f"[info] Selected email ({'oldest' if oldest else 'latest'}): "
        f"subject='{selected['subject']}' date='{selected['date']}' thread={selected['thread_id']}"
    )
    return selected


# Called by: service/order_sustaining_objection.py → generate_payload_objection_sustain_for_session_gmail (else branch)
def search_and_extract_all_subject_emails(
    case_number: str,
    subject_title: str,
    docket_text_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Like search_and_extract_subject_email but returns ALL thread originals
    (one per unique thread, keeping the oldest message per thread) instead of
    just the latest/oldest single result.

    Args:
        case_number:        Case number to search for (e.g., "25-14980")
        subject_title:      Subject keyword filter (e.g., "Objection to Claim")
        docket_text_filter: Optional string that must appear in the "Docket Text:"
                            section of the email body.

    Returns:
        List of dicts (may be empty), each with:
        { "email_id", "thread_id", "subject", "from", "date", "body",
          "case_number", "internal_date" }
        Sorted ascending by internal_date (oldest first).
    """
    gmail_service = get_gmail_service()

    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = Exception

    def _run_query(q: str):
        try:
            return gmail_service.users().messages().list(
                userId="me",
                q=q,
                maxResults=100,
            ).execute().get("messages", []) or []
        except HttpError as e:
            raise Exception(f"Gmail API search error: {e}")

    # Same query chain as search_and_extract_subject_email
    query = f'"{case_number}" subject:"{subject_title}"'
    print(f"[info] search_and_extract_all_subject_emails: {query}")
    message_refs = _run_query(query)

    if not message_refs:
        words = [w for w in subject_title.split() if len(w) > 3]
        fallback_word = words[-1] if words else subject_title.split()[0]
        message_refs = _run_query(f'"{case_number}" subject:{fallback_word}')

    if not message_refs:
        message_refs = _run_query(f'"{case_number}" "{subject_title}"')

    if not message_refs:
        title_words = subject_title.split()
        if len(title_words) >= 3:
            partial_subject = " ".join(title_words[:2])
            message_refs = _run_query(f'"{case_number}" subject:"{partial_subject}"')

    if not message_refs:
        print(f"[info] search_and_extract_all_subject_emails: no emails found for case {case_number} subject '{subject_title}'")
        return []

    print(f"[info] search_and_extract_all_subject_emails: found {len(message_refs)} messages, fetching details...")

    messages: List[Dict[str, Any]] = []
    for ref in message_refs:
        try:
            msg = gmail_service.users().messages().get(
                userId="me",
                id=ref["id"],
                format="full",
            ).execute()

            payload = msg.get("payload", {}) or {}
            headers = payload.get("headers", []) or []

            def _get_hdr(name: str) -> str:
                for h in headers:
                    if h.get("name", "").lower() == name.lower():
                        return h.get("value", "")
                return ""

            messages.append({
                "email_id":      msg["id"],
                "thread_id":     msg["threadId"],
                "internal_date": int(msg.get("internalDate", 0)),
                "subject":       _get_hdr("Subject"),
                "from":          _get_hdr("From"),
                "date":          _get_hdr("Date"),
                "body":          _extract_plain_text(payload),
                "case_number":   case_number,
            })
        except Exception as e:
            print(f"[warn] search_and_extract_all_subject_emails: error fetching {ref['id']}: {e}")
            continue

    if not messages:
        return []

    # Subject regex filter
    import re as _re
    subject_pattern = _re.compile(_re.escape(subject_title), _re.IGNORECASE)
    subject_matched = [m for m in messages if subject_pattern.search(m.get("subject", ""))]
    if subject_matched:
        messages = subject_matched

    # Docket Text filter
    if docket_text_filter:
        filter_lower = docket_text_filter.lower()
        filtered = []
        for msg in messages:
            body_lower = (msg.get("body") or "").lower()
            docket_idx = body_lower.find("docket text:")
            if docket_idx == -1:
                continue
            if filter_lower in body_lower[docket_idx:]:
                filtered.append(msg)
        if not filtered:
            print(f"[info] search_and_extract_all_subject_emails: no emails matched docket_text_filter='{docket_text_filter}'")
            return []
        messages = filtered

    # Deduplicate threads — keep oldest message per thread
    thread_originals: Dict[str, Dict[str, Any]] = {}
    for msg in messages:
        tid = msg["thread_id"]
        if tid not in thread_originals or msg["internal_date"] < thread_originals[tid]["internal_date"]:
            thread_originals[tid] = msg

    originals = sorted(thread_originals.values(), key=lambda m: m["internal_date"])
    print(f"[info] search_and_extract_all_subject_emails: returning {len(originals)} thread original(s)")
    return originals


# Called by: service/cert_service.py → generate_payload_service_for_session_gmail
def search_latest_court_mail(case_number: str) -> Optional[Dict[str, Any]]:
    """
    Search Gmail for the latest Notice of Electronic Filing (NEF) email for a case.

    Searches using the case number only (no subject filter) and filters results
    to emails whose body contains both "Document Number" and "Docket Text:" —
    the two markers that identify a court NEF body.

    Returns the most recently filed matching email, or None if none found.
    """
    gmail_service = get_gmail_service()

    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = Exception

    query = f'"{case_number}"'
    print(f"[info] search_latest_court_mail: querying Gmail: {query}")

    try:
        message_refs = gmail_service.users().messages().list(
            userId="me",
            q=query,
            maxResults=100,
        ).execute().get("messages", []) or []
    except HttpError as e:
        raise Exception(f"Gmail API search error: {e}")

    if not message_refs:
        print(f"[info] search_latest_court_mail: no emails found for case {case_number}")
        return None

    print(f"[info] search_latest_court_mail: found {len(message_refs)} messages, fetching details...")

    messages: List[Dict[str, Any]] = []
    for ref in message_refs:
        try:
            msg = gmail_service.users().messages().get(
                userId="me",
                id=ref["id"],
                format="full",
            ).execute()

            payload = msg.get("payload", {}) or {}
            headers = payload.get("headers", []) or []

            def _get_hdr(name: str) -> str:
                for h in headers:
                    if h.get("name", "").lower() == name.lower():
                        return h.get("value", "")
                return ""

            messages.append({
                "email_id":      msg["id"],
                "thread_id":     msg["threadId"],
                "internal_date": int(msg.get("internalDate", 0)),
                "subject":       _get_hdr("Subject"),
                "from":          _get_hdr("From"),
                "date":          _get_hdr("Date"),
                "body":          _extract_plain_text(payload),
                "case_number":   case_number,
            })
        except Exception as e:
            print(f"[warn] search_latest_court_mail: error fetching message {ref['id']}: {e}")
            continue

    if not messages:
        return None

    # Keep only emails whose body contains both "Document Number" and "Docket Text:"
    nef_messages = []
    for msg in messages:
        body_lower = (msg.get("body") or "").lower()
        if "document number" in body_lower and "docket text:" in body_lower:
            nef_messages.append(msg)
        else:
            print(f"[info] search_latest_court_mail: skipping {msg['email_id']} — missing NEF markers")

    if not nef_messages:
        print(f"[info] search_latest_court_mail: no NEF emails matched for case {case_number}")
        return None

    # Group by thread — keep only the oldest message per thread (original, not replies)
    thread_originals: Dict[str, Dict[str, Any]] = {}
    for msg in nef_messages:
        tid = msg["thread_id"]
        if tid not in thread_originals or msg["internal_date"] < thread_originals[tid]["internal_date"]:
            thread_originals[tid] = msg

    # Return the latest thread original
    selected = max(thread_originals.values(), key=lambda m: m["internal_date"])
    print(
        f"[info] search_latest_court_mail: selected latest NEF: "
        f"subject='{selected['subject']}' date='{selected['date']}'"
    )
    return selected

