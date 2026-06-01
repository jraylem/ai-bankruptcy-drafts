"""Prompt builder for `CaseVectorVisionAgent`.

The agent reads the petition PDF as a Document content block AND the
text portion produced here. The text lists each low-confidence
case_vector field's metadata (property_name, topical query from the
author's source_params, instruction, sample marker) so the LLM knows
what to extract from the PDF and which existing low-confidence
reasoning it's correcting.

`source_params.text_query` (the author-supplied topical query) is
treated as the AUTHORITATIVE description of what to extract. The
property_name is just a label — when its literal meaning conflicts
with the topical query (e.g. `plaintiff_name` whose query is "case
filed against the debtor under SOFA #9"), the topical query wins.
"""

from typing import Any

from ...types.sources import CaseVectorSourceParams, VectorSourceParams
from ...types.spec import TemplateField


_PROMPT_TEMPLATE = """You are re-extracting field values for a bankruptcy template directly from the petition PDF attached as a Document. Pgvector chunk retrieval missed (or low-confidenced) these fields — typically because the values live in checkboxes, tables, or layout-sensitive form regions that don't survive chunking. Read the PDF visually as a paralegal would.

CASE CONTEXT
{case_details_block}

FIELDS TO RE-EXTRACT
{fields_block}

INSTRUCTIONS
- For each field above, return a `ResolvedTemplateValue` carrying:
  - `property_name` — must EXACTLY match the field's listed property_name.
  - `value` — the value extracted from the PDF, formatted to match the field's instruction / sample marker. Use `""` (empty string) ONLY when the PDF genuinely doesn't carry the field.
  - `reasoning` — a brief sentence citing the PDF page/section you pulled the value from (e.g. "Page 3, item 9 — checkbox 'Yes' marked, case number 25-12345 written below").
  - `confidence` — `"high"`, `"medium"`, or `"low"` based on how certain you are after reading the rendered PDF. The pipeline will REPLACE the previous low-confidence value with what you return, so be honest about confidence.

- **TOPICAL QUERY IS AUTHORITATIVE.** When a field has a `topical query` line, that is the AUTHOR'S DESCRIPTION of what they want extracted — written in their own words. It overrides any literal interpretation of `property_name`. Example: a field named `plaintiff_name` with topical query "Case filed against the debtor under SOFA question number 9" means navigate to SOFA Q9 (the lawsuits the debtor is a party to) and return the OPPOSING PARTY's name (the actual plaintiff in the state-court suit), NOT the bankruptcy debtor. Do NOT fall back to a generic interpretation of the variable name when a topical query is present.
- **Don't substitute the debtor for missing values.** If the topical query asks for something that a bankruptcy petition genuinely doesn't carry, return `""` and `confidence="low"` — do NOT invent the debtor / petitioner as a stand-in.
- Treat checkboxes literally: read which one is filled, follow the form's flow, and report the answer the form is actually capturing — not the question text.
- For numeric / date fields, normalize whitespace but preserve the form's exact characters (case numbers like "25-19062-SMG" stay verbatim; dates stay in the form's format and the heal pass will normalize them).
- Do NOT invent fields that aren't listed above. Return values only for the fields explicitly enumerated.

Return your output as a single `_VisionExtraction` object containing the list of resolved values."""


def _format_case_details(case_details: dict[str, Any] | None) -> str:
    if not case_details:
        return "(no case details available)"
    rows = [f"- {k}: {v}" for k, v in case_details.items() if v is not None]
    return "\n".join(rows) if rows else "(no case details available)"


def _extract_text_query(field: TemplateField) -> str | None:
    """Pull `text_query` off case_vector source_params if present.

    Both `CaseVectorSourceParams` (text_query optional) and
    `VectorSourceParams` (text_query required) carry the field — they
    coexist for back-compat per the validators.
    """
    params = field.source_params
    if isinstance(params, (CaseVectorSourceParams, VectorSourceParams)):
        query = (params.text_query or "").strip()
        return query or None
    return None


def _format_field(field: TemplateField, idx: int) -> str:
    instruction = (field.instruction or "").strip() or "(no instruction provided)"
    marker = (field.template_property_marker or "").strip() or "(no sample marker)"
    text_query = _extract_text_query(field)
    lines = [f"{idx}. property_name: `{field.property_name}`"]
    if text_query:
        lines.append(f"   topical query (authoritative): {text_query}")
    lines.append(f"   instruction: {instruction}")
    lines.append(f"   sample marker (canonical shape): `{marker}`")
    return "\n".join(lines)


def build_vision_extraction_prompt(
    fields: list[TemplateField],
    case_details: dict[str, Any] | None,
) -> str:
    """Assemble the text portion of the multimodal prompt."""
    case_details_block = _format_case_details(case_details)
    fields_block = "\n\n".join(_format_field(f, idx) for idx, f in enumerate(fields, start=1))
    return _PROMPT_TEMPLATE.format(
        case_details_block=case_details_block,
        fields_block=fields_block,
    )
