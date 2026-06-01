"""LLM-mocking fixture shared by every agent test."""

import pytest


@pytest.fixture
def mock_agent_invoke(monkeypatch):
    """Patch Agent._invoke to return a caller-provided value and capture
    the (prompt, run_name, metadata) the agent tried to send.

    Usage::

        async def test_something(mock_agent_invoke):
            captured = mock_agent_invoke(SomeOutput(...))  # or None / raise
            await SomeAgent.run(...)
            assert captured["run_name"] == "SomeAgent"

    Pass an Exception instance to simulate the invoke raising.
    """
    from src.core.agents.llm import base as agent_base

    captured: dict = {}

    def make_patch(return_value):
        async def fake_invoke(cls, prompt, run_name, metadata=None):
            captured["prompt"] = prompt
            captured["run_name"] = run_name
            captured["metadata"] = metadata or {}
            if isinstance(return_value, Exception):
                raise return_value
            return return_value

        monkeypatch.setattr(agent_base.Agent, "_invoke", classmethod(fake_invoke))
        return captured

    return make_patch
