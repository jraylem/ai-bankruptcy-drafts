"""Langfuse LangChain integration — opt-in via environment variables.

Returns a ready-to-attach LangChain `CallbackHandler` when all three of
`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL`
(or `LANGFUSE_HOST`) are set. Returns `None` otherwise — calling sites
detect the `None` and skip attaching, so Langfuse stays completely
silent in environments where the keys haven't been provisioned (prod
without observability creds, CI, unit tests, etc.).

Cached at module load: the handler is built ONCE and reused across
every agent run. Langfuse's `CallbackHandler` is process-local and
thread-safe — multiple LangChain runs can share it.

Failure mode is silent: if the `langfuse` package isn't installed
(missing optional dependency) or initialization raises, we log and
return `None`. The pipeline keeps running with only the existing
`CostTrackingCallback` attached.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _read_credentials() -> tuple[str, str, str] | None:
    """Read Langfuse credentials from the environment.

    Returns `(public_key, secret_key, host)` when all three are set,
    otherwise returns `None`. Accepts either `LANGFUSE_BASE_URL`
    (docs name) or `LANGFUSE_HOST` (SDK alt name) for the host.
    """
    public = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    secret = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    host = (
        os.environ.get("LANGFUSE_BASE_URL", "").strip()
        or os.environ.get("LANGFUSE_HOST", "").strip()
    )
    if not (public and secret and host):
        return None
    return public, secret, host


_cached_handler: Any | None = None
_cache_initialized = False


def langfuse_callback() -> Any | None:
    """Return a LangChain `CallbackHandler` bound to the firm's
    Langfuse project, or `None` when the integration is disabled.

    Disabled when:
    - Any of `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` /
      (`LANGFUSE_BASE_URL` or `LANGFUSE_HOST`) is missing or empty.
    - The `langfuse` package isn't importable (optional dep).
    - Initialization raises (bad host URL, etc.) — logged once.

    Callers pattern:
        cb = langfuse_callback()
        callbacks = [CostTrackingCallback(...)]
        if cb is not None:
            callbacks.append(cb)
    """
    global _cached_handler, _cache_initialized
    if _cache_initialized:
        return _cached_handler

    _cache_initialized = True
    creds = _read_credentials()
    if creds is None:
        logger.debug(
            "Langfuse disabled — LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / "
            "LANGFUSE_BASE_URL not all set.",
        )
        _cached_handler = None
        return None

    public, secret, host = creds
    try:
        # The SDK reads credentials from env vars at import time; pass
        # them through env so we don't have to hand-thread them into
        # the handler constructor (the API has shifted across versions).
        os.environ["LANGFUSE_PUBLIC_KEY"] = public
        os.environ["LANGFUSE_SECRET_KEY"] = secret
        os.environ["LANGFUSE_HOST"] = host
        from langfuse.langchain import CallbackHandler
    except ImportError as err:
        logger.warning(
            "langfuse_callback: `langfuse` package not importable (%s) — "
            "tracing disabled. Add `langfuse` to pyproject.toml to enable.",
            err,
        )
        _cached_handler = None
        return None

    try:
        _cached_handler = CallbackHandler()
        logger.info(
            "Langfuse tracing enabled — host=%s, public_key=%s***",
            host,
            public[:10] if len(public) > 10 else public,
        )
        return _cached_handler
    except Exception as err:  # noqa: BLE001 — never raise into the pipeline
        logger.warning(
            "langfuse_callback: handler construction failed (%s) — "
            "tracing disabled.",
            err,
        )
        _cached_handler = None
        return None


def reset_cache_for_tests() -> None:
    """Reset the module-level handler cache. Test-only — production
    callers should never need this since env vars don't change at
    runtime."""
    global _cached_handler, _cache_initialized
    _cached_handler = None
    _cache_initialized = False
