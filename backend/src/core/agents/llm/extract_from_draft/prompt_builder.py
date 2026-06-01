"""Prompt builder for ExtractFromDraftAgent.

The prompt frames the parent's filled draft as the source-of-truth and
asks the LLM to extract ONE specific fragment per the author's
extract_instruction. The slot's template_property_marker (when set) is
surfaced as a SHAPE reference only — same rule as the DraftAgent prompt:
the marker contributes formatting/length expectations, never content.
"""


_EXTRACT_PROMPT = """You are extracting a single fragment from a legal document so it can fill a placeholder in a companion document (e.g. a Certificate of Service that ships with this motion).

The DRAFT TEXT below is the FILED VERSION of the parent document. Treat it as the authoritative source — names, titles, dates, and case identifiers in the draft are the real values for this case. Do not invent or paraphrase.

<draft_text>
{draft_text}
</draft_text>

<extract_instruction>
{extract_instruction}
</extract_instruction>

{shape_block}

Return ONLY the extracted value as a string. No quotes, no labels, no leading/trailing punctuation unless it's part of the value itself. If the draft text genuinely lacks the value, return an empty string."""


_SHAPE_BLOCK = """<shape_reference>
The companion document expects the value in approximately this shape:
{marker}

Treat this ONLY as a shape/length cue (casing, punctuation style, level of detail). NEVER copy this content verbatim — the actual value MUST come from the draft text above.
</shape_reference>"""


def build_prompt(
    draft_text: str,
    extract_instruction: str,
    template_property_marker: str | None,
) -> str:
    """Assemble the extract-from-draft prompt.

    `template_property_marker` is rendered as a shape reference block when
    set, omitted otherwise. The block carries the same anti-borrow rule as
    the DraftAgent's marker handling.
    """
    shape_block = (
        _SHAPE_BLOCK.format(marker=template_property_marker)
        if template_property_marker
        else ""
    )
    return _EXTRACT_PROMPT.format(
        draft_text=draft_text,
        extract_instruction=extract_instruction,
        shape_block=shape_block,
    )
