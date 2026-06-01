"""Typed repository for the attorney roster — a reserved reference_data row whose value is a JSON array of attorney entries.

Wraps ReferenceDataRepository so callers see typed `Attorney` Pydantic models
instead of a JSON blob. The roster is a *system config*: a single
`reference_data` row with short_code=ATTORNEYS that every read path can
assume exists (see `ensure_exists`). Later we'll wire up a
`dropdown_from_constants` source that reads this list so authors can bind a
template field to an attorney pick at draft time.
"""

from __future__ import annotations  # so `list[Attorney]` in method hints isn't eagerly resolved against the `list` classmethod on this class

import json
import logging
import uuid

from pydantic import BaseModel, Field

from .reference_data_repository import ReferenceDataRepository

logger = logging.getLogger(__name__)


ATTORNEYS_SHORT_CODE = "ATTORNEYS"
_ROSTER_DISPLAY_NAME = "Attorney Roster"
_ROSTER_CATEGORY = "system"
_ROSTER_DESCRIPTION = "Curated list of attorneys referenced by dropdown_from_constants template fields. Managed via /core/attorneys."


class Attorney(BaseModel):
    """One attorney entry in the roster. `id` is stable so templates can
    reference an attorney without breaking when display name changes."""

    id: str = Field(description="Stable UUID4 assigned at add-time; never reused.")
    full_name: str = Field(description="Signed form including suffix when applicable (e.g. 'Chad Van Horn, Esq.').")


class AttorneyRosterRepository:
    """Typed CRUD over the ATTORNEYS reference_data row (JSON list of Attorney entries)."""

    @classmethod
    async def ensure_exists(cls) -> None:
        """Seed the ATTORNEYS reference_data row with an empty list if missing.

        Idempotent — safe to call on every service startup. Every other
        method assumes the row exists.
        """
        existing = await ReferenceDataRepository.get(ATTORNEYS_SHORT_CODE)
        if existing is not None:
            return
        await ReferenceDataRepository.create(
            short_code=ATTORNEYS_SHORT_CODE,
            display_name=_ROSTER_DISPLAY_NAME,
            value="[]",
            category=_ROSTER_CATEGORY,
            description=_ROSTER_DESCRIPTION,
        )
        logger.info("Seeded empty attorney roster (%s)", ATTORNEYS_SHORT_CODE)

    @classmethod
    async def list(cls) -> list[Attorney]:
        """Return the roster as a list of `Attorney` models.

        Returns an empty list if the row exists but the value fails to parse —
        corrupted JSON is logged and treated as a fresh roster so the
        endpoint stays responsive.
        """
        row = await ReferenceDataRepository.get(ATTORNEYS_SHORT_CODE)
        if row is None:
            return []
        try:
            raw = json.loads(row.value or "[]")
        except json.JSONDecodeError:
            logger.error("Attorney roster JSON is corrupt; treating as empty")
            return []
        return [Attorney.model_validate(item) for item in raw]

    @classmethod
    async def get(cls, attorney_id: str) -> Attorney | None:
        """Return the attorney with the given `id` or None."""
        for att in await cls.list():
            if att.id == attorney_id:
                return att
        return None

    @classmethod
    async def add(cls, full_name: str) -> Attorney:
        """Append a new attorney to the roster; returns the created entry with a fresh UUID."""
        roster = await cls.list()
        attorney = Attorney(id=str(uuid.uuid4()), full_name=full_name)
        roster.append(attorney)
        await cls._write(roster)
        return attorney

    @classmethod
    async def update(cls, attorney_id: str, full_name: str) -> Attorney | None:
        """Replace the `full_name` of the attorney with the given id; returns None if id is unknown."""
        roster = await cls.list()
        for i, att in enumerate(roster):
            if att.id == attorney_id:
                updated = att.model_copy(update={"full_name": full_name})
                roster[i] = updated
                await cls._write(roster)
                return updated
        return None

    @classmethod
    async def delete(cls, attorney_id: str) -> bool:
        """Remove the attorney with the given id; returns True if removed, False if id was unknown."""
        roster = await cls.list()
        filtered = [att for att in roster if att.id != attorney_id]
        if len(filtered) == len(roster):
            return False
        await cls._write(filtered)
        return True

    @classmethod
    async def _write(cls, roster: list[Attorney]) -> None:
        """Serialize `roster` to JSON and persist via ReferenceDataRepository.update."""
        serialized = json.dumps([att.model_dump() for att in roster])
        result = await ReferenceDataRepository.update(
            short_code=ATTORNEYS_SHORT_CODE,
            value=serialized,
        )
        if result is None:
            # Row was missing — self-heal by seeding, then retry once. This
            # covers test / fresh-DB scenarios where ensure_exists hasn't run.
            await cls.ensure_exists()
            await ReferenceDataRepository.update(
                short_code=ATTORNEYS_SHORT_CODE,
                value=serialized,
            )
