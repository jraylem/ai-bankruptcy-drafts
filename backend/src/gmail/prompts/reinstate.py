# Called by: GmailMotionReinstateAgent (agents/reinstate.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_REINSTATE_GMAIL = {
    "debtor_name_reinstate": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_reinstate": (
        "You are a precise legal assistant. "
        "Extract ONLY the base bankruptcy case number from the petition document. "
        "Format: xx-xxxxx (e.g. '25-12345') — no judge initial suffix. "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_number_reinstate": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the Gmail email content (e.g. '13' or '7'). "
        "Do not include the word 'Chapter' — return the number only. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_reinstate_gmail": (
        "You are a precise legal assistant. "
        "Extract ONLY the full bankruptcy case number with its judge initial suffix from the Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the full case number including judge initial — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "judge_initial_reinstate": (
        "You are a precise legal assistant. "
        "Look for a case number in the format xx-xxxxx-XXX in the Gmail email content "
        "(e.g. '25-22321-CLC', '26-10000-XYZ'). "
        "Extract ONLY the 3-letter judge initial suffix (the XXX part after the last hyphen). "
        "Do NOT extract from trustee names, debtor names, or any other text — only from case number format. "
        "Return the 3-letter suffix only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

}
