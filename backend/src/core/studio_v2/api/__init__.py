"""Studio V2 HTTP routes mounted under /api/v3/studio/*.

Phase 1 shipped the composer slice (templates + fields + re-extract).
Phase 2 adds dry-run (/dry-run + /dry-run/resume).
Draft and chat endpoints land in Phases 3 and 4.
"""

from .composer_router import router as composer_router
from .dry_run_router import router as dry_run_router
from .templates_router import router as templates_router

__all__ = ["composer_router", "dry_run_router", "templates_router"]
