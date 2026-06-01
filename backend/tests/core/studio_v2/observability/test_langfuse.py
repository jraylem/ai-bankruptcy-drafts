"""Tests for `langfuse_callback()` — the opt-in tracing helper.

The helper returns a LangChain CallbackHandler when all three env vars
are set, otherwise returns None so the integration is fully disabled.
Failure modes (missing package, init exception) are silent — they log
and return None so the LLM pipeline never aborts.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.studio_v2.observability.langfuse import (
    _read_credentials,
    langfuse_callback,
    reset_cache_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_handler_cache():
    """Wipe the module-level cache between tests so each one gets a
    fresh init attempt."""
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


# ─── _read_credentials ───────────────────────────────────────────────


@pytest.mark.unit
def test_read_credentials_returns_none_when_all_missing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    assert _read_credentials() is None


@pytest.mark.unit
def test_read_credentials_returns_none_when_public_missing(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-xxx")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    assert _read_credentials() is None


@pytest.mark.unit
def test_read_credentials_returns_none_when_secret_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-xxx")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    assert _read_credentials() is None


@pytest.mark.unit
def test_read_credentials_returns_none_when_host_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-xxx")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-xxx")
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    assert _read_credentials() is None


@pytest.mark.unit
def test_read_credentials_accepts_langfuse_host_alias(monkeypatch):
    """LANGFUSE_HOST is the SDK's canonical name; LANGFUSE_BASE_URL is
    the docs' name. The helper must accept either."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-xxx")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-xxx")
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    creds = _read_credentials()
    assert creds == ("pk-xxx", "sk-xxx", "https://us.cloud.langfuse.com")


@pytest.mark.unit
def test_read_credentials_treats_whitespace_only_as_missing(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "  ")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-xxx")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    assert _read_credentials() is None


# ─── langfuse_callback ───────────────────────────────────────────────


@pytest.mark.unit
def test_langfuse_callback_returns_none_when_disabled(monkeypatch):
    """No env vars → handler is None and the integration is silent.
    This is the production-by-default path."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    assert langfuse_callback() is None


@pytest.mark.unit
def test_langfuse_callback_returns_handler_when_enabled(monkeypatch):
    """All three env vars set + package imports OK → returns the
    LangChain handler."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    fake_handler = MagicMock(name="LangfuseHandler")
    with patch(
        "langfuse.langchain.CallbackHandler",
        return_value=fake_handler,
    ):
        result = langfuse_callback()
        assert result is fake_handler


@pytest.mark.unit
def test_langfuse_callback_returns_none_on_init_exception(monkeypatch):
    """Handler constructor raises → caught + returns None. The LLM
    pipeline must never crash because Langfuse misbehaved."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    with patch(
        "langfuse.langchain.CallbackHandler",
        side_effect=RuntimeError("bad host"),
    ):
        assert langfuse_callback() is None


@pytest.mark.unit
def test_langfuse_callback_cached_across_calls(monkeypatch):
    """The handler is built ONCE and reused across every agent run —
    the constructor is only called once even with repeated calls."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    fake_handler = MagicMock(name="LangfuseHandler")
    with patch(
        "langfuse.langchain.CallbackHandler",
        return_value=fake_handler,
    ) as mock_ctor:
        r1 = langfuse_callback()
        r2 = langfuse_callback()
        r3 = langfuse_callback()
    assert r1 is r2 is r3 is fake_handler
    assert mock_ctor.call_count == 1


@pytest.mark.unit
def test_langfuse_callback_cached_none_across_calls(monkeypatch):
    """The disabled-state (None) is also cached. We don't re-check env
    vars on every call once we've determined the integration is off."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    assert langfuse_callback() is None
    # After caching, even if env vars magically appear, we still return None.
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-late")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-late")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    assert langfuse_callback() is None
