"""Async CRUD repository for the ReferenceData ORM model (reusable constants keyed by short_code)."""

import logging

from sqlalchemy import text

from ..models import ReferenceData
from .base import BaseRepository

logger = logging.getLogger(__name__)


class ReferenceDataRepository(BaseRepository):
    """Async CRUD over the ReferenceData table — reusable constants keyed by short_code (firm name, attorney name, etc.)."""

    @classmethod
    async def create(
        cls,
        short_code: str,
        display_name: str,
        value: str,
        category: str | None = None,
        description: str | None = None,
    ) -> ReferenceData:
        """Create a new reference data entry."""
        async with cls._session() as session:
            try:
                ref_data = ReferenceData(
                    short_code=short_code,
                    display_name=display_name,
                    value=value,
                    category=category,
                    description=description,
                )
                session.add(ref_data)
                await session.commit()
                await session.refresh(ref_data)
                logger.info(f"Created reference data: {short_code}")
                return ref_data
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to create reference data {short_code}: {e}")
                raise

    @classmethod
    async def get(cls, short_code: str) -> ReferenceData | None:
        """Get reference data by short_code."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        "SELECT * FROM reference_data WHERE short_code = :short_code AND is_active = true"
                    ),
                    {"short_code": short_code},
                )
                row = result.fetchone()
                if row:
                    return ReferenceData(**dict(row._mapping))
                return None
            except Exception as e:
                logger.error(f"Failed to get reference data {short_code}: {e}")
                raise

    @classmethod
    async def list(cls, category: str | None = None) -> list[ReferenceData]:
        """List all active reference data, optionally filtered by category."""
        async with cls._session() as session:
            try:
                if category:
                    result = await session.execute(
                        text(
                            "SELECT * FROM reference_data WHERE is_active = true AND category = :category ORDER BY short_code"
                        ),
                        {"category": category},
                    )
                else:
                    result = await session.execute(
                        text("SELECT * FROM reference_data WHERE is_active = true ORDER BY short_code")
                    )
                rows = result.fetchall()
                return [ReferenceData(**dict(r._mapping)) for r in rows]
            except Exception as e:
                logger.error(f"Failed to list reference data: {e}")
                raise

    @classmethod
    async def update(
        cls,
        short_code: str,
        display_name: str | None = None,
        value: str | None = None,
        category: str | None = None,
        description: str | None = None,
    ) -> ReferenceData | None:
        """Update reference data by short_code."""
        async with cls._session() as session:
            try:
                sets = []
                params = {"short_code": short_code}

                if display_name is not None:
                    sets.append("display_name = :display_name")
                    params["display_name"] = display_name
                if value is not None:
                    sets.append("value = :value")
                    params["value"] = value
                if category is not None:
                    sets.append("category = :category")
                    params["category"] = category
                if description is not None:
                    sets.append("description = :description")
                    params["description"] = description

                if not sets:
                    return None

                sets.append("updated_at = now()")
                set_clause = ", ".join(sets)

                await session.execute(
                    text(f"UPDATE reference_data SET {set_clause} WHERE short_code = :short_code"),
                    params,
                )
                await session.commit()

                result = await session.execute(
                    text("SELECT * FROM reference_data WHERE short_code = :short_code"),
                    {"short_code": short_code},
                )
                row = result.fetchone()
                return ReferenceData(**dict(row._mapping)) if row else None
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update reference data {short_code}: {e}")
                raise

    @classmethod
    async def delete(cls, short_code: str) -> bool:
        """Soft-delete reference data by short_code."""
        async with cls._session() as session:
            try:
                await session.execute(
                    text("UPDATE reference_data SET is_active = false WHERE short_code = :short_code"),
                    {"short_code": short_code},
                )
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to delete reference data {short_code}: {e}")
                raise
