# Called by: GmailMotionServiceAgent (agents/cert_service.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_CERT_SERVICE_GMAIL = {
    "court_district_cert_service": (
        "You are a precise legal assistant. "
        "Extract ONLY the court district from bankruptcy petition PDFs. "
        "Locate the line that begins with 'United States Bankruptcy Court for the' (or similar) "
        "and return the complete district name that follows (e.g., 'Southern District of Florida'). "
        "Return the full district name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_cert_service": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number (with judge initial) from Gmail emails related to the case. "
        "Return the complete case number WITH judge initial suffix (e.g., '25-12345-ABC', '26-10000-XYZ'). "
        "Format: xx-xxxxx-XXX where XXX is the judge initial (typically 3 letters). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "debtor_name_cert_service": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_cert_service": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from Gmail emails related to the case (e.g. '13' or '7'). "
        "Return the chapter number only — do not include the word 'chapter', no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_cert_service_pdf": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number from the bankruptcy petition PDF. "
        "Return the case number EXACTLY as it appears in the document — do NOT reformat or normalize it. "
        "It may appear in PACER format (e.g. '3:26-bk-01451') or standard format (e.g. '26-01451-JAB'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_cert_service_pdf": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the bankruptcy petition PDF (e.g. '13' or '7'). "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
}


_STRICT_HX = (
    ' If the value is not found, return "N/A".'
    ' Your ENTIRE response must be the requested value and nothing else.'
    ' No markdown, no bold, no bullet points, no extra context.'
    ' Do NOT ask for clarification or additional information under any circumstances.'
)

# Known bankruptcy trustees. Names may be stored as "Last First" or "First Last".
_TRUSTEE_NAMES = (
    "Weiner Robin", "Duncan Leigh", "Weatherford Laurie", "Neidich Nancy",
    "Waage Jon", "Remick Kelley", "Neway Douglas", "Smith Daryl",
    "Winnecour Ronda J.", "Abbott Doreen", "Thomas Robert", "Calderin Jacqueline",
    "Tabas Joel", "Dillworth Drew", "Barmat Marc", "Osborne Leslie",
    "Welt Kenneth", "Angueira Robert", "Slott Sonya", "Furr Robert",
    "Mehdipour Nicole", "Hartog Ross", "Garvin Karin", "Cohen Aaron",
    "Mahendru Arvind", "Scharrer Beth", "Stevenson Traci", "Smith Margaret",
    "Chambers Gene", "Noble Emerson", "Cameron Nicole", "Johnson Eugene",
    "Mukamal Barry", "Atwater Gregory", "Brown Scott", "Chancellor Sherry",
    "Bender Theresa", "Chaney Carolyn", "Herendeen Christine", "Crews Gregory",
    "Yip Maria", "Patton Lori", "Webber Richard", "Altman Robert",
    "Menchise Douglas", "Crawford Rosemary C.", "Thornton-Illar Crystal",
    "Carapella Dawn", "Meininger Stephen", "Jones Gordon", "Nacole M. Jipping",
    "Jacobs Eric", "Hyman Larry", "Welch Angela", "Musselman Carla",
    "Henkel Marie", "Pamela J. Wilson", "Paiva Chad", "Menotte Deborah",
    "Dunn Marcia", "Kapila Soneet", "Bakst Michael", "Rivera Luis",
    "Tardif Robert", "Kennedy Dennis", "Dauval Richard", "Colon Mary",
)
_TRUSTEE_LIST_STR = "\n".join(f"- {n}" for n in _TRUSTEE_NAMES)

_TRUSTEE_MATCH_RULES = (
    "Matching rules: "
    "(1) List names may be in 'Last First' format — match by first + last name only. "
    "(2) Ignore middle names or middle initials when comparing "
    "(e.g. 'Robin R Weiner' matches 'Weiner Robin'). "
    "(3) The matching entry may include 'on behalf of' text or be a standalone name line. "
    "(4) There is exactly ONE trustee in the section — return only that result. "
)

HEARING_EXTRACT_FIELDS_CERT_SERVICE_TRUSTEE = {
    "TrusteeName": (
        "You are given the 'Notice will be electronically mailed to:' section of a court NEF email "
        "and a list of known bankruptcy trustees.\n\n"
        f"Known trustees:\n{_TRUSTEE_LIST_STR}\n\n"
        "Find the ONE entry in the section whose person name matches any name on the list above. "
        + _TRUSTEE_MATCH_RULES
        + "Return the FULL name exactly as it appears in the section text (not the list format). "
        "If no match is found, return 'N/A'."
        + _STRICT_HX
    ),
    "TrustEmail": (
        "You are given the 'Notice will be electronically mailed to:' section of a court NEF email "
        "and a list of known bankruptcy trustees.\n\n"
        f"Known trustees:\n{_TRUSTEE_LIST_STR}\n\n"
        "Find the ONE entry in the section whose person name matches any name on the list above. "
        + _TRUSTEE_MATCH_RULES
        + "From that matched entry, return ONLY the FIRST email address listed. "
        "If the entry has multiple comma-separated emails, take only the first one. "
        "If no match or no email, return 'N/A'."
        + _STRICT_HX
    ),
    "USTemail": (
        "You are given the 'Notice will be electronically mailed to:' section of a court NEF email.\n\n"
        "Find the entry labelled 'Office of the US Trustee' and return its FIRST email address. "
        "The email will contain 'USTP' and end with '@usdoj.gov' "
        "(e.g. 'USTPRegion21.MM.ECF@usdoj.gov'). "
        "If the entry has multiple email addresses, return only the first one. "
        "If not found, return 'N/A'."
        + _STRICT_HX
    ),
    "MiscMailListings": (
        "You are given the 'Notice will be electronically mailed to:' section of a court NEF email "
        "and a list of known bankruptcy trustees.\n\n"
        f"Known trustees:\n{_TRUSTEE_LIST_STR}\n\n"
        "Extract ALL parties from the section EXCEPT — skip these entirely:\n"
        "  - Any entry whose name matches a name in the known trustees list above\n"
        "  - The 'Office of the US Trustee' entry and its email(s)\n"
        "  - Any entry whose name contains both 'Chad' and 'Van Horn'\n\n"
        "For each REMAINING party:\n"
        "  - Extract ONLY the person's own name. If the name line contains ' on behalf of', "
        "take ONLY the text BEFORE ' on behalf of' and discard everything after it. "
        "Example: 'Can Guner on behalf of Creditor JPMorgan Chase Bank' → use 'Can Guner' only.\n"
        "  - Take ONLY the FIRST email address from the line(s) below their name\n\n"
        "Return a JSON array of strings, each formatted as 'Name|email'.\n"
        "Example: [\"Can Guner|cguner@raslg.com\", \"Giselle Velez|gvelez@rasflaw.com\"]\n"
        "If no parties remain after exclusions, return an empty array: []\n"
        "Return ONLY the JSON array — no explanation, no markdown."
    ),
}


HEARING_EXTRACT_FIELDS_CERT_SERVICE_HEARING = {
    "DocketMotion": (
        'Find the structured header block near the top of the email that contains '
        '"Case Name:", "Case Number:", and "Document Number:" on consecutive lines. '
        'Return ONLY the number on the "Document Number:" line. '
        'Example: given "Document Number:\t16" return "16". '
        'Return as string, digits only.'
        + _STRICT_HX
    ),
}
