"""Shared base class for async Postgres repositories.

Each repository encapsulates CRUD for a single SQLAlchemy model and
inherits the AsyncSessionLocal context helper from here so subclasses
don't need to import it directly. Session boundary + rollback-on-error
patterns stay in the subclass methods because their log messages are
operation-specific — the only thing this base DRYs is session handle.
"""

from src.chatbot.database import AsyncSessionLocal


class BaseRepository:
    """Base class that gives every repository the `_session()` context-manager helper for async Postgres access."""

    @staticmethod
    def _session():
        """Return a new AsyncSessionLocal context manager."""
        return AsyncSessionLocal()
