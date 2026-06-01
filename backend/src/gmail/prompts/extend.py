# Called by: GmailMotionExtendAgent (agents/extend.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_EXTEND_GMAIL = {
    "court_district_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the court district from the bankruptcy petition PDF. "
        "Locate the line beginning with 'United States Bankruptcy Court for the' and return the full district name that follows (e.g. 'Southern District of Florida'). "
        "Return the district name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "debtor_name_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition PDF. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "petition_date_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the date the bankruptcy petition was executed/signed from the PDF. "
        "Format: Month D, YYYY (e.g. 'January 1, 2025'). "
        "Return the date only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number with its judge initial suffix from the Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-12345-ABC'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "court_division_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the court division from the Gmail email content (e.g. 'Miami Division', 'Fort Lauderdale Division'). "
        "Look for phrases like 'hearing will be held at' or courthouse address references. "
        "Return the division name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "dismissed_case_number_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the base case number of the previously dismissed case from the Gmail email content. "
        "This is found near 'was dismissed on'. Return ONLY the base case number without judge initial (e.g. '25-12345'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "dismissed_case_number_with_judge_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the dismissed case number with its judge initial suffix from the dismissed case Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-12345-ABC'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "docket_entry_number_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the document number related to the dismissal from the dismissed case Gmail email content. "
        "Look for the docket entry where the docket text contains 'Order Granting Dismissal'. "
        "Return the document number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "trustees_reason_extend": (
        "You are a precise legal extraction assistant. "
        "Extract ONLY the trustee's or clerk's reason explaining why the case was dismissed from the Gmail email content. "
        "Begin the output with the exact phrase 'due to ...' and keep it short (e.g. 'due to payment failure', 'due to failure to file reports'). "
        "Look for sections labeled 'Clerk\\'s Evidence', 'Trustee\\'s Reason', or 'Reason for Dismissal'. "
        "Do NOT infer or speculate — use verbatim wording from the email. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "dismissal_date_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the date the case was dismissed from the Gmail email content. "
        "Look for the phrase 'was dismissed on' or 'was closed on'. "
        "Format: Month D, YYYY (e.g. 'January 1, 2025'). "
        "Return the date only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_extend": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the Gmail email content (e.g. '13' or '7'). "
        "Do not include the word 'chapter'. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}
