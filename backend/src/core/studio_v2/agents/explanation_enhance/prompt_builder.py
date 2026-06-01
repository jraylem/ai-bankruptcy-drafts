"""Prompt builder for ExplanationEnhanceAgentV2.

Renders the text preamble (user_text + inlined DOCX/TXT/MD sections).
PDFs and images are appended by the agent as separate content blocks
on the multimodal HumanMessage.

Mirrors v1's `explanation_enhance/prompt_builder.py` verbatim in
structural rules — those rules have been hardened by months of
production paralegal usage. Brand-new file in the v2 namespace (no
v1 import).
"""

from __future__ import annotations

from src.core.common.documents.supporting_doc_reader import InlineTextDoc


_ENHANCE_PROMPT_V2 = """\
You are a legal-document drafting assistant.

A user is filling a template placeholder labeled "{label}". They have provided:

  1. A free-form explanation in their own words (USER_TEXT below).
  2. Zero or more supporting documents corroborating facts in that explanation.
     Text-based supporting docs (DOCX/TXT/MD) are inlined below under
     <supporting_text_docs>. PDFs and images are attached separately as
     document/image content blocks on this message.
{shape_guidance_block}
<user_text>
{user_text}
</user_text>
{inline_docs_block}
YOUR TASK: Produce ONE compact, legally-worded paragraph that fills the
placeholder. The paragraph must:

1. PRESERVE EVERY FACT the user asserts in USER_TEXT. Do not drop names,
   dates, amounts, employer identities, tenures, specific events. The
   user's text is ground truth for what happened.
2. USE THE SUPPORTING DOCUMENTS to corroborate, sharpen, or correct the
   user's factual claims. If a doc shows a date the user gave approximately
   (e.g. user wrote "last March" and a pay stub shows "March 8, 2026"),
   prefer the precise value from the doc. If a doc reveals a material fact
   relevant to the explanation (e.g. the user said "I was laid off" and a
   termination letter specifies "position eliminated due to restructuring"),
   fold it in concisely.
3. DO NOT FABRICATE facts absent from BOTH the user's text AND the
   supporting docs. If the user omits a detail and no doc supplies it,
   leave it out — do NOT invent employer names, dates, or amounts.
4. USE FORMAL THIRD-PERSON LEGAL TONE suitable for a bankruptcy filing:
   - **Third person only.** Refer to the filer as "the Debtor" (or the
     named debtor when they are explicitly identified elsewhere). Never
     use "I", "me", "my", "we", "our", "you" — rewrite every first- or
     second-person phrasing into third person.
   - **Factual and direct.** State what happened, when, to whom, and for
     how much. Short declarative sentences. No hedging ("it seems that",
     "unfortunately"), no intensifiers ("truly", "desperately", "deeply"),
     no rhetorical flourishes.
   - **No emotional appeals.** Strip hardship language, sympathy cues,
     and subjective framing ("has been struggling", "is facing severe
     hardship", "has suffered", "through no fault of their own",
     "respectfully requests understanding"). The filing already implies
     distress; the paragraph's job is to document causation and numbers,
     not to persuade emotionally.
   - **No editorializing or conclusions of law.** Do not characterize
     facts as "unfair", "unforeseen", "beyond control", "unjust", or
     similar. Present the facts; the reader draws conclusions.
   - If the user's text contains emotional language, casual register,
     or first-person prose, rewrite — do NOT preserve that register.
     Only the FACTS from the user text are ground truth; the TONE is
     not.
5. PRODUCE ONE PARAGRAPH. No bullet points, no headers, no prefatory
   commentary. The return value fills the placeholder verbatim.

Return ONLY the final paragraph."""


def _inline_text_docs_block(inline_docs: list[InlineTextDoc]) -> str:
    """Render inline-text supporting docs as a labeled block for the prompt.

    Returns empty string when there are no inline-text docs so the prompt
    doesn't carry a dangling `<supporting_text_docs>` section.
    """
    if not inline_docs:
        return ""
    sections = [
        f'<doc filename="{doc.filename}">\n{doc.text}\n</doc>'
        for doc in inline_docs
    ]
    body = "\n\n".join(sections)
    return f"\n<supporting_text_docs>\n{body}\n</supporting_text_docs>\n"


def _shape_guidance_block(
    template_property_marker: str | None,
    output_expectation: str | None,
) -> str:
    """Render the shape-guidance section combining the .docx's
    original sample sentence (marker) and the author's tuning
    instruction (output_expectation).

    Both are optional. When neither is present, return empty string so
    the prompt doesn't carry a dangling block. The marker is rendered
    as an example to mimic in shape/tone/length (NOT as facts to
    preserve — the facts come from user_text and supporting docs).
    The output_expectation is rendered as a directive.
    """
    marker = (template_property_marker or "").strip()
    expectation = (output_expectation or "").strip()
    if not marker and not expectation:
        return ""

    parts: list[str] = ["", "SHAPE GUIDANCE for the final paragraph:"]
    if marker:
        parts.append(
            "- A real sample from this position in the document — mimic "
            "its tone, grammar, length, and register (NOT its facts):"
        )
        parts.append(f'  <sample>{marker}</sample>')
    if expectation:
        parts.append(f"- Author's tuning instruction: {expectation}")
    parts.append("")
    return "\n".join(parts)


def build_explanation_enhance_prompt(
    *,
    label: str,
    user_text: str,
    inline_docs: list[InlineTextDoc],
    template_property_marker: str | None = None,
    output_expectation: str | None = None,
) -> str:
    """Assemble the text preamble for an ExplanationEnhanceAgentV2 call."""
    return _ENHANCE_PROMPT_V2.format(
        label=label,
        user_text=user_text,
        inline_docs_block=_inline_text_docs_block(inline_docs),
        shape_guidance_block=_shape_guidance_block(
            template_property_marker, output_expectation,
        ),
    )
