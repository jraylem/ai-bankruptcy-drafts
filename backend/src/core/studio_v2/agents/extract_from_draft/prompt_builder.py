"""Prompt builder for ExtractFromDraftAgentV2.

Frames the parent's filled draft as the source-of-truth and asks
the LLM to extract ONE specific fragment per the author's
`extract_instruction`. The optional `template_property_marker` is
surfaced as a SHAPE reference only — same anti-borrow rule as v1's
DraftAgent: the marker contributes formatting/length expectations,
NEVER the content.

Prose mirrors v1's `extract_from_draft/prompt_builder.py` 1:1 —
brand-new file in the v2 namespace, no v1 import.
"""

from __future__ import annotations


_EXTRACT_PROMPT_V2 = """\
You are extracting a single fragment from a legal document so it can
fill a placeholder in a companion document (e.g. a Certificate of
Service that ships with this motion).

The DRAFT TEXT below is the FILED VERSION of the parent document.
Treat it as the authoritative source — names, titles, dates, and case
identifiers in the draft are the real values for this case. Do NOT
invent or paraphrase.

<draft_text>
{draft_text}
</draft_text>

<extract_instruction>
{extract_instruction}
</extract_instruction>
{shape_block}
Return ONLY the extracted value as a string. No quotes, no labels, no
leading/trailing punctuation unless it's part of the value itself. If
the draft text genuinely lacks the value, return an empty string."""


_SHAPE_BLOCK_V2 = """

<shape_reference>
The companion document expects the value in approximately this shape:
{marker}

Treat this ONLY as a shape/length cue (casing, punctuation style,
level of detail). NEVER copy this content verbatim — the actual value
MUST come from the draft text above.
</shape_reference>"""


def build_extract_from_draft_prompt(
    *,
    draft_text: str,
    extract_instruction: str,
    template_property_marker: str | None = None,
) -> str:
    """Assemble the extract-from-draft prompt.

    `template_property_marker` is rendered as a shape reference block
    when supplied, omitted otherwise.
    """
    shape_block = (
        _SHAPE_BLOCK_V2.format(marker=template_property_marker)
        if template_property_marker
        else ""
    )
    return _EXTRACT_PROMPT_V2.format(
        draft_text=draft_text,
        extract_instruction=extract_instruction,
        shape_block=shape_block,
    )
