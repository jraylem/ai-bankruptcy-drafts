"""Public surface of the core database layer — re-exports the ORM models and their repository classes."""

from .models import (
    Case,
    CaseGenerationLog,
    CaseInbox,
    CaseIngestionLog,
    CaseSession,
    CaseSessionMessage,
    DraftTemplate,
    LlmCostLog,
    ReferenceData,
)
from .repositories.attorney_roster_repository import (
    ATTORNEYS_SHORT_CODE,
    Attorney,
    AttorneyRosterRepository,
)
from .repositories.case_generation_log_repository import CaseGenerationLogRepository
from .repositories.case_inbox_repository import CaseInboxRepository
from .repositories.case_ingestion_log_repository import (
    ALL_OUTCOMES,
    CaseIngestionLogRepository,
)
from .repositories.case_repository import CaseRepository
from .repositories.case_session_message_repository import (
    CaseSessionMessageRepository,
)
from .repositories.case_session_repository import CaseSessionRepository
from .repositories.draft_template_repository import DraftTemplateRepository
from .repositories.llm_cost_log_repository import LlmCostLogRepository
from .repositories.reference_data_repository import ReferenceDataRepository

__all__ = [
    "ALL_OUTCOMES",
    "ATTORNEYS_SHORT_CODE",
    "Attorney",
    "AttorneyRosterRepository",
    "Case",
    "CaseGenerationLog",
    "CaseGenerationLogRepository",
    "CaseInbox",
    "CaseInboxRepository",
    "CaseIngestionLog",
    "CaseIngestionLogRepository",
    "CaseRepository",
    "CaseSession",
    "CaseSessionMessage",
    "CaseSessionMessageRepository",
    "CaseSessionRepository",
    "DraftTemplate",
    "DraftTemplateRepository",
    "LlmCostLog",
    "LlmCostLogRepository",
    "ReferenceData",
    "ReferenceDataRepository",
]
