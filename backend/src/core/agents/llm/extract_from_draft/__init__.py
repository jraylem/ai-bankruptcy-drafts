"""ExtractFromDraftAgent — pulls a slot value from a parent's produced draft text.

Used by Phase 2's InheritFromParentResolver when a child's slot has a
SlotConfig of kind `extract_from_draft`. The companion's
`extract_instruction` describes which fragment of the parent's filled
docx should fill the slot (typically the FILED docket title, which
differs from the parent template's authoring name).
"""

from .agent import ExtractFromDraftAgent

__all__ = ["ExtractFromDraftAgent"]
