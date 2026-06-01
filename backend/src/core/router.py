"""Top-level /core router — aggregates every component-level router under a single /core prefix."""

from fastapi import APIRouter

from .components.attorneys.router import router as attorneys_router
from .components.case_inbox.router import router as case_inbox_router
from .components.cases.router import router as cases_router
from .components.chat.router import router as chat_router
from .components.costs.router import router as costs_router
from .components.engines.draft.router import router as draft_router
from .components.engines.template.router import router as template_router
from .components.pleading.router import router as pleading_router

router = APIRouter(prefix="/core", tags=["Core"])

router.include_router(template_router)
router.include_router(draft_router)
router.include_router(cases_router)
router.include_router(attorneys_router)
router.include_router(pleading_router)
router.include_router(chat_router)
router.include_router(costs_router)
router.include_router(case_inbox_router)
