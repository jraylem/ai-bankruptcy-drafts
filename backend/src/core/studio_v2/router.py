"""Top-level studio_v2 router — aggregates the api/ sub-routers.

Mounted in main.py as:
    app.include_router(studio_v2_router, prefix="/api/v3")

Final paths land under /api/v3/studio/*.

Phase 1: composer + templates CRUD.
Phase 2: dry-run (/dry-run + /dry-run/resume).
Phases 3-4 add: drafting (/drafting/*), chat (/chat/draft). When
those land, add their sub-routers via `router.include_router(...)` here.
"""

from fastapi import APIRouter

from .api import composer_router, dry_run_router, templates_router
from .composer.async_run.router import router as composer_async_router
from .dry_run.async_run.router import router as dry_run_async_router

router = APIRouter(tags=["Studio V2"])

router.include_router(composer_router)
router.include_router(templates_router)
router.include_router(dry_run_router)
router.include_router(composer_async_router)
router.include_router(dry_run_async_router)
