"""Prompt template and heal-target helpers for the UserInputHealAgent.

Owns the base heal prompt plus the two conditional heal-target blocks:
GUIDE (example_sentence target for reco-chips) and PREFERRED PRESENTATION
(preferred_format target for dropdowns).
"""

from typing import Literal

HealTargetKind = Literal["example_sentence", "preferred_format"]


_HEAL_PROMPT = """You are a legal-document grammar and tone editor. A user has selected and edited text that needs to fill a placeholder in the following template paragraph:

<template_paragraph>
{template_paragraph}
</template_paragraph>

The placeholder you are filling is: {placeholder}
The user's current text for this placeholder: {user_value}
{heal_target_block}{author_instruction_block}
YOUR TASK: Return the text that should replace {placeholder} in the template paragraph above. The text must:

1. PRESERVE EVERY FACT from the user's current text (names, dates, amounts, employer identities, tenures, specific events). Do NOT add, remove, or alter facts.
2. FIT GRAMMATICALLY with the words on either side of {placeholder} in the template paragraph — drop redundant subjects, articles, or conjunctions that the surrounding template already supplies; adjust tense and number to agree with the surrounding sentence.
3. USE FORMAL THIRD-PERSON LEGAL TONE. If the user's text is casual or colloquial, rewrite it in the register of a legal motion — without changing meaning or adding new claims.
4. AUTHOR INSTRUCTION (when present below) is AUTHORITATIVE. It is a per-field rule the author wrote for the final output, and it overrides any conflicting shape guidance shown above OR conflicting wording in the user's text.

Return ONLY the fragment that fills {placeholder}. No surrounding template text, no quotes, no prefatory commentary."""


_AUTHOR_INSTRUCTION_BLOCK = """
AUTHOR INSTRUCTION — per-field rules for the final output (authoritative, see rule 4):
    {author_instruction}
"""


_EXAMPLE_SENTENCE_BLOCK = """
GUIDE — the author's name-free target sentence for this placeholder:
    {heal_target}
Match this tone, structure, and legal framing. Do NOT copy specific names, dates, amounts, or identifying details from this example — those come from the user's value.
"""


_PREFERRED_FORMAT_BLOCK = """
PREFERRED PRESENTATION — the template's original value at this variable position shows how the filled value SHOULD LOOK (casing, phrasing, formatting):
    {heal_target}

This block is a SAMPLE FROM A DIFFERENT CASE. Strict rules:
- Use ONLY facts present in the user's current text. Do NOT borrow specific values (VINs, addresses, dates, dollar amounts, names, account numbers) from the PREFERRED PRESENTATION — those belong to a different sample case and would be hallucinated facts in this output.
- The PREFERRED PRESENTATION's role is shape/format guidance only: punctuation, casing, connector words, suffix labels (e.g. trailing role tags like '("Vehicle")' or '(""Property"")').
- If the user's text is missing a field that the PREFERRED PRESENTATION has (e.g. user's pick has no VIN but the sample shows 'VIN# X'), LEAVE IT MISSING in the output. Do not fabricate or copy.
- It is OK — and often expected — to add the same suffix label / role tag style the sample uses, because that is shape, not fact.
"""


def _render_heal_target_block(heal_target: str | None, kind: HealTargetKind | None) -> str:
    if not heal_target or not heal_target.strip() or kind is None:
        return ""
    template = (
        _EXAMPLE_SENTENCE_BLOCK if kind == "example_sentence" else _PREFERRED_FORMAT_BLOCK
    )
    return template.format(heal_target=heal_target.strip())


def _render_author_instruction_block(author_instruction: str | None) -> str:
    if not author_instruction or not author_instruction.strip():
        return ""
    return _AUTHOR_INSTRUCTION_BLOCK.format(author_instruction=author_instruction.strip())


def _build_heal_prompt(
    template_paragraph: str,
    placeholder: str,
    user_value: str,
    heal_target: str | None,
    heal_target_kind: HealTargetKind | None,
    author_instruction: str | None = None,
) -> str:
    heal_target_block = _render_heal_target_block(heal_target, heal_target_kind)
    author_instruction_block = _render_author_instruction_block(author_instruction)
    return _HEAL_PROMPT.format(
        template_paragraph=template_paragraph,
        placeholder=placeholder,
        user_value=user_value,
        heal_target_block=heal_target_block,
        author_instruction_block=author_instruction_block,
    )
