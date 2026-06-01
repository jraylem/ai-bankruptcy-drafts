"""Public type exports for studio_v2.

Wizard params, template field/spec/config, bundling, resolution,
picks, pending envelopes, and orchestration result types all live one
layer down. This file re-exports the most-used names so call sites
can `from src.core.studio_v2.types import ...` without knowing the
submodule layout.
"""

from .bundling import (
    BranchCompanion,
    BranchOption,
    BundleCompanion,
    ExtractFromDraftSlotConfig,
    FixedCompanion,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
    SlotConfig,
    TemplateConfigV2,
    TemplateRole,
)
from .fields import (
    TemplateFieldV2,
    TemplateSpecV2,
)
from .orchestration import (
    AwaitingInputResponseV2,
    BundleChildRunV2,
    DryRunResponseV2,
    FinalizedRunV2,
    InitialStagesResultV2,
    ParentBundleContextV2,
)
from .pending import (
    AttorneyRow,
    PendingAttorneyPickV2,
    PendingAuthorDateV2,
    PendingAuthorDocsV2,
    PendingAuthorTextV2,
    PendingChipV2,
    PendingDropdownV2,
    PendingMultiSelectV2,
    PendingUserInputV2,
)
from .picks import (
    MultiSelectPickV2,
    SingleValuePickV2,
    SupportingDocsPickV2,
    UserSelectionV2,
)
from .resolution import (
    ResolvedTemplateValueV2,
)
from .wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)

__all__ = [
    "AttorneyRow",
    "AuthorInputKind",
    "AwaitingInputResponseV2",
    "BranchCompanion",
    "BranchOption",
    "BundleChildRunV2",
    "BundleCompanion",
    "DryRunResponseV2",
    "ExtractFromDraftSlotConfig",
    "FinalizedRunV2",
    "FixedCompanion",
    "InitialStagesResultV2",
    "LiteralSlotConfig",
    "MultiSelectPickV2",
    "ParentBundleContextV2",
    "ParentVariableSlotConfig",
    "PendingAttorneyPickV2",
    "PendingAuthorDateV2",
    "PendingAuthorDocsV2",
    "PendingAuthorTextV2",
    "PendingChipV2",
    "PendingDropdownV2",
    "PendingMultiSelectV2",
    "PendingUserInputV2",
    "PresentationShape",
    "ResolvedTemplateValueV2",
    "SingleValuePickV2",
    "SlotConfig",
    "SourceKind",
    "SupportingDocsPickV2",
    "TemplateConfigV2",
    "TemplateFieldV2",
    "TemplateRole",
    "TemplateSpecV2",
    "UserSelectionV2",
    "WizardSourceParams",
]
