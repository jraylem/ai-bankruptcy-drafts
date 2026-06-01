"""Prompt template for the AutoDeriveAgent — extracts a derived substring from an already-resolved parent variable value at fill time."""

_DERIVE_PROMPT = """You are extracting a substring or derived value from a parent template variable's resolved value.

PARENT VARIABLE: {parent_variable}
PARENT VALUE: {parent_value}

The derived value should appear in the following surrounding context (extracted at template-generation time from the source document):

    {derived_context}

At template-generation, the derived value at this position looked like this in the source:

    {derived_marker}

YOUR TASK: Extract from PARENT VALUE the portion that should fill the derived position.

GUIDANCE:
- Match the format and granularity of `derived_marker`. If it's just a number (e.g. "3"), return only the number, not the surrounding clause.
- Use the same casing, punctuation, and presentation as `derived_marker` when possible.
- Do NOT include any text from `derived_context` that's outside the variable's own value.
- If PARENT VALUE cannot reasonably be derived to fit the derived position, return an empty string.
- Do NOT add commentary, quotes, or prefixes — return ONLY the derived value.
"""
