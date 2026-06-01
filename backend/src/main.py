"""FastAPI application entry point for AI Petition Reviewer."""

import asyncio
import secrets
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_core.tracers.langchain import wait_for_all_tracers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .auth.database import init_user_db
from .auth.admin_routes import router as admin_router
from .auth.routes import router as auth_router
from .billing.routes import router as billing_router
from .billing.seed import seed_plans
from .billing.webhook import router as billing_webhook_router
from .chatbot.database import init_db
from .chatbot.routes import router as chatbot_router
from .chatbot.vectorestore import load_bankruptcy_knowledge
from .config import settings
from .core.common.storage.database import AttorneyRosterRepository
from .core.router import router as core_router
from .core.studio_v2.router import router as studio_v2_router
from .courtdrive.routes import router as motion_router
from .firms import models as _firms_models  # noqa: F401 — registers Firm mapper
from .collaboration import models as _collaboration_models  # noqa: F401 — registers MotionComment mapper
from .collaboration.routes import router as collab_router
from .settings import models as _settings_models  # noqa: F401 — registers UserSettings, FirmSettings, AuditLog mappers
from .settings.routes import router as settings_router
from .firms.routes import router as firms_router
from .gmail.poll_worker import CourtMailPollWorker
from .gmail.routes import router as gmail_router
from .routes.dashboard import router as dashboard_router
from .routes.events import router as events_router
from .routes.pleadings import router as pleadings_router
from .routes.reviews import router as reviews_router
from .routes.stream import router as stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # === STARTUP ===
    await init_db()
    await init_user_db()

    # System-config: guarantee the attorney roster row exists so every
    # /core/attorneys read path and future dropdown_from_constants resolver
    # can assume it's there. Idempotent.
    try:
        await AttorneyRosterRepository.ensure_exists()
    except Exception as e:
        print(f"Warning: failed to ensure attorney roster exists at startup: {e}")

    try:
        await seed_plans()
    except Exception as e:
        print(f"Warning: failed to seed billing plans at startup: {e}")

    print("Loading bankruptcy knowledge into vectorstore...")
    knowledge_result = load_bankruptcy_knowledge()

    if knowledge_result['success']:
        print(f"Bankruptcy knowledge loaded successfully!")
        print(f"   - Files processed: {knowledge_result['total_files']}")
        print(f"   - Documents stored: {knowledge_result['stored_count']}")
    else:
        print(f"Failed to load bankruptcy knowledge: {knowledge_result.get('error', 'Unknown error')}")
        if knowledge_result.get('failed_files'):
            print("   Failed files:")
            for failed in knowledge_result['failed_files']:
                print(f"     - {failed['file']}: {failed['error']}")

    app.state.court_mail_poll_worker = None
    if settings.COURT_MAIL_POLL_WORKER_ENABLED:
        worker = CourtMailPollWorker(
            interval_seconds=settings.COURT_MAIL_POLL_INTERVAL_SECONDS,
            max_results_per_trigger=settings.COURT_MAIL_POLL_MAX_RESULTS_PER_TRIGGER,
        )
        await worker.start(run_immediately=settings.COURT_MAIL_POLL_RUN_ON_STARTUP)
        app.state.court_mail_poll_worker = worker

    from .taskiq_app import startup as taskiq_startup
    await taskiq_startup()

    yield

    # === SHUTDOWN ===
    wait_for_all_tracers()

    worker = getattr(app.state, "court_mail_poll_worker", None)
    if worker:
        await worker.stop()

    from .taskiq_app import shutdown as taskiq_shutdown
    await taskiq_shutdown()


app = FastAPI(
    title="AI Petition Reviewer API",
    version="2.0.0",
    description="Modular backend for AI Petition Reviewer with chatbot, motion drafting, and authentication",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Shared JWT extraction used by both middlewares below.
# ---------------------------------------------------------------------------
def _extract_jwt_fields(request: Request):
    from .auth.auth import decode_access_token
    candidates = []
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        candidates.append(cookie_token)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        candidates.append(auth_header[7:])
    for token in candidates:
        try:
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            if user_id:
                return user_id, payload.get("firm_id")
        except Exception:
            pass
    return None, None


# ---------------------------------------------------------------------------
# Subscription gate — blocks billable endpoints when the firm's subscription
# is not active or trialing (e.g. past_due, canceled, or never subscribed).
# Returns 402 Payment Required so the frontend can redirect to billing.
# ---------------------------------------------------------------------------
class SubscriptionGateMiddleware(BaseHTTPMiddleware):
    _ALLOWED_STATUSES = {"active", "trialing"}

    # (method, path_prefix) pairs — any request matching either is gated.
    _GATED = [
        ("POST", "/api/chat"),
        ("POST", "/api/chat-stream"),
        ("POST", "/api/upload-pdf"),
        ("POST", "/api/upload-objection-pdf"),
        ("POST", "/api/upload-motion-pdf"),
        ("POST", "/api/upload-loe-supporting-docs"),
        ("POST", "/api/upload-order-delay-motion"),
        ("POST", "/api/generate-"),
        ("POST", "/api/pleadings/generate"),
        ("POST", "/api/pleadings/tasks/"),
    ]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        gated = any(
            method == gm and path.startswith(gp)
            for gm, gp in self._GATED
        )
        if not gated:
            return await call_next(request)

        _, firm_id = _extract_jwt_fields(request)
        if not firm_id:
            return await call_next(request)  # let the auth layer handle it

        from .settings.service import get_paywall_enabled
        if not await get_paywall_enabled(firm_id):
            return await call_next(request)

        from .billing.service import get_subscription
        sub = await get_subscription(firm_id)

        if not sub or sub.status.value not in self._ALLOWED_STATUSES:
            return JSONResponse(
                {"detail": "An active subscription is required. Please subscribe to continue."},
                status_code=402,
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Activity log middleware — tracks all meaningful user actions across routes
# without touching each handler individually.
# Fires only on successful responses (status < 400).
# ---------------------------------------------------------------------------
class ActivityLogMiddleware(BaseHTTPMiddleware):
    _GENERATE_PREFIXES = ("/api/generate-",)

    # (method, path_prefix, path_suffix_or_None) -> action_name
    # suffix=None means prefix match is sufficient (no suffix check)
    _ROUTE_ACTIONS = [
        ("GET",  "/api/motions/download",  None,          "download_motion"),
        ("GET",  "/api/download-petition", None,          "download_petition"),
        ("POST", "/api/pleadings/tasks/",  "/input",      "pleading_task_input"),
        ("POST", "/api/pleadings/tasks/",  "/cancel",     "pleading_task_cancel"),
        ("POST", "/api/pleadings/tasks/",  "/regenerate", "pleading_task_regenerate"),
        ("POST", "/api/pleadings/tasks/",  "/use-existing", "pleading_use_existing"),
        ("POST", "/api/reviews/tasks/",    "/cancel",     "review_task_cancel"),
    ]

    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        path = request.url.path
        method = request.method
        status_code = response.status_code

        from .chatbot.database import log_user_action
        from .billing.service import report_usage_event

        # Detailed generate-document tracking (derives motion_type + format from URL)
        if method == "POST" and any(path.startswith(p) for p in self._GENERATE_PREFIXES):
            segment = path.split("/api/generate-", 1)[-1]
            fmt = "docx" if segment.endswith("-docx") else "pdf"
            motion_type = segment.removesuffix("-pdf").removesuffix("-docx")
            user_id, firm_id = _extract_jwt_fields(request)
            asyncio.create_task(log_user_action(
                action="generate_document",
                user_id=user_id,
                firm_id=firm_id,
                metadata={"motion_type": motion_type, "format": fmt, "status_code": status_code, "duration_ms": duration_ms},
            ))
            if firm_id and status_code < 400:
                asyncio.create_task(report_usage_event(firm_id, "agt_composition"))
            return response

        # Only track /api/* routes
        if not path.startswith("/api/"):
            return response

        user_id, firm_id = _extract_jwt_fields(request)

        # Count-only tracking for explicitly named routes
        matched = False
        for route_method, prefix, suffix, action in self._ROUTE_ACTIONS:
            if method == route_method and path.startswith(prefix):
                if suffix is None or path.endswith(suffix):
                    asyncio.create_task(log_user_action(
                        action=action,
                        user_id=user_id,
                        firm_id=firm_id,
                        metadata={"status_code": status_code, "duration_ms": duration_ms},
                    ))
                    matched = True
                    break

        # Catch-all: every /api/* call not already captured gets logged as "others"
        # This ensures total call count matches what's visible in access logs
        if not matched:
            asyncio.create_task(log_user_action(
                action="others",
                user_id=user_id,
                firm_id=firm_id,
                metadata={"path": path, "method": method, "status_code": status_code, "duration_ms": duration_ms},
            ))

        return response


# ---------------------------------------------------------------------------
# CSRF middleware — double-submit cookie pattern.
# For cookie-authenticated mutation requests, the X-CSRF-Token header must
# match the csrf_token cookie set at login time.
# Bearer-only requests (no access_token cookie) are exempt — the token itself
# proves intent and Bearer can't be set by a cross-origin form.
# Login/register/refresh are exempt: no session exists yet (login/register)
# or the refresh token cookie IS the sole credential (refresh).
# ---------------------------------------------------------------------------
class CsrfMiddleware(BaseHTTPMiddleware):
    _SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    _EXEMPT_PATHS = {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/refresh",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/firms/invite/accept",  # public — no session exists yet
    }

    async def dispatch(self, request: Request, call_next):
        if request.method in self._SAFE_METHODS:
            return await call_next(request)

        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)

        # Only enforce when the request is cookie-authenticated.
        if "access_token" not in request.cookies:
            return await call_next(request)

        # Bearer header present alongside the cookie = frontend is still in
        # the migration period. Skip CSRF — the token itself proves intent.
        if request.headers.get("Authorization", "").startswith("Bearer "):
            return await call_next(request)

        csrf_cookie = request.cookies.get("csrf_token", "")
        csrf_header = request.headers.get("X-CSRF-Token", "")

        if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
            return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)

        return await call_next(request)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-CSRF-Token"],
)
app.add_middleware(CsrfMiddleware)
app.add_middleware(ActivityLogMiddleware)
app.add_middleware(SubscriptionGateMiddleware)

# Include routers with proper prefixing
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(chatbot_router, prefix="/api")
app.include_router(motion_router, prefix="/api")
app.include_router(gmail_router, prefix="/api")
app.include_router(stream_router, prefix="/api")
app.include_router(pleadings_router, prefix="/api/pleadings")
app.include_router(reviews_router, prefix="/api/reviews")
app.include_router(dashboard_router, prefix="/api/dashboard")
app.include_router(core_router, prefix="/api/v2")
app.include_router(studio_v2_router, prefix="/api/v3")
app.include_router(events_router, prefix="/api")
app.include_router(billing_webhook_router, prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(firms_router, prefix="/api")
app.include_router(collab_router, prefix="/api")
app.include_router(settings_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Petition Reviewer API",
        "version": "2.0.0",
        "modules": ["auth", "chatbot", "motion"]
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    worker = getattr(app.state, "court_mail_poll_worker", None)
    return {
        "status": "healthy",
        "court_mail_poll_worker": {
            "enabled": bool(settings.COURT_MAIL_POLL_WORKER_ENABLED),
            "running": bool(worker.is_running) if worker else False,
            "interval_seconds": settings.COURT_MAIL_POLL_INTERVAL_SECONDS,
            "max_results_per_trigger": settings.COURT_MAIL_POLL_MAX_RESULTS_PER_TRIGGER,
            "last_run_at": worker.last_run_at if worker else None,
            "last_result": worker.last_result if worker else None,
        },
    }


if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=True,
        log_level="info"
    )
