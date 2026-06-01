# Called by: GmailOrderImposeRegularAgent (agents/order_impose.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_ORDER_IMPOSE_REGULAR_GMAIL = {
    "debtor_name_order_impose_regular": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition PDF. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_order_impose_regular": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number with its judge initial suffix from the Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-12345-ABC'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_order_impose_regular": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the Gmail email content (e.g. '13' or '7'). "
        "Do not include the word 'chapter'. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}
