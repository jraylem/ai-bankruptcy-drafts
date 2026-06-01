"""Prompt builder for UserInputHealAgentV2.

Mirrors v1's UserInputHealAgent prompt structure verbatim — the same
"GUIDE" and "PREFERRED PRESENTATION" blocks (matching v1's
heal_target_kind discriminator) plus the strict-binding clause for
the optional author instruction.

Brand-new file (no v1 import); the prose has been hardened through
months of paralegal usage so the structural rules port unchanged.
"""

from __future__ import annotations

from typing import Literal


HealTargetKindV2 = Literal["example_sentence", "preferred_format"]


_HEAL_PROMPT_V2 = """\
You are a legal-document grammar and tone editor. A user has selected and \
edited text that needs to fill a placeholder in the following template \
paragraph:

<template_paragraph>
{template_paragraph}
</template_paragraph>

The placeholder you are filling is: {placeholder}
The user's current text for this placeholder: {user_value}
{heal_target_block}{author_instruction_block}
YOUR TASK: Return the text that should replace {placeholder} in the template \
paragraph above. The text must:

1. PRESERVE EVERY FACT from the user's current text (names, dates, amounts, \
employer identities, tenures, specific events). Do NOT add, remove, or alter \
facts.
2. FIT GRAMMATICALLY with the words on either side of {placeholder} in the \
template paragraph — drop redundant subjects, articles, or conjunctions that \
the surrounding template already supplies; adjust tense and number to agree \
with the surrounding sentence.
3. USE FORMAL THIRD-PERSON LEGAL TONE. If the user's text is casual or \
colloquial, rewrite it in the register of a legal motion — without changing \
meaning or adding new claims.
4. AUTHOR INSTRUCTION (when present below) is AUTHORITATIVE. It is a \
per-field rule the author wrote for the final output, and it overrides any \
conflicting shape guidance shown above OR conflicting wording in the user's \
text.
5. DO NOT touch date strings that look already-normalized (e.g. \
"April 30, 2026"). The pipeline's date-healing pass runs before this one \
and locks the date format to the firm default.
6. LIST READABILITY. When the value is a list of multi-line entries — \
e.g. each entry has a name on one line and an email / phone / address on \
the next, or any pattern where ONE logical entry occupies TWO OR MORE \
lines — separate distinct entries with a single blank line so the reader \
can visually group them. Example:
    Gavin N Stewart
    bk@stewartlegalgroup.com

    Giselle Velez
    gvelez@rasflaw.com

    Daniel A Weber
    dweber@ssclawfirm.com
DO NOT add blank lines when each entry is single-line (e.g. a simple \
comma-separated address list, a numbered list, or "Name, email" per \
line) — blank lines there would oversize the block. If a shape block \
or author instruction above explicitly shows a different separator \
(e.g. always-flat, or a horizontal rule between entries), follow \
that instead.

Return ONLY the fragment that fills {placeholder}. No surrounding template \
text, no quotes, no prefatory commentary.
"""


_AUTHOR_INSTRUCTION_BLOCK_V2 = """\

AUTHOR INSTRUCTION — per-field rule for the final output (authoritative, \
see rule 4):
    {author_instruction}
"""


_EXAMPLE_SENTENCE_BLOCK_V2 = """\

GUIDE — the author's name-free target sentence for this placeholder:
    {heal_target}
Match this tone, structure, and legal framing. Do NOT copy specific names, \
dates, amounts, or identifying details from this example — those come from \
the user's value.
"""


_PREFERRED_FORMAT_BLOCK_V2 = """\

PREFERRED PRESENTATION — the template's original value at this variable \
position shows how the filled value SHOULD LOOK (casing, phrasing, \
formatting):
    {heal_target}

This block is a SAMPLE FROM A DIFFERENT CASE. Strict rules:
- Use ONLY facts present in the user's current text. Do NOT borrow specific \
values (VINs, addresses, dates, dollar amounts, names, account numbers) from \
the PREFERRED PRESENTATION — those belong to a different sample case and \
would be hallucinated facts in this output.
- The PREFERRED PRESENTATION's role is shape/format guidance only: \
punctuation, casing, connector words, suffix labels (e.g. trailing role \
tags like '("Vehicle")' or '("Property")').
- If the user's text is missing a field that the PREFERRED PRESENTATION has \
(e.g. user's pick has no VIN but the sample shows 'VIN# X'), LEAVE IT \
MISSING in the output. Do not fabricate or copy.
- It is OK — and often expected — to add the same suffix label / role tag \
style the sample uses, because that is shape, not fact.
"""


def _render_heal_target_block(
    heal_target: str | None,
    kind: HealTargetKindV2 | None,
) -> str:
    if not heal_target or not heal_target.strip() or kind is None:
        return ""
    template = (
        _EXAMPLE_SENTENCE_BLOCK_V2
        if kind == "example_sentence"
        else _PREFERRED_FORMAT_BLOCK_V2
    )
    return template.format(heal_target=heal_target.strip())


def _render_author_instruction_block(author_instruction: str | None) -> str:
    if not author_instruction or not author_instruction.strip():
        return ""
    return _AUTHOR_INSTRUCTION_BLOCK_V2.format(
        author_instruction=author_instruction.strip(),
    )


def build_user_input_heal_prompt(
    *,
    template_paragraph: str,
    placeholder: str,
    user_value: str,
    heal_target: str | None,
    heal_target_kind: HealTargetKindV2 | None,
    author_instruction: str | None = None,
) -> str:
    """Assemble the heal prompt for a single user-input field.

    Args:
        template_paragraph: The .docx paragraph containing the
            `[[placeholder]]` — name-free, date-free by construction.
        placeholder: The `[[var]]` string this fill replaces.
        user_value: The user's final (possibly edited) text.
        heal_target: Optional per-shape heal-target string
            (example_format for dropdown/multi-select;
            output_expectation for chip / author_input).
        heal_target_kind: Discriminates between "example_sentence"
            (chip / plain text) and "preferred_format" (dropdown /
            multi-select) presentation.
        author_instruction: The field's `params.output_expectation`
            surfaced as an authoritative per-field rule. Overrides
            shape conflicts.
    """
    return _HEAL_PROMPT_V2.format(
        template_paragraph=template_paragraph,
        placeholder=placeholder,
        user_value=user_value,
        heal_target_block=_render_heal_target_block(heal_target, heal_target_kind),
        author_instruction_block=_render_author_instruction_block(author_instruction),
    )
