"""Studio V2 repositories — Phase 1 ships templates_v2 + template_fields_v2.

drafts_v2 lands in Phase 3 (drafting). resolutions_v2 lands in Phase 2
(dry-run). Each repo follows the v1 BaseRepository pattern and uses
the shared AsyncSessionLocal from src.chatbot.database.

Importing the package eagerly imports `models` so the ORM classes
register against the shared Base.metadata used by migrations.
"""

from . import models  # noqa: F401 — ensure ORM models are registered on import
from .template_fields_v2 import ReExtractDiff, TemplateFieldsV2Repository
from .templates_v2 import TemplatesV2Repository

__all__ = [
    "models",
    "ReExtractDiff",
    "TemplateFieldsV2Repository",
    "TemplatesV2Repository",
]
