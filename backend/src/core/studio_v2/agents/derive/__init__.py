"""DeriveAgent — prompt-based derivation for v2.

Replaces v1's `AutoDeriveAgent` family (extract_substring,
pluralize_by_count, dependent_on_variable). v1 used a `rule_effect`
enum to discriminate the derivation kind; v2 collapses everything
into a single LLM call where the author's free-form
`extraction_prompt` IS the instruction.

Reads `raw_context` first (when the parent is a dropdown / chip /
multi-select pick) and falls back to the parent's display `value`
when no source slice is available (constants, author input, current
date, etc.). This is the load-bearing path that makes Rules 16/18
virtual-parent-with-derived-children work end-to-end.
"""

from .agent import DeriveAgent

__all__ = ["DeriveAgent"]
