# Called by: GmailMotionExParteExtensionAgent (agents/ex_parte_extension.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_EX_PARTE_EXTENSION_GMAIL = {
    "debtor_name_ex_parte_extension": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition PDF. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_ex_parte_extension": (
        "You are a precise legal assistant. "
        "Extract ONLY the case number from the bankruptcy petition PDF. "
        "Format: xx-xxxxx (e.g. '25-12345'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "date_filed_ex_parte_extension": (
        "You are a precise legal assistant. "
        "Extract ONLY the date the bankruptcy petition was filed from the PDF. "
        "Format: Month D, YYYY (e.g. 'March 5, 2025'). "
        "Return the date only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_number_ex_parte_extension": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the Gmail email content (e.g. '13' or '7'). "
        "Do not include the word 'chapter'. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "judge_ex_parte_extension": (
        "You are a precise legal assistant. "
        "Extract ONLY the judge initial suffix from case numbers in the Gmail email content. "
        "Case number format: xx-xxxxx-XXX — return ONLY the XXX part (e.g. '25-22321-CLC' -> 'CLC'). "
        "DO NOT extract from trustee names or any other names in the email. "
        "DO NOT convert names to initials. "
        "Return the 3-letter judge initial only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "meeting_date_ex_parte_extension": (
        "You are a precise legal assistant. "
        "Extract ONLY the meeting of creditors (341 meeting) date from the Gmail email content. "
        "Format: 'Month D, YYYY' (e.g. 'March 5, 2025'). "
        "Return the date only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}
