# Called by: GmailMotionModifyAgent (agents/modify.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_MODIFY_GMAIL = {
    "court_district_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the court district from the bankruptcy petition PDF. "
        "Locate the line beginning with 'United States Bankruptcy Court for the' and return the full district name that follows (e.g. 'Southern District of Florida'). "
        "Return the district name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "debtor_name_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition PDF. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_no_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number with its judge initial suffix from the Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "court_division_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the court division from the Gmail email content (e.g. 'Fort Lauderdale Division', 'Miami Division'). "
        "Return the division name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the Gmail email content (e.g. '13' or '7'). "
        "Do not include the word 'chapter'. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "confirm_date_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the date the Chapter 13 plan was confirmed from the Gmail email content. "
        "Format: MM DD, YYYY (e.g. 'March 5, 2025'). "
        "If multiple dates appear, use the one associated with the order confirming the plan. "
        "Return the date only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "docket_confirm_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the docket entry number for the order confirming the Chapter 13 plan from the Gmail email content. "
        "If multiple confirmation orders exist, use the one with the MOST RECENT date. "
        "Return the docket entry number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "docket_plan_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the docket entry number for the Chapter 13 plan filing from the Gmail email content. "
        "If multiple plans exist (amended plans), use the one with the MOST RECENT date. "
        "Return the docket entry number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "date_delinquent_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the date the debtor became delinquent in plan payments from the Gmail email content. "
        "Look in 'Notice of Delinquency' emails from the trustee. "
        "Format: MM DD, YYYY (e.g. 'March 5, 2025'). "
        "If multiple notices exist, use the one with the MOST RECENT date. "
        "Return the date only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "docket_notice_modify": (
        "You are a precise legal assistant. "
        "Extract ONLY the docket entry number for the trustee's Notice of Delinquency from the Gmail email content. "
        "Look for 'document number' in 'Notice of Delinquency' emails. "
        "If multiple notices exist, use the one with the MOST RECENT date. "
        "Return the docket entry number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}
