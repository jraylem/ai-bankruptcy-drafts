# Called by: GmailMotionObjectionClaimAgent (agents/objection_claim.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_OBJECTION_CLAIM_GMAIL = {
    "debtor_name_objection": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition PDF. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_objection": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number with its judge initial suffix from the Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "slot_objection": """
    NOTE: This field is now directly extracted without AI. The tool returns the claim numbers directly.
    If you see this prompt, the tool should be invoked directly.
    """,

    "claimant_name_objection": """
    NOTE: This field is now directly extracted without AI. The tool returns the creditor names directly.
    If you see this prompt, the tool should be invoked directly.
    """,

    "claim_amount_objection": """
    NOTE: This field is now directly extracted without AI. The tool returns the claim amounts directly.
    If you see this prompt, the tool should be invoked directly.
    """,

    "judge_initial_objection": (
        "You are a precise legal assistant. "
        "Extract ONLY the judge initial suffix from the case number in the Gmail email content. "
        "Case number format: xx-xxxxx-XXX — return ONLY the XXX part (e.g. '25-14980-PDR' -> 'PDR'). "
        "Return the judge initial only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}
