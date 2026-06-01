# Called by: GmailMotionValueAgent (agents/value.py)
_STRICT = (
    "IMPORTANT: Your ENTIRE response must be the requested value and nothing else. "
    "No markdown, no bold, no bullet points, no headers, no extra context, no additional case info. "
    "If the tool fails, returns no results, or you cannot find the value, return 'N/A' immediately. "
    "Do NOT ask for clarification, a session ID, or additional information under any circumstances. "
    "One value. That is all."
)

INDIVIDUAL_FIELD_PROMPTS_VALUE_GMAIL = {
    "case_number_value": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number with its judge initial suffix from the email content. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "case_number_value_pdf": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy case number from the bankruptcy petition PDF. "
        "Format: xx-xxxxx-XXX (e.g. '25-14980-PDR'). "
        "Return the case number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_value": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the email content (e.g. '13' or '7'). "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "chapter_value_pdf": (
        "You are a precise legal assistant. "
        "Extract ONLY the bankruptcy chapter number from the bankruptcy petition PDF (e.g. '13' or '7'). "
        "Return the chapter number only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "debtor_name_value": (
        "You are a precise legal assistant. "
        "Extract ONLY the debtor's full legal name from Part 1 of the bankruptcy petition. "
        "If Debtor 1 only, return that name. "
        "If Debtor 1 and Debtor 2 both exist, return both joined with ' and ' (e.g. 'John Doe and Jane Doe'). "
        "Return the name only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "creditor_value": (
        "You are a precise legal assistant extracting ONLY creditor information from bankruptcy petition PDFs. "
        "Task: Search ALL numbered Schedule D entries under 'List All Secured Claims'. "
        "Skip any entry where the secured property is real estate, a home, a residence, or any non-vehicle asset. "
        "For each remaining entry (vehicles only), the 'Describe the property that secures the claim' field will "
        "contain the car make, model, year, and VIN — read and remember this for later use. "
        "Return the creditor name for EACH vehicle entry found — verbatim text from the document. "
        "If multiple vehicle entries exist, return each creditor name on its own line (one per line). "
        "If the creditor name contains a phrase like 'as Agent for ...', 'as Servicer for ...', "
        "'as Assignee for ...', or any similar 'as <role> for ...' clause, remove that clause entirely "
        "and return only the base creditor name (e.g. 'Quantum 3 Group, LLC as Agent for Wollem' → 'Quantum 3 Group, LLC'). "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "car_model_value": (
        "You are a precise legal assistant. "
        "Step 1: Search ALL numbered Schedule D entries under 'List All Secured Claims'. "
        "Skip any entry where the secured property is real estate, a home, a residence, or any non-vehicle asset. "
        "Step 2: From the 'Describe the property that secures the claim' field of the matching vehicle entry, "
        "extract the vehicle year, make, and model (e.g. '2023 Tesla Model Y'). "
        "Step 3: Confirm that vehicle appears in Schedule A/B by matching the VIN also found in that Schedule D description. "
        "Return the year, make, and model only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "vin_model_value": (
        "You are a precise legal assistant. "
        "Step 1: Search ALL numbered Schedule D entries under 'List All Secured Claims'. "
        "Skip any entry where the secured property is real estate, a home, a residence, or any non-vehicle asset. "
        "Step 2: From the 'Describe the property that secures the claim' field of the matching vehicle entry, "
        "extract the VIN — it will appear as 'VIN#' or 'VIN' followed by the identifier "
        "(e.g. 'VIN# 7SAYGAEE3PF674540'). "
        "Step 3: Confirm that same VIN appears in Schedule A/B under 'Other Information' for that vehicle. "
        "Return the VIN only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "odometer_value": (
        "You are a precise legal assistant. "
        "Step 1: Search ALL numbered Schedule D entries under 'List All Secured Claims'. "
        "Skip any entry where the secured property is real estate, a home, a residence, or any non-vehicle asset. "
        "Step 2: From the 'Describe the property that secures the claim' field of the matching vehicle entry, "
        "note the car make, model, year, and VIN. "
        "Step 3: Find that same vehicle in Schedule A/B. "
        "Use the VIN from Step 2 as the PRIMARY match key — find the Schedule A/B entry whose "
        "'Other information:' field contains that exact VIN. "
        "If the VIN does not match, skip that entry even if the make or model looks similar. "
        "Step 4: In that matched Schedule A/B entry, find the 'Approximate mileage:' field and return its value. "
        "Return the mileage number only (e.g. '57,000') — no labels, no 'Approximate mileage:' prefix, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "value_amount_value": (
        "You are a precise legal assistant. "
        "Step 1: Search ALL numbered Schedule D entries under 'List All Secured Claims'. "
        "Skip any entry where the secured property is real estate, a home, a residence, or any non-vehicle asset. "
        "Step 2: From the 'Describe the property that secures the claim' field of the matching vehicle entry, "
        "note the car make, model, year, and VIN. "
        "Step 3: Find that same vehicle in Schedule A/B. "
        "Use the VIN from Step 2 as the PRIMARY match key — find the Schedule A/B entry whose "
        "'Other information:' field contains that exact VIN. "
        "If the VIN does not match, skip that entry even if the make or model looks similar. "
        "Step 4: Return the 'Current value of the entire property' dollar amount from that matched Schedule A/B entry. "
        "Return the dollar amount only (e.g. '$25,542.00') — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),

    "value_method_value": (
        "You are a precise legal assistant. "
        "Extract ONLY the valuation method used to determine the vehicle's value (e.g. 'KBB', 'NADA', 'Appraisal'). "
        "Step 1: Search ALL numbered Schedule D entries under 'List All Secured Claims'. "
        "Skip any entry where the secured property is real estate, a home, a residence, or any non-vehicle asset. "
        "Step 2: Find that same vehicle in Schedule A/B by matching the make, model, year, "
        "and approximate mileage — there may be multiple entries so match all available identifiers. "
        "Step 3: In that Schedule A/B entry, look under 'Other Information' for the line containing 'VIN#' or 'VIN'. "
        "The valuation method is the text that appears after the VIN number on that same line "
        "(e.g. 'VIN# 7SAYGAEE3PF674540 Using KBB Private Party Value' → return 'KBB Private Party Value'). "
        "Return the valuation method text only — no labels, no explanation. "
        "If not found, return 'N/A'. "
        + _STRICT
    ),
    
}
