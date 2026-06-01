"""Shared fixtures for every test under tests/core/.

Populate as additional tests need shared setup. Per-layer fixtures
(e.g. LLM mocks for agent tests) live in the nearest conftest, not here.
"""

# Register MotionComment mapper so MotionDraftLog.comments relationship
# resolves correctly in tests that import chatbot/models.py.
import src.collaboration.models as _collaboration_models  # noqa: F401
