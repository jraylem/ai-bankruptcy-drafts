"""Prompt template and helpers for the ExplanationEnhanceAgent.

Builds the multimodal text preamble (prompt + user_text + inlined DOCX/TXT/MD
sections); PDF and image content blocks are appended by the agent itself after
this text is rendered.
"""

from src.core.common.documents.supporting_doc_reader import InlineTextDoc

_ENHANCE_PROMPT = """You are a legal-document drafting assistant.

A user is filling a template placeholder labeled "{label}". They have provided:

  1. A free-form explanation in their own words (USER_TEXT below).
  2. Zero or more supporting documents corroborating facts in that explanation.
     Text-based supporting docs (DOCX/TXT/MD) are inlined below under
     <supporting_text_docs>. PDFs and images are attached separately as
     document/image content blocks on this message.

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

    Returns an empty string when there are no inline-text docs so the prompt
    doesn't grow a dangling `<supporting_text_docs>` section.
    """
    if not inline_docs:
        return ""

    sections = []
    for doc in inline_docs:
        sections.append(
            f'<doc filename="{doc.filename}">\n{doc.text}\n</doc>'
        )
    body = "\n\n".join(sections)
    return f"\n<supporting_text_docs>\n{body}\n</supporting_text_docs>\n"


def build_enhance_prompt(label: str, user_text: str, inline_docs: list[InlineTextDoc]) -> str:
    """Render the text preamble for a ExplanationEnhanceAgent call (prompt + user_text + inlined DOCX/TXT/MD sections)."""
    return _ENHANCE_PROMPT.format(
        label=label,
        user_text=user_text,
        inline_docs_block=_inline_text_docs_block(inline_docs),
    )
