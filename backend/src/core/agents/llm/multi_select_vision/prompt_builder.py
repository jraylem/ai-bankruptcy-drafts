"""Prompt builder for the MultiSelectVisionAgent.

Re-extracts multi_select option strings directly from the petition PDF
using claude-opus-4-6 Document content blocks. Mirrors DropdownAgent's
extraction prompt but reads PDF visually instead of pgvector chunks.
"""

from src.core.agents.types.sources import MultiSelectFromCaseVectorSourceParams


def build_multi_select_vision_prompt(
    params: MultiSelectFromCaseVectorSourceParams,
    baseline_options: list[str] | None = None,
) -> str:
    """Compose the text portion of the multimodal prompt.

    The PDF rides as a separate Document content block alongside this
    text — see `MultiSelectVisionAgent.run`.

    `baseline_options`, when provided, is rendered as an `<existing_options>`
    block telling the LLM which items have already been extracted by an
    earlier pass. The LLM is instructed to return ONLY new items — items
    that refer to a different real-world entity than anything in the
    baseline, even when shapes differ. Replaces fragile post-merge
    string-equality dedup which can't catch shape variants like
    'Mercedes G-Wagon' vs 'Mercedes G-Wagon - VIN# X'.
    """
    if len(params.example_formats) == 1:
        formats_block = f"    {params.example_formats[0]}"
    else:
        formats_block = "\n".join(f"    - {fmt}" for fmt in params.example_formats)

    existing_options_block = ""
    if baseline_options:
        bullets = "\n".join(f"- {opt}" for opt in baseline_options)
        existing_options_block = (
            "\n<existing_options>\n"
            f"{bullets}\n"
            "</existing_options>\n\n"
            "EXISTING OPTIONS — these have already been extracted by an "
            "earlier pass. For each item you find in the PDF that refers "
            "to the SAME real-world entity as one above (same VIN, street "
            "address, or year+make+model — match on canonical identity, "
            "not string shape), follow this rule:\n"
            "\n"
            "  (a) BASELINE ALREADY MATCHES THE FORMAT WELL → SKIP it. "
            "Do not include the item in your output. Note in "
            "`extraction_notes` which items you skipped.\n"
            "\n"
            "  (b) YOUR VERSION WOULD BETTER MATCH `example_formats` than "
            "the baseline → RETURN your better-shaped version AND set "
            "`supersedes` to the EXACT baseline string (verbatim, copy-"
            "pasted from <existing_options>) it replaces. The resolver "
            "will drop the baseline entry and keep yours.\n"
            "\n"
            "Examples (assume `example_formats` includes "
            "'<Year> <Make> <Model> - VIN <VIN>'):\n"
            "- Baseline: '2018 Mercedes G-Wagon' (no VIN). PDF row: 2018 "
            "Mercedes G-Wagon, VIN WDCYC3KH3JX288288. Your version "
            "matches the format better → RETURN '2018 Mercedes G-Wagon - "
            "VIN WDCYC3KH3JX288288' with supersedes='2018 Mercedes "
            "G-Wagon'.\n"
            "- Baseline: '2022 Kia Stinger - VIN KNAE55LC5N6117584' "
            "(already full match). PDF row: same vehicle. Baseline "
            "already matches → SKIP, do not output.\n"
            "- Baseline: 'Mercedes G-Wagon'. PDF: '2023 Kia Sportage'. "
            "Different vehicles → RETURN the Kia (no supersedes; brand "
            "new item).\n"
            "\n"
            "When deciding (a) vs (b), be conservative — only set "
            "`supersedes` when YOUR version genuinely adds a field "
            "required by `example_formats` that the baseline lacks (VIN, "
            "address, year, etc.). If both shapes are equivalent, prefer "
            "(a) SKIP to avoid noise.\n"
        )

    locator_block = ""
    if params.text_query and params.text_query.strip():
        locator_block = (
            "\n<locator>\n"
            f"{params.text_query.strip()}\n"
            "</locator>\n\n"
            "LOCATOR — author-supplied section / topic guidance for WHERE in "
            "the petition PDF the options live (e.g. which schedule to read, "
            "which categories to include or exclude). Use this to navigate "
            "the form before extracting. If the locator names a specific "
            "schedule (Schedule A/B, Schedule D, Statement of Financial "
            "Affairs, etc.), restrict extraction to that section.\n"
        )

    instruction_block = ""
    if params.instruction and params.instruction.strip():
        instruction_block = (
            "\n<instruction>\n"
            f"{params.instruction.strip()}\n"
            "</instruction>\n\n"
            "INSTRUCTION — author-supplied guidance about WHAT to pick "
            "(selection criteria, exclusions, edge cases). Apply alongside "
            "the format(s) below.\n"
        )

    return f"""You are extracting multi-select option strings DIRECTLY from a petition PDF (attached as a Document content block in this message). The user will later pick one or more options; the picked string(s) fill the '{params.label}' template variable.
{existing_options_block}{locator_block}{instruction_block}
TASK: From the attached PDF, extract a list of options. Each option must resemble the format(s) below:

{formats_block}

GUIDANCE:
- Read the PDF directly — checkbox state, tabular layout, and form-field structure are visible to you. This is exactly the content pgvector chunks lose.
- The petition is a multi-section form (Schedule A/B: Property, Schedule D: Secured Claims, Schedule E/F: Unsecured Claims, Statement of Financial Affairs, etc.). If a LOCATOR is provided above, navigate to that section first; otherwise infer the right section(s) from the format(s) and label.
- EXHAUSTIVE EXTRACTION: Within the targeted section, extract EVERY row that matches any example_format — do NOT stop after the first match. Petition forms list multiple instances by sub-number (e.g. 3.1, 3.2, 3.3 for vehicles; 1.1, 1.2 for real property; "If you own or have more than one, list here:" prompts followed by additional entries). Every numbered sub-entry that satisfies the format is its own option. If the section has 3 vehicles you must return 3 options, not 1.
- When multiple formats are listed above, each extracted option must match ONE of them (not all). Different rows in the PDF may match different formats — for instance, in an asset picker, vehicles match the vehicle format and real property matches the property format.
- Each option is a single line of text by default (no leading bullets or numbering). Multi-line example_formats are preserved verbatim — embed real newlines in the option string only when the format itself contains them.
- Return DISTINCT options — do not repeat the same value twice.
- Prefer values exactly as they appear in the PDF. Do not paraphrase, summarize, or invent details not visible on the page.
- If a source value carries trailing metadata NOT present in the matching format above (e.g. amounts, exemption codes, internal IDs), TRIM it so the option matches the format's structure.
- Cap at 20 options; prefer the most relevant if more exist.
- If the PDF has no plausible options for '{params.label}' under the LOCATOR / INSTRUCTION constraints, return an empty list.

REASONING TRAIL (debug-only, NOT shown to the user):
- For each option, fill `reasoning` with a brief note: which schedule + sub-number it came from (e.g. "Schedule A/B, row 3.2"), which example_format shape it matched, and any field-trimming you did (e.g. "trimmed trailing $ amount"). When you set `supersedes`, also note WHY your version is a better match (e.g. "supersedes baseline 'Mercedes G-Wagon' because format requires VIN").
- Fill `extraction_notes` with overall context: which sections you searched, how many candidate rows you saw vs. how many you returned, why any plausible rows were rejected (e.g. "row 4.1 didn't include a VIN so couldn't fully match the vehicle format"), and which items you SKIPPED because the baseline already represented them well. If you returned 0 options, explain why so the author can adjust the LOCATOR or example_formats.

Return the list of options for '{params.label}'."""
