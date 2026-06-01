# Called by: GmailMotionObjectionSustainNoUploadAgent, GmailMotionObjectionSustainAgent (agents/order_sustaining_objection.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

# Called by: GmailMotionObjectionSustainNoUploadAgent (agents/order_sustaining_objection.py)
INDIVIDUAL_FIELD_PROMPTS_OBJECTION_SUSTAIN_NO_UPLOAD_GMAIL = {
    "debtor_name_objection_sustain": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_objection_sustain": (
        "You are a precise legal assistant. "
        "Extract ONLY the base bankruptcy case number from the petition document. "
        "Format: xx-xxxxx (e.g. '25-12345') — no judge initial suffix. "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_number_objection_sustain": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the Gmail email content (e.g. '13' or '7'). "
        "Do not include the word 'Chapter' — return the number only. "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "judge_initial_objection_sustain": (
        "You are a precise legal assistant. "
        "Look for a case number in the format xx-xxxxx-XXX in the Gmail email content "
        "(e.g. '25-22288-PDR', '26-10000-XYZ'). "
        "Extract ONLY the 3-letter judge initial suffix (the XXX part after the last hyphen). "
        "Do NOT extract from trustee names, debtor names, or any other text — only from case number format. "
        "Return the 3-letter suffix only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_objection_sustain_gmail": (
        "You are a precise legal assistant. "
        "Extract ONLY the full bankruptcy case number with its judge initial suffix from the Gmail email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-22288-PDR'). "
        "Return the full case number including judge initial — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}

# Called by: GmailMotionObjectionSustainAgent (agents/order_sustaining_objection.py)
# Only slot number and creditor — all other fields come from the no-upload path (petition PDF + Gmail)
INDIVIDUAL_FIELD_PROMPTS_OBJECTION_SUSTAIN_GMAIL = {
    "slot_numb_objection_sustain": (
        "You are a precise legal assistant. "
        "Find the claim slot number from the objection PDF using ONLY these two sources (in order): "
        "1) The document header line formatted as 'OBJECTION TO CLAIM #X-X FILED BY ...' — "
        "   extract the number immediately after '#' (e.g. 'OBJECTION TO CLAIM #2-1 FILED BY...' → '2-1'). "
        "2) If no header, look for a table column labeled 'Claim No.' and return the value in that column. "
        "Return the slot number only (e.g. '2-1'). "
        "If neither source is found, return 'N/A'. "
        + _STRICT
    ),

    "creditor_objection_sustain": (
        "You are a precise legal assistant. "
        "Find the creditor name from the objection PDF using ONLY these two sources (in order): "
        "1) The document header line formatted as 'OBJECTION TO CLAIM #X-X FILED BY <CREDITOR NAME>' — "
        "   extract everything after 'FILED BY' (e.g. 'OBJECTION TO CLAIM #2-1 FILED BY LVNV FUNDING, LLC' → 'LVNV FUNDING, LLC'). "
        "2) If no header, look for a table column labeled 'Name of Claimant' and return the value in that column. "
        "Return the creditor name only (e.g. 'LVNV FUNDING, LLC'). "
        "If neither source is found, return 'N/A'. "
        + _STRICT
    ),
}
