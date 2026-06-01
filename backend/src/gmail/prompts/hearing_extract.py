# Called by: GmailHearingExtractAgent (agents/hearing_extract.py)
_STRICT = (
    ' If the value is not found, return "N/A".'
    ' Your ENTIRE response must be the requested value and nothing else.'
    ' No markdown, no bold, no bullet points, no extra context.'
    ' Do NOT ask for clarification or additional information under any circumstances.'
)

HEARING_EXTRACT_FIELDS_VALUE = {
    "DocketNumber": (
        'the number inside the square brackets that appears in the Docket Text section '
        'after "Re: [" — this is the referenced motion docket number, NOT the Document Number at the top. '
        'Example: in "Notice of Hearing by Filer (Re: [34] Motion to Value..." return "34". '
        'Return as string, digits only.'
        + _STRICT
    ),
    "TrusteeCalendar": (
        'the hearing date and time that appears after "Hearing scheduled for" in the Docket Text section. '
        'Example: in "Chapter 13 Hearing scheduled for 02/12/2026 at 10:00 AM U.S. Courthouse..." '
        'return "02/12/2026 at 10:00 AM". '
        'Return exactly the date and time only, no location or extra text.'
        + _STRICT
    ),
}


HEARING_EXTRACT_FIELDS_WAIVE = {
    "DocketNumber": (
        'the number inside the square brackets that appears in the Docket Text section '
        'after "Re: [" — this is the referenced motion docket number, NOT the Document Number at the top. '
        'Example: in "Notice of Hearing by Filer (Re: [34] Motion to Waive..." return "34". '
        'Return as string, digits only.'
        + _STRICT
    ),
    "TrusteeCalendar": (
        'the hearing date and time that appears after "Hearing scheduled for" in the Docket Text section. '
        'Example: in "Chapter 13 Hearing scheduled for 02/12/2026 at 10:00 AM U.S. Courthouse..." '
        'return "02/12/2026 at 10:00 AM". '
        'Return exactly the date and time only, no location or extra text.'
        + _STRICT
    ),
}

PROOF_OF_CLAIM_EXTRACT_FIELDS_AMOUNT = {
    "AmountClaimed": (
        'the dollar amount that appears after "Amount Claimed:" in the email body. '
        'Example: in "Amount Claimed: $1000" return "1000". '
        'Return the number only — no dollar sign, no commas, no extra text.'
        + _STRICT
    ),
    "AmountSecured": (
        'the dollar amount that appears after "Amount Secured:" in the email body. '
        'Example: in "Amount Secured: $2000" return "2000". '
        'Return the number only — no dollar sign, no commas, no extra text.'
        + _STRICT
    ),
    "ClaimSlot": (
        'the claim number that appears immediately after "Claim Number:" in the email body, '
        'before any "&nbsp" or "Claims Register" text. '
        'Example: in "Claim Number: 3 &nbsp &nbsp Claims Register" return "3". '
        'Return the number only — digits only, no extra text.'
        + _STRICT
    ),
}

PETITION_EXTRACT_FIELDS_DATE_FILED = {
    "DateFiled": (
        'the date that appears after "filed on" in the email body. '
        'Example: in "The following transaction was received from Chad T Van Horn entered on 3/9/2026 '
        'at 2:35 PM EDT and filed on 3/9/2026" return "3/9/2026". '
        'Return exactly the date only in M/D/YYYY format, no time or extra text.'
        + _STRICT
    ),
}

HEARING_EXTRACT_FIELDS_WITHDRAW = {
    "DocketNumber": (
        'the number inside the square brackets that appears in the Docket Text section '
        'after "Re: [" — this is the referenced motion docket number, NOT the Document Number at the top. '
        'Example: in "Notice of Hearing by Filer (Re: [34] Motion to Withdraw..." return "34". '
        'Return as string, digits only.'
        + _STRICT
    ),
    "TrusteeCalendar": (
        'the hearing date and time that appears after "Hearing scheduled for" in the Docket Text section. '
        'Example: in "Chapter 13 Hearing scheduled for 02/12/2026 at 10:00 AM U.S. Courthouse..." '
        'return "02/12/2026 at 10:00 AM". '
        'Return exactly the date and time only, no location or extra text.'
        + _STRICT
    ),
}


HEARING_EXTRACT_FIELDS_REINSTATE = {
    "DocketNumber": (
        'the number inside the square brackets that appears in the Docket Text section '
        'after "Re: [" — this is the referenced motion docket number, NOT the Document Number at the top. '
        'Example: in "Notice of Hearing by Filer (Re: [34] Motion to Reinstate..." return "34". '
        'Return as string, digits only.'
        + _STRICT
    ),
    "TrusteeCalendar": (
        'the hearing date and time that appears after "Hearing scheduled for" in the Docket Text section. '
        'Example: in "Chapter 13 Hearing scheduled for 02/12/2026 at 10:00 AM U.S. Courthouse..." '
        'return "02/12/2026 at 10:00 AM". '
        'Return exactly the date and time only, no location or extra text.'
        + _STRICT
    ),
}


HEARING_EXTRACT_FIELDS_OBJECTION_SUSTAIN = {
    "DocketNumber": (
        'the number inside the square brackets that appears in the Docket Text section '
        'after "Re: [" — this is the referenced motion docket number, NOT the Document Number at the top. '
        'Example: in "Notice of Hearing by Filer (Re: [34] Objection to Claim..." return "34". '
        'Return as string, digits only.'
        + _STRICT
    ),
    "TrusteeCalendar": (
        'the hearing date and time that appears after "Hearing scheduled for" in the Docket Text section. '
        'Example: in "Chapter 13 Hearing scheduled for 02/12/2026 at 10:00 AM U.S. Courthouse..." '
        'return "02/12/2026 at 10:00 AM". '
        'Return exactly the date and time only, no location or extra text.'
        + _STRICT
    ),
}


HEARING_EXTRACT_FIELDS_EXTEND = {
    "DocketNumber": (
        'the number inside the square brackets that appears in the Docket Text section '
        'after "Re: [" — this is the referenced motion docket number, NOT the Document Number at the top. '
        'Example: in "Notice of Hearing by Filer (Re: [34] Motion to Extend..." return "34". '
        'Return as string, digits only.'
        + _STRICT
    ),
}

DISMISS_EXTRACT_FIELDS_REINSTATE = {
    "DismissedDate": (
        'the date that appears after "filed on" in the email body. '
        'Example: in "The following transaction was received from Williams, Antowanette entered on 9/16/2025 '
        'at 3:39 PM EDT and filed on 09/16/2025" return "09/16/2025". '
        'Return exactly the date only in MM/D/YYYY format, no time or extra text.'
        + _STRICT
    ),
    "DismissalReason": (
        'the reason phrase that appears in the Docket Text section, '
        'between "Order Dismissing Case" and "(Re: #". '
        'Examples: '
        'in "Order Granting Trustee\'s Request for Order Dismissing Case Upon Denial of Confirmation of Plan (Re: # [53])" '
        'return "Upon Denial of Confirmation of Plan". '
        'In "Order Granting Trustee\'s Request for Order Dismissing Case for Failure to Make Pre-Confirmation Plan Payments (Re: # [32])" '
        'return "Failure to Make Pre-Confirmation Plan Payments". '
        'Return the reason phrase only — no parentheses, no extra text.'
        + _STRICT
    ),
}


MEETING_OF_CREDITORS_EXTRACT_FIELDS = {
    "OldDischargeability": (
        'the date that appears after "Last Day to Oppose Discharge or Dischargeability is" in the Docket Text section. '
        'Example: in "Last Day to Oppose Discharge or Dischargeability is 3/24/2026" return "3/24/2026". '
        'Return exactly the date only in M/D/YYYY format, no extra text.'
        + _STRICT
    ),
}


OBJECTION_CLAIM_EMAIL_EXTRACT_FIELDS = {
    "SlotNumb": (
        'the claim slot number inside the square brackets after "[#" in the Docket Text section. '
        'Example: in "Objection to Claim of LVNV Funding, LLC [# 2-1], Filed by Debtor" return "2-1". '
        'Return as string exactly as written (e.g. "2-1"), no extra text.'
        + _STRICT
    ),
    "Creditor": (
        'the creditor name that appears between "Objection to Claim of" and "[#" in the Docket Text section. '
        'Example: in "Objection to Claim of LVNV Funding, LLC [# 2-1], Filed by Debtor" return "LVNV Funding, LLC". '
        'Return the creditor name only, no extra text.'
        + _STRICT
    ),
    "DocketNumber": (
        'the number on the "Document Number:" line near the top of the email, '
        'NOT any number from the Docket Text section. '
        'Example: in "Document Number: 32" return "32". '
        'Return as string, digits only.'
        + _STRICT
    ),
    "TrusteeCalendar": (
        'the date and time that appear after "entered on" near the top of the email body. '
        'Example: in "The following transaction was received from Chad T Van Horn entered on '
        '2/27/2026 at 2:48 PM EST and filed on 2/27/2026" return "2/27/2026 at 2:48 PM". '
        'Return exactly the date and time only (no EST/EDT or extra text).'
        + _STRICT
    ),
}


MOTION_EXTENSION_EXTRACT_FIELDS = {
    "DocketNumber": (
        'Find the structured header block near the top of the email that contains '
        '"Case Name:", "Case Number:", and "Document Number:" on consecutive lines. '
        'Return ONLY the number on the "Document Number:" line. '
        'Example: given the block '
        '"Case Name:\tVincent S Dimino\nCase Number:\t25-21814-PDR\nDocument Number:\t13" '
        'return "13". '
        'Do NOT return any number from the Docket Text section or anywhere else. '
        'Return as string, digits only.'
        + _STRICT
    ),
}

