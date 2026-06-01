# Called by: GmailMotionSuggestionAgent (agents/suggestion.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_SUGGESTION_GMAIL = {
    "case_number_suggestion": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number with its judge initial suffix from the email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. " + _STRICT
    ),

    "case_number_suggestion_pdf": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number from the bankruptcy petition PDF. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. " + _STRICT
    ),

    "district_suggestion": (
        "You are a precise legal assistant. "
        "Locate the line that begins with 'United States Bankruptcy Court for the' in the bankruptcy petition PDF. "
        "Extract the district name that follows (e.g., 'Southern District of Florida'). "
        "Return ONLY the directional word — the first word of the district name (e.g., 'Southern', 'Northern', 'Middle', 'Eastern', 'Western'). "
        "Do NOT include 'District', 'of Florida', or any other text — just the single directional word. "
        "If not found, return 'N/A'. " + _STRICT
    ),

    "creditor_suggestion": (
        "You are a precise legal assistant. "
        "Look in the Statement of Financial Affairs, specifically the section titled "
        "'Identify Legal Actions, Repossessions, and Foreclosures' (question 9). "
        "Each entry has a case title in the format: '[Creditor], Plaintiff vs. [Debtor], et al Defendant' "
        "or '[Creditor] vs. [Debtor]', followed by a case number. "
        "Extract ONLY the creditor name from EACH entry — the text that appears BEFORE 'vs.' in the case title. "
        "Do NOT include 'Plaintiff', 'vs.', or anything after 'vs.'. "
        "Examples: 'KEYBANK NA, Plaintiff vs. ...' → 'KEYBANK NA'; "
        "'Capital One, N.A. vs. ...' → 'Capital One, N.A.'; "
        "'NATIONSTAR MORTGAGE LLC Plaintiff vs. ...' → 'NATIONSTAR MORTGAGE LLC'; "
        "'WELLS FARGO BANK N A\\nvs.\\nO CONNER, CORLISS NINA\\n2026CA000285' → 'WELLS FARGO BANK N A'. "
        "If multiple entries exist, return each creditor name on its own line, in the order they appear. "
        "If not found, return 'N/A'. " + _STRICT
    ),

    "vs_case_no_suggestion": (
        "You are a precise legal assistant. "
        "Look in the Statement of Financial Affairs, specifically the section titled "
        "'Identify Legal Actions, Repossessions, and Foreclosures' (question 9). "
        "For each legal action entry, extract ONLY the civil case number (not the bankruptcy case number). "
        "Case numbers may contain letters, digits, and hyphens (e.g. 'CACE23012999', 'CACE-23-014226', '19CC001636', 'CONO-25-075332', 'CONO25072975', 'COSO25033485', 'CACE21000349'). "
        "The case number may appear in TWO different formats — handle both: "
        "FORMAT 1 — Inline after the case title: the case number appears at the END of the case title line, after 'Defendant' or after the debtor name. "
        "  Example: 'NATIONSTAR MORTGAGE LLC Plaintiff vs. ALTAGRACE M JEANTY, et al Defendant CACE23012999' → 'CACE23012999'. "
        "FORMAT 2 — Labeled field: the case number appears on its own line directly below a 'Case number' label. "
        "  Example: 'Case number\\nCACE21000349' → 'CACE21000349'; "
        "  Example: 'Case title\\nGeico General Insurance Company\\nPlaintiff vs. Demetric Toporis Lee\\nDefendant\\nCase number\\nCACE21000349' → 'CACE21000349'; "
        "  Example: 'Case title\\nAMERICAN\\nEXPRESS NATIONAL\\nBANK Plaintiff vs.\\nJACQUES FENELON\\nDefendant\\nCase number\\nCONO25072975' → 'CONO25072975' (the case title may span multiple lines before the Case number label). "
        "Additional inline examples: "
        "'Mercury Indemnity Company Of Ame vs. KIM BROWN, KIM LEWIS 19CC001636' → '19CC001636'; "
        "'KEYBANK NA, Plaintiff vs. CURAE TESTING SOLUTIONS LLC, et al Defendant COSO25033485' → 'COSO25033485'; "
        "'The Bank of New York Mellon FKA the Bank of New York As Trustee for the Certificate Holders of CWABS, Inc., Asset-Backed Certificates, Series 2007-BCI vs Kirk Edwards CACE-23-014226' → 'CACE-23-014226'. "
        "Do NOT include creditor names, debtor names, 'Plaintiff', 'Defendant', 'vs.', or the label 'Case number'. "
        "If multiple entries exist, return each case number on its own line, in the order they appear. "
        "If no case numbers are found, return 'N/A'. " + _STRICT
    ),

    "debtor_name_suggestion": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. " + _STRICT
    ),

    "date_filed_suggestion": (
        "You are a precise legal assistant. "
        "Extract ONLY the date when the bankruptcy petition was filed. "
        "Look for filing date information in the document header, footer, or signature area. "
        "Return ONLY the date in YYYY-MM-DD format (e.g. '2025-10-20'). "
        "Convert any date format found in the document to YYYY-MM-DD format. "
        "Always use 2 digits for month and day (pad with zero if needed). "
        "If not found, return 'N/A'. " + _STRICT
    ),

    "court_agency_suggestion": (
        "You are a precise legal assistant. "
        "Look in the Statement of Financial Affairs, specifically the section titled "
        "'Identify Legal Actions, Repossessions, and Foreclosures' (question 9). "
        "Each entry contains a 'Court or agency' field. "
        "Extract ONLY the court or agency name from EACH entry. "
        "Return the name verbatim — no labels, no explanation. "
        "Examples: 'MARION CIRCUIT COURT - OCALA', 'Broward County Court', "
        "'Broward County Circuit Court', 'Clay County Clerk of Courts'. "
        "Do NOT include the street address or zip code if present — return only the court name. "
        "If multiple entries exist, return each court or agency name on its own line, in the order they appear. "
        "If not found, return 'N/A'. " + _STRICT
    ),
}
