"""Public surface of the GroupDropdownAgent — re-exports the agent class, the DropdownOption row type, and the structured-output schema."""

from .agent import DropdownOption, GroupDropdownAgent, _ExtractedPairs

__all__ = ["DropdownOption", "GroupDropdownAgent", "_ExtractedPairs"]
