"""UserInputHealAgentV2 — LLM prose shaper for user-input fields.

Runs in the v2 finalizer pipeline AFTER `DateHealingResolverV2` and
BEFORE `DocxTemplateService.fill_template`. For each user-input field
(dropdown / chip / multi_select pick, author_input plain_text /
date / with_docs, INHERIT_FROM_PARENT real fill), the agent reshapes
the picked value into formal third-person legal prose that fits the
surrounding template paragraph grammatically.

Mirrors v1's `UserInputHealAgent` 1:1 in behavior; brand-new class in
the v2 namespace (no v1 import). v1's source-discrimination via
`FieldSource` enum is replaced by v2's
`(WizardSourceParams.source, presentation_shape)` discriminator.
"""

from .agent import UserInputHealAgentV2

__all__ = ["UserInputHealAgentV2"]
