"""Prompt builder for `WebEnhanceAgentV2`.

Renders a single-turn instruction that frames the resolved value as
the anchor, the author's `web_enhance_instruction` as authoritative
search guidance, and the template's `template_property_marker` +
surrounding paragraph as shape/tone references. The agent emits any
reasoning + tool calls inline, then wraps the final reshaped string
in `<answer>...</answer>` tags. The caller parses the LAST `<answer>`
match.

This is source-agnostic: the same prompt runs for gmail / case_file /
derived / author_input. The author's instruction is what specializes
each invocation, NOT the source kind.
"""

from __future__ import annotations

from typing import Any


_PROMPT_TEMPLATE = """You are enhancing a single bankruptcy template variable. The upstream pipeline has already extracted a value from the firm's data sources. Your job is to use Anthropic's web search tool to look up one small piece of stable, public context that the firm's data does NOT carry, then return the result in the EXACT shape the docx placeholder expects.

VARIABLE
- name: `{variable_name}`
- current_value (the anchor — extracted by the upstream pipeline): `{current_value}`

TEMPLATE_PROPERTY_MARKER — THE DOCX'S REQUIRED OUTPUT SHAPE
This is the load-bearing rule of this whole task. The marker shows the EXACT prose pattern the rendered docx needs — every capitalization choice, every connector word, every punctuation mark, every suffix, every spacing convention. Any deviation breaks the rendered document.
{template_property_marker_block}

SURROUNDING CONTEXT
- template_paragraph (the docx prose that contains the placeholder for this variable):
{template_paragraph_block}

CASE DETAILS
{case_details_block}

AUTHOR'S WEB ENHANCEMENT INSTRUCTION (the ONLY thing that can deviate from the marker's shape):
    {web_enhance_instruction}
{output_expectation_block}
INSTRUCTIONS — read in order

1. **STRICTLY MATCH `template_property_marker`'s SHAPE.** This is the DEFAULT. The marker dictates every formatting choice: capitalization (UPPER/lower/Title), ordering (state-before-county vs county-before-state), connector words (`IN AND FOR`, `of the`, `, `), suffix labels (`, FLORIDA`, `Judicial Circuit`), digit form (`17` vs `17TH` vs `Seventeenth`), punctuation, spacing. Treat it as a fill-in-the-blank where you only swap in the new fact while keeping every other character of the marker's shape verbatim.

   The marker is from a DIFFERENT case. Do NOT copy the marker's literal facts (its specific county name, its specific number, its specific court name) into your answer — those belong to that other case. Copy only the shape.

2. **The AUTHOR'S INSTRUCTION is the ONLY override channel.** The marker shape is binding unless the author's instruction EXPLICITLY directs a specific deviation. Examples of valid overrides:
   - "use ordinal form" → marker has `17`, emit `17TH` instead
   - "include the FBN suffix" → marker doesn't have it, add it
   - "lowercase the county name" → marker shows `BROWARD`, emit `Broward`

   Generic instructions like "confirm the right circuit" or "look up the bar number" are search guidance, NOT format overrides — keep the marker's shape exactly.

3. **The current_value is your search anchor.** It identifies WHICH real-world entity this variable is about for THIS specific case. Use it (plus case_details when relevant) to scope your queries — e.g. `Clinton County, IA` not just `Clinton County` if the anchor or case details tell you which state.

4. **template_paragraph is for grammar/tone only.** Read it to understand how the placeholder sits in a sentence (tense, articles, prepositions). Do NOT borrow facts from the paragraph and do NOT let it override the marker's shape.

5. **Use web search sparingly.** You may issue up to 3 searches; you will rarely need more than 1. Compose targeted queries combining the anchor with the author's instruction. If your first search resolves it, stop.

6. **If the lookup fails, is ambiguous (e.g. multiple states have a county with this name), or you cannot fit the answer into the marker's shape without losing meaning — return the current_value unchanged.** Do not invent. Do not approximate. Do not break the marker's shape to fit a partial answer. Leaving the field at its pre-enhancement value is always safer than corrupting the rendered docx.

7. **Final answer wrapped in `<answer>` tags.** After your reasoning and any tool calls, emit ONE final assistant turn that ends with `<answer>YOUR FINAL STRING</answer>` on its own line. The `<answer>` content fills the docx VERBATIM — no quotes, no labels, no commentary inside the tags. It must match the marker's shape character-for-character, with only the new fact swapped in (plus any explicit author-instruction overrides applied).

Now do the work."""


_OUTPUT_EXPECTATION_BLOCK = """
OUTPUT EXPECTATION — author's rule for the final docx output shape (authoritative; rule 2 applies):
    {output_expectation}
"""


def _format_case_details(case_details: dict[str, Any] | None) -> str:
    if not case_details:
        return "(no case details available)"
    rows = [f"- {k}: {v}" for k, v in case_details.items() if v is not None]
    return "\n".join(rows) if rows else "(no case details available)"


def _format_paragraph(template_paragraph: str | None) -> str:
    if not template_paragraph or not template_paragraph.strip():
        return (
            "(surrounding paragraph not available — match the marker's "
            "shape and write neutrally)"
        )
    return template_paragraph.strip()


def _format_marker(template_property_marker: str | None) -> str:
    if not template_property_marker or not template_property_marker.strip():
        return (
            "(no sample marker available — shape the output to read "
            "naturally inside the surrounding paragraph)"
        )
    return template_property_marker.strip()


def _render_output_expectation_block(output_expectation: str | None) -> str:
    if not output_expectation or not output_expectation.strip():
        return ""
    return _OUTPUT_EXPECTATION_BLOCK.format(output_expectation=output_expectation.strip())


def build_web_enhance_prompt(
    *,
    variable_name: str,
    current_value: str,
    web_enhance_instruction: str,
    template_property_marker: str | None,
    template_paragraph: str | None,
    case_details: dict[str, Any] | None,
    output_expectation: str | None = None,
) -> str:
    """Assemble the single-turn web-enhance prompt."""
    return _PROMPT_TEMPLATE.format(
        variable_name=variable_name,
        current_value=current_value,
        web_enhance_instruction=web_enhance_instruction.strip(),
        template_property_marker_block=_format_marker(template_property_marker),
        template_paragraph_block=_format_paragraph(template_paragraph),
        case_details_block=_format_case_details(case_details),
        output_expectation_block=_render_output_expectation_block(output_expectation),
    )
