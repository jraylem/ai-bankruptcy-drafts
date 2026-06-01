"""Prompt builders for the v2 extractor agents.

All four agents share most of the system-prompt scaffolding (the tool
guide, the strict-binding clause for the author's extraction_prompt,
the dependency-values block, the paralegal-speak translation
guideline) and differ in the per-shape USER prompt that describes
what kind of output the submit_* tool expects.
"""

from __future__ import annotations

from ...types.wizard_sources import SourceKind, WizardSourceParams


_SYSTEM_PROMPT_TEMPLATE = """\
You are an extraction agent for the Studio V2 templating system.

You will be given:
- A `template_variable` name + its `extraction_prompt` (the author's
  binding instruction for what to extract).
- A `source` kind — `gmail` (the firm's shared mailbox) or
  `case_file` (the case's filed petition + uploaded documents).
- Optional `dependency_values` — already-resolved values for other
  template variables this extraction should use as CONTEXT for
  crafting tool queries (e.g. a `case_number` to scope a Gmail search).
- A toolset to navigate the source material:

  * `gmail_search` — run a Gmail-query-syntax search. Each result
    includes `subject`, `sender`, `snippet`, AND the full plain-text
    `body`. Default to UNQUOTED phrase searches with no operator
    (e.g. `"proof of claim"`) so Gmail matches across subject,
    body, sender, and attachments — most useful answers live in the
    body. Use `from:` to filter by sender or `after:YYYY/MM/DD` to
    narrow by date. Avoid `subject:` unless you specifically want
    to ignore the body. The active case's number is automatically
    appended to every query — don't include it yourself.
  * `case_vector_query` — semantic similarity search over the case
    file (petition + schedules + uploaded documents). Returns
    ranked chunks. Use natural-language queries; be specific.
  * `vision_fallback` — Claude-vision call over the petition PDF.
    Use ONLY when text extraction returned weak / empty / OCR-garbled
    results AND the answer requires visual layout reasoning
    (checkboxes, signatures, tabular cells, form-field content).
    Slow + expensive — do not use as the first lookup.

When you have the answer, call `{submit_tool_name}` exactly ONCE
with the structured arguments. The conversation ends after that call.

**STRICT ADHERENCE TO THE AUTHOR'S EXTRACTION PROMPT.** The
extraction_prompt is BINDING and has the highest priority of any
guidance in this conversation. If it conflicts with default
behavior, follow the instruction. Translate paralegal English freely
("the case number thing", "that boilerplate footer") — match by
meaning, not by exact token. If the source material doesn't contain
the answer, call `{submit_tool_name}` with an empty value and
`confidence="none"` — do NOT invent content.
"""


_USER_PROMPT_TEMPLATE = """\
<template_variable>{template_variable}</template_variable>
<source>{source}</source>
<presentation_shape>{presentation_shape}</presentation_shape>
{case_context_block}
<author_instruction>
{extraction_prompt}
</author_instruction>
{dependency_block}{output_expectation_block}{example_block}{marker_block}{shape_block}\

Begin your investigation. Use the tools above to find the answer,
then call `{submit_tool_name}` to finalize.
"""


_CASE_CONTEXT_BLOCK_TEMPLATE = """
<case_context>
{rendered_values}
</case_context>
**The values above are the AUTHORITATIVE truth for this case** —
already loaded from the case row, NOT something to look up.

**SHORT-CIRCUIT: if the `template_variable` is one of these four,
call `{submit_tool_name}` IMMEDIATELY with the corresponding value
from `<case_context>` and `confidence="high"`. Do NOT call any
tools — the answer is already in front of you, and tool calls here
risk pulling a stale value from a different document AND waste
your tool-call budget.**

  - `template_variable == "case_number"` → use `case_context.case_number`
  - `template_variable == "chapter"`     → use `case_context.chapter`
  - `template_variable == "debtor_name"` → use `case_context.case_name`
    (the "In re:" caption IS the debtor's name in bankruptcy filings)
  - `template_variable == "court_district"` → use `case_context.court_district`

**For ALL OTHER variables, use the context only as scope / query
hints**: every `gmail_search` MUST include `case_number` (the
wrapper auto-appends it; you don't need to type it). Every
`case_vector_query` is already auto-scoped to this case's documents,
but mentioning `case_number` / `case_name` in the query string
still improves relevance. Never return values that came from a
different case.
"""


_DEPENDENCY_BLOCK_TEMPLATE = """
<dependency_values>
{rendered_values}
</dependency_values>
The values above are already resolved for this case — use them as
ADDITIONAL CONTEXT when constructing tool queries (e.g. narrow a
`case_vector_query` by `meeting_date`).
"""


_OUTPUT_EXPECTATION_BLOCK_TEMPLATE = """
<output_expectation>
{output_expectation}
</output_expectation>
"""


_EXAMPLE_FORMAT_BLOCK_TEMPLATE = """
<example_format>
{example_format}
</example_format>
Shape each extracted value to LOOK like the example above — this is
a concrete sample, NOT a template substitution. Do not return the
example itself.
"""


_TEMPLATE_MARKER_BLOCK_TEMPLATE = """
<original_value_at_this_position>
{marker}
</original_value_at_this_position>
The text above is the LITERAL value that occupied this placeholder's
position in the source `.docx` (from the sample case the document
was authored against). Use it as **shape / format / casing /
delimiter / line-break guidance ONLY**:

- If it shows `Name, email` per line → format your extraction the
  same way (one entry per line, comma-separated).
- If it shows `Name\\nemail` (name and email on separate lines, blank
  line between entries) → match that vertical layout.
- If it shows a numbered list, an Oxford-comma sentence, an
  all-caps heading, or any other distinctive shape → mirror it.

**Do NOT copy specific names, dates, amounts, emails, addresses, or
identifying details from this sample** — those belong to a different
case and would be hallucinated facts. The fact content comes from
your tool calls; this block tells you only how to *present* it.

When both `<example_format>` and this block are present,
`<example_format>` wins (it's the author's deliberate override).
"""




_SHAPE_BLOCKS = {
    "raw": "",
    "dropdown": """
<dropdown_extraction>
Extract up to 20 candidate values. Each candidate must come from a
DISTINCT source chunk; do not duplicate. For every candidate, capture
the source slice it was extracted from (capped ≤ 2000 chars) as
`raw_context` — derived children of this dropdown read raw_context,
not the display label, so it must be a real chunk of source material.
</dropdown_extraction>
""",
    "chip": """
<chip_extraction>
Generate 1-3 SUGGESTION chips the paralegal will pick from or edit.
Each chip should be a plausible final value (not a candidate list);
favor brevity over completeness. For each chip, capture the source
slice that supports it as `raw_context`. The paralegal may edit the
chip text before submitting — so produce confident, defensible
suggestions.
</chip_extraction>
""",
    "multi_select": """
<multi_select_extraction>
Extract up to 20 candidates the paralegal will pick K-of-N from.
Same per-candidate `raw_context` rule as dropdown. Order candidates
in document order (top-to-bottom for case_file, newest-first for
gmail) so the paralegal can scan the list quickly.
</multi_select_extraction>
""",
}


def build_system_prompt(*, submit_tool_name: str) -> str:
    """Assemble the system prompt with the submit-tool name interpolated."""
    return _SYSTEM_PROMPT_TEMPLATE.format(submit_tool_name=submit_tool_name)


def build_user_prompt(
    *,
    template_variable: str,
    params: WizardSourceParams,
    submit_tool_name: str,
    case_context: dict[str, str] | None = None,
    dependency_values: dict[str, str] | None = None,
    template_property_marker: str | None = None,
) -> str:
    """Assemble the initial user prompt for an extractor agent.

    Renders the source / shape / mandatory case-context block / author
    instruction / optional dependency-values block / optional
    example_format / optional output_expectation / per-shape
    extraction guidance into one HumanMessage body.

    `case_context` carries the active case's identity (case_number,
    case_name, chapter) — auto-supplied by the orchestrator from the
    `Case` row. When non-empty, the agent is INSTRUCTED to scope
    every tool query by these values (load-bearing — prevents Gmail
    search from pulling documents from other cases in the inbox).
    """
    return _USER_PROMPT_TEMPLATE.format(
        template_variable=template_variable,
        source=_source_label(params.source),
        presentation_shape=params.presentation_shape.value,
        extraction_prompt=(params.extraction_prompt or "").strip(),
        marker_block=_format_marker_block(template_property_marker),
        case_context_block=_format_case_context_block(
            case_context, submit_tool_name,
        ),
        dependency_block=_format_dependency_block(dependency_values),
        output_expectation_block=_format_output_expectation_block(
            params.output_expectation,
        ),
        example_block=_format_example_block(params.example_format),
        shape_block=_SHAPE_BLOCKS.get(params.presentation_shape.value, ""),
        submit_tool_name=submit_tool_name,
    )


def _format_case_context_block(
    values: dict[str, str] | None,
    submit_tool_name: str,
) -> str:
    if not values:
        return ""
    rendered = "\n".join(
        f'  {name} = "{val}"' for name, val in values.items() if val
    )
    if not rendered:
        return ""
    return _CASE_CONTEXT_BLOCK_TEMPLATE.format(
        rendered_values=rendered,
        submit_tool_name=submit_tool_name,
    )


def _source_label(source: SourceKind) -> str:
    """Human-readable label for the source kind — matches the wizard's
    Phase 0 layman vocabulary (Behavior Contract #13)."""
    return {
        SourceKind.GMAIL: "Email Inbox (gmail)",
        SourceKind.CASE_FILE: "Case Documents (case_file)",
    }.get(source, source.value)


def _format_dependency_block(values: dict[str, str] | None) -> str:
    if not values:
        return ""
    rendered = "\n".join(
        f'  {name} = "{val}"' for name, val in values.items()
    )
    return _DEPENDENCY_BLOCK_TEMPLATE.format(rendered_values=rendered)


def _format_output_expectation_block(expectation: str | None) -> str:
    if not expectation or not expectation.strip():
        return ""
    return _OUTPUT_EXPECTATION_BLOCK_TEMPLATE.format(
        output_expectation=expectation.strip(),
    )


def _format_example_block(example: str | None) -> str:
    if not example or not example.strip():
        return ""
    return _EXAMPLE_FORMAT_BLOCK_TEMPLATE.format(example_format=example.strip())


def _format_marker_block(marker: str | None) -> str:
    if not marker or not marker.strip():
        return ""
    return _TEMPLATE_MARKER_BLOCK_TEMPLATE.format(marker=marker.strip())
