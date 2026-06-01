# Called by: GmailMotionWithdrawAgent (agents/withdraw.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_WITHDRAW_GMAIL = {
    "debtor_name_withdraw": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition PDF. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_withdraw": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number with its judge initial suffix from the Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_withdraw": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the Gmail email content (e.g. '13' or '7'). "
        "Do not include the word 'chapter'. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "judge_initial_withdraw": (
        "You are a precise legal assistant. "
        "Extract ONLY the judge initial suffix from case numbers in the Gmail email content. "
        "Case number format: xx-xxxxx-XXX — return ONLY the XXX part (e.g. '25-22321-CLC' -> 'CLC'). "
        "DO NOT extract from trustee names, debtor names, or any other names. "
        "DO NOT convert names to initials. "
        "Examples: '25-22321-CLC' -> 'CLC', '26-10000-XYZ' -> 'XYZ', '25-14980-PDR' -> 'PDR'. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_withdraw_pdf": (
        "You are a precise legal assistant. "
        "Extract ONLY the base bankruptcy case number from the bankruptcy petition PDF. "
        "Format: xx-xxxxx (e.g. '25-14980') — do NOT include a judge initial suffix. "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_withdraw_pdf": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the bankruptcy petition PDF (e.g. '13' or '7'). "
        "Do not include the word 'chapter'. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "debtor_current_addy_withdraw": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's current residential address from the bankruptcy petition PDF (typically in Part 1 or address section). "
        "Return the complete address (street, city, state, zip) — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}
