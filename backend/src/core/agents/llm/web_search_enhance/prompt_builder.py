"""Prompt builder for `WebSearchEnhanceAgent`.

The agent runs a SINGLE web search round-trip per case_vector field whose
author has flipped `enable_web_search=True`. Inputs are:
  - `variable_name` (label only)
  - `current_value` (the anchor — what case_vector + vision pulled from
    the petition; the search starts here)
  - `template_property_marker` (sample shape of the desired output)
  - `template_paragraph` (the docx prose surrounding the placeholder, used
    only as a grammar/tone reference; may be `None` if the placeholder
    isn't found in the rendered template)
  - `case_details` (debtor / case number / chapter — for cross-reference)

The prompt is fully GENERIC — it does not reference Florida, judicial
circuits, court addresses, or any concrete domain. Same prompt is supposed
to handle "Broward → 17th circuit", a court address lookup, or an
attorney's bar number — anything where the petition reveals the topic but
the *missing fact* is one stable lookup away.

The model is told to emit reasoning + tool calls inline, then wrap the
final reshaped string in `<answer>...</answer>` tags. The agent strips
those tags from the last assistant turn. If no `<answer>` tag is present,
the resolver falls through to the original `current_value`.
"""

from typing import Any


_PROMPT_TEMPLATE = """You are enhancing a single bankruptcy template variable. Pgvector retrieval and (when applicable) the vision pass have already extracted the value from the case file. Your job is to use Anthropic's web search tool to look up ONE small piece of stable, factual context that the petition itself does NOT carry, then reshape the result so it drops cleanly into the docx placeholder.

VARIABLE
- name: `{variable_name}`
- current_value (the anchor — extracted from the petition / case file): `{current_value}`

TARGET SHAPE
- template_property_marker (a sample-case value showing the prose pattern the output should match): `{template_property_marker}`

SURROUNDING CONTEXT
- template_paragraph (the docx prose that contains the placeholder for this variable):
{template_paragraph_block}

CASE DETAILS
{case_details_block}
{web_search_instruction_block}{output_instruction_block}
INSTRUCTIONS

1. **The current_value is your anchor.** It tells you WHICH real-world entity this variable is about for THIS specific case. Compare its shape against `template_property_marker` to identify what's MISSING — the marker shows the full prose pattern, the current_value shows what part of that pattern the petition already gave you. Search for the missing piece only.

2. **template_property_marker is a SHAPE, not a fact source.** The marker comes from a different draft for a different case. Match its prose pattern (capitalization, ordering, connector words like "IN AND FOR", "of the", suffix labels like ", FLORIDA") VERBATIM. Do NOT copy any literal facts from the marker (a specific number, county, court name, or year that appears in it belongs to that other case). Treat the marker as a fill-in-the-blank template you reshape from your own case's facts.

3. **template_paragraph is for grammar / tone only.** Read the paragraph to see how the placeholder is used in a sentence — what tense, articles, prepositions, capitalization the surrounding prose expects. Your output must drop into the placeholder so the resulting sentence reads naturally. Do NOT borrow facts from the paragraph either; many paragraphs in legal templates contain other variables that are unrelated.

4. **Use web search sparingly and specifically.** Compose at most a handful of targeted queries that combine the anchor with the surrounding-paragraph topic + case_details where useful. You may issue up to 3 searches; you will rarely need more than 1. If your first search resolves it, stop searching.

5. **If the lookup fails or is ambiguous, return the current_value unchanged.** Do not invent. Do not approximate. It's better to leave the field at the petition's wording than to hallucinate the missing piece.

6. **AUTHOR INSTRUCTIONS ARE AUTHORITATIVE.** When WEB SEARCH INSTRUCTION or OUTPUT INSTRUCTION (above) conflict with the marker's literal shape OR the surrounding paragraph's grammar, follow the AUTHOR INSTRUCTIONS first. Examples: marker shows `11` but OUTPUT INSTRUCTION says "use ordinal" → emit `11TH`; WEB SEARCH INSTRUCTION says "search by county; ignore federal court" → narrow your queries accordingly even if a federal court answer is more readily findable.

7. **Final answer wrapped in `<answer>` tags.** After your reasoning and any tool calls, emit ONE final assistant turn that ends with `<answer>YOUR FINAL STRING</answer>` on its own line. The `<answer>` content is what fills the docx — no quotes, no labels, no commentary inside the tags. Just the prose value, shaped to match template_property_marker (with AUTHOR INSTRUCTIONS overrides applied), ready to drop into the paragraph above where the placeholder sits.

Now do the work."""


_WEB_SEARCH_INSTRUCTION_BLOCK = """
WEB SEARCH INSTRUCTION — author's directive for the search step (authoritative; see rule 6):
    {web_search_instruction}
"""


_OUTPUT_INSTRUCTION_BLOCK = """
OUTPUT INSTRUCTION — author's rule for the final docx output shape (authoritative; see rule 6):
    {output_instruction}
"""


def _format_case_details(case_details: dict[str, Any] | None) -> str:
    if not case_details:
        return "(no case details available)"
    rows = [f"- {k}: {v}" for k, v in case_details.items() if v is not None]
    return "\n".join(rows) if rows else "(no case details available)"


def _format_paragraph(template_paragraph: str | None) -> str:
    if not template_paragraph or not template_paragraph.strip():
        return "(surrounding paragraph not available — match the marker's shape and write neutrally)"
    return template_paragraph.strip()


def _render_web_search_instruction_block(web_search_instruction: str | None) -> str:
    if not web_search_instruction or not web_search_instruction.strip():
        return ""
    return _WEB_SEARCH_INSTRUCTION_BLOCK.format(
        web_search_instruction=web_search_instruction.strip(),
    )


def _render_output_instruction_block(output_instruction: str | None) -> str:
    if not output_instruction or not output_instruction.strip():
        return ""
    return _OUTPUT_INSTRUCTION_BLOCK.format(output_instruction=output_instruction.strip())


def build_web_search_enhance_prompt(
    variable_name: str,
    current_value: str,
    template_property_marker: str,
    template_paragraph: str | None,
    case_details: dict[str, Any] | None,
    web_search_instruction: str | None = None,
    output_instruction: str | None = None,
) -> str:
    """Assemble the single-turn web-search-enhance prompt."""
    return _PROMPT_TEMPLATE.format(
        variable_name=variable_name,
        current_value=current_value,
        template_property_marker=template_property_marker,
        template_paragraph_block=_format_paragraph(template_paragraph),
        case_details_block=_format_case_details(case_details),
        web_search_instruction_block=_render_web_search_instruction_block(web_search_instruction),
        output_instruction_block=_render_output_instruction_block(output_instruction),
    )
