"""Prompt instruction for the CaseIngestionAgent — accompanies a base64-attached petition PDF on a HumanMessage."""

_EXTRACTION_INSTRUCTION = (
    "The attached file is '{filename}', a bankruptcy petition. "
    "Read it and return the case number, the list of debtor(s), the "
    "bankruptcy chapter, and the court district. For the debtors list: "
    "look at the 'In re:' caption and return EVERY named debtor in the "
    "order they appear. Solo filing → one name. Joint filing (spouses or "
    "multi-party) → two or more names. Preserve any trailing comma on the "
    "last name as it appears on the petition. Include the bankruptcy "
    "chapter and court district if visible.\n\n"
    "FILED vs UNFILED: return case_number=null when the petition has not "
    "been filed yet. Indicators of an unfiled (in-preparation) petition: "
    "no docket number printed on the cover sheet; the 'Case number (if "
    "known)' field is blank; the petition is a draft/working copy. Do NOT "
    "guess, fabricate, or infer a case number from context — a null value "
    "is the authoritative signal that downstream code uses to create the "
    "row as 'unfiled' (no pgvector indexing, awaiting later filing)."
)
