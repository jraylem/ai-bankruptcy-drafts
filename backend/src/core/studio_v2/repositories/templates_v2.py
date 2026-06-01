"""Async CRUD repository for the TemplateV2 ORM model.

Mutations scope their WHERE clause to `is_active = true` so soft-deleted
rows are effectively immutable even if a future caller forgets the
existence pre-check. Mirrors the conventions in v1's
`DraftTemplateRepository`.

Phase 1 surface: create / get / list / update / soft-delete. The
publish endpoint (Phase 3) uses `update_published_snapshot()` —
exposed here but not yet wired by any caller in Phase 1.
"""

import logging

from sqlalchemy import desc, select

from src.core.common.storage.database.repositories.base import BaseRepository

from .models import TemplateV2

logger = logging.getLogger(__name__)


class TemplatesV2Repository(BaseRepository):
    """Async CRUD over the templates_v2 table."""

    @classmethod
    async def create(
        cls,
        template_id: str,
        name: str,
        config: dict | None = None,
        original_doc_url: str | None = None,
        template_doc_url: str | None = None,
        firm_id: str | None = None,
    ) -> TemplateV2:
        """Create a new v2 template row. Returns the row (refreshed)."""
        async with cls._session() as session:
            try:
                row = TemplateV2(
                    id=template_id,
                    firm_id=firm_id,
                    name=name,
                    config=config if config is not None else {"role": "single", "companions": []},
                    original_doc_url=original_doc_url,
                    template_doc_url=template_doc_url,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return row
            except Exception as e:
                await session.rollback()
                logger.exception("TemplatesV2Repository.create failed for %s: %s", template_id, e)
                raise

    @classmethod
    async def get(cls, template_id: str) -> TemplateV2 | None:
        """Fetch an ACTIVE template by id; returns None if not found or soft-deleted."""
        async with cls._session() as session:
            stmt = select(TemplateV2).where(
                TemplateV2.id == template_id,
                TemplateV2.is_active.is_(True),
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @classmethod
    async def list(
        cls,
        firm_id: str | None = None,
        published_only: bool = False,
    ) -> list[TemplateV2]:
        """List active templates ordered by created_at DESC.

        `firm_id` filter is optional — when None, returns rows across firms
        (admin/global view). `published_only=True` filters to rows that have
        been published at least once (`published_at IS NOT NULL`).
        """
        async with cls._session() as session:
            stmt = select(TemplateV2).where(TemplateV2.is_active.is_(True))
            if firm_id is not None:
                stmt = stmt.where(TemplateV2.firm_id == firm_id)
            if published_only:
                stmt = stmt.where(TemplateV2.published_at.isnot(None))
            stmt = stmt.order_by(desc(TemplateV2.created_at))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def update(
        cls,
        template_id: str,
        *,
        name: str | None = None,
        config: dict | None = None,
        original_doc_url: str | None = None,
        template_doc_url: str | None = None,
    ) -> TemplateV2 | None:
        """Partial update — only non-None args mutate. Returns None if the
        row doesn't exist or is soft-deleted. **Does NOT touch
        published_at / published_spec** — those move only via
        `update_published_snapshot()`.
        """
        async with cls._session() as session:
            try:
                stmt = select(TemplateV2).where(
                    TemplateV2.id == template_id,
                    TemplateV2.is_active.is_(True),
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                if name is not None:
                    row.name = name
                if config is not None:
                    row.config = config
                if original_doc_url is not None:
                    row.original_doc_url = original_doc_url
                if template_doc_url is not None:
                    row.template_doc_url = template_doc_url
                await session.commit()
                await session.refresh(row)
                return row
            except Exception as e:
                await session.rollback()
                logger.exception("TemplatesV2Repository.update failed for %s: %s", template_id, e)
                raise

    @classmethod
    async def update_published_snapshot(
        cls,
        template_id: str,
        published_spec: dict,
    ) -> TemplateV2 | None:
        """Set `published_spec` JSONB + bump `published_at` to NOW().

        Called by the Phase 3 publish endpoint AFTER validate_for_draft_v2
        passes. Phase 1 doesn't call this; the column sits NULL until then.
        """
        from datetime import datetime, timezone

        async with cls._session() as session:
            try:
                stmt = select(TemplateV2).where(
                    TemplateV2.id == template_id,
                    TemplateV2.is_active.is_(True),
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                row.published_spec = published_spec
                row.published_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(row)
                return row
            except Exception as e:
                await session.rollback()
                logger.exception(
                    "TemplatesV2Repository.update_published_snapshot failed for %s: %s",
                    template_id, e,
                )
                raise

    @classmethod
    async def touch_updated_at(cls, template_id: str) -> TemplateV2 | None:
        """Bump `templates_v2.updated_at` to NOW() without touching
        any other column.

        Called after a child-row mutation (per-field PATCH, future
        bulk operations) so the BE-computed
        `has_unpublished_changes = updated_at > published_at` reflects
        the working-draft drift. Without this, edits to
        `template_fields_v2` rows leave the parent's `updated_at`
        stale and the PublishStep status pill stays "Live" forever.

        Returns None if the row doesn't exist or is soft-deleted.
        """
        from datetime import datetime, timezone

        async with cls._session() as session:
            try:
                stmt = select(TemplateV2).where(
                    TemplateV2.id == template_id,
                    TemplateV2.is_active.is_(True),
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                row.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(row)
                return row
            except Exception as e:
                await session.rollback()
                logger.exception(
                    "TemplatesV2Repository.touch_updated_at failed for %s: %s",
                    template_id, e,
                )
                raise

    @classmethod
    async def soft_delete(cls, template_id: str) -> bool:
        """Soft-delete: flip is_active to false. Idempotent — returns
        True if the row was active and is now inactive; False if it was
        already inactive or didn't exist.
        """
        async with cls._session() as session:
            try:
                stmt = select(TemplateV2).where(
                    TemplateV2.id == template_id,
                    TemplateV2.is_active.is_(True),
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return False
                row.is_active = False
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.exception("TemplatesV2Repository.soft_delete failed for %s: %s", template_id, e)
                raise
