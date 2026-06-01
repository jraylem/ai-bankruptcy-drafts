"""Prompt builder for DeriveAgent.

Author's `extraction_prompt` is the BINDING instruction (same
strict-binding contract as `regeneration_instruction` — decision #12
from Phase 1). `output_expectation` (optional) shapes the final
string. `parent_value` is either the parent's `raw_context` (when
available — the source slice the parent value came from) or its
display `value` (fallback for non-extractable sources like constants
or author input).

Replaces v1's `auto_derive` family of prompts:
- `extract_substring` (substring rule effect)
- `pluralize_by_count` (count → singular/plural verb)
- `dependent_on_variable` (free-form prompt-based derivation)
All three collapse to ONE prompt path here: the LLM applies the
author's `extraction_prompt` to `parent_value`, optionally shaped by
`output_expectation`, returns one string.
"""

from __future__ import annotations


_DERIVE_PROMPT_TEMPLATE = """\
You are deriving the value of a template variable named `{child_variable}`
from the value of another template variable named `{parent_variable}`.

The author has supplied a precise natural-language instruction for HOW
to derive `{child_variable}` from `{parent_variable}`'s value. Follow
the instruction exactly — it is BINDING and has the highest priority
of any guidance in this prompt. If the instruction conflicts with
output_expectation, follow the instruction.

<author_instruction>
{extraction_prompt}
</author_instruction>

{output_expectation_block}\
<parent_variable_value>
{parent_value}
</parent_variable_value>

Return EXACTLY one JSON object matching the structured-output schema:
```
{{ "value": "<the derived string — no surrounding quotes, no commentary>" }}
```

Critical rules:
- The author's instruction comes first. If they say "return 'are' when
  there are multiple items, otherwise 'is'", produce exactly that
  output — do NOT add caveats, explanations, or alternative phrasings.
- If the instruction asks you to extract a substring, return ONLY the
  substring — no prefixes, no quotes, no surrounding punctuation
  unless the instruction asks for them.
- If the parent value is empty or doesn't contain the information the
  instruction asks for, return an empty string. Do NOT invent content.
- Plain paralegal English in the author instruction is fine; translate
  freely ("the docket number" = the integer after "Dkt No." / "ECF No.";
  "the dollar amount" = the dollar figure with currency formatting).
"""


_OUTPUT_EXPECTATION_BLOCK = """\
The final inserted value should be shaped according to this
expectation (a hint for formatting; the author instruction above
still takes priority):

<output_expectation>
{output_expectation}
</output_expectation>

"""


def build_derive_prompt(
    child_variable: str,
    parent_variable: str,
    parent_value: str,
    extraction_prompt: str,
    output_expectation: str | None = None,
) -> str:
    """Compose the DeriveAgent prompt.

    Args:
        child_variable: The variable this derivation is producing
            (e.g. ``vin``, ``car_year``, ``is_or_are``).
        parent_variable: The variable whose value this derivation reads
            from (e.g. ``vehicle_record``, ``creditors_list``).
        parent_value: The parent's resolved value to extract from. The
            caller should prefer the parent's `raw_context` (source
            slice) over the display `value` when both exist.
        extraction_prompt: The author's free-form derivation
            instruction.
        output_expectation: Optional shape hint for the final string.

    Returns:
        The fully-formatted prompt string ready to pass to
        `DeriveAgent._invoke(...)`.
    """
    output_block = (
        _OUTPUT_EXPECTATION_BLOCK.format(
            output_expectation=output_expectation.strip()
        )
        if output_expectation and output_expectation.strip()
        else ""
    )
    return _DERIVE_PROMPT_TEMPLATE.format(
        child_variable=child_variable,
        parent_variable=parent_variable,
        parent_value=parent_value,
        extraction_prompt=extraction_prompt.strip(),
        output_expectation_block=output_block,
    )
