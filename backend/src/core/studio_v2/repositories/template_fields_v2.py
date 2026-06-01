"""Async CRUD repository for the TemplateFieldV2 ORM model.

Phase 1 operations:
- create_many(): batch insert at composer time (one row per variable).
- list_for_template(): load the working spec for a template.
- get(): fetch one field by id (for PATCH).
- patch_params(): atomic per-field params update (the wizard's save).
- re_extract_diff_apply(): on regenerate, diff the new spec against
  existing rows by `template_variable` name and INSERT/UPDATE/DELETE,
  preserving wizard-saved `params` on kept fields.

The diff CLASSIFICATION (inserted / updated / deleted by name) is
extracted as a pure function `classify_re_extract_diff()` so it's
unit-testable without a DB session — the ORM mutations themselves
just follow the classification deterministically.
"""

import logging
import uuid

from sqlalchemy import func, select

from src.core.common.storage.database.repositories.base import BaseRepository

from .models import TemplateFieldV2

logger = logging.getLogger(__name__)


def classify_re_extract_diff(
    existing_names: set[str],
    new_names: set[str],
) -> "tuple[list[str], list[str], list[str]]":
    """Pure classification of the re-extract diff by variable name.

    Returns (inserted, updated, deleted) lists. Inserted = new but not
    existing; updated = both (kept rows whose composer-set fields refresh
    but whose wizard-saved `params` MUST be preserved verbatim);
    deleted = existing but not new (paralegal merged or ignored).

    Extracted from `re_extract_diff_apply` so the set-difference logic
    is testable without a DB session.
    """
    inserted = sorted(new_names - existing_names)
    updated = sorted(new_names & existing_names)
    deleted = sorted(existing_names - new_names)
    return inserted, updated, deleted


class TemplateFieldsV2Repository(BaseRepository):
    """Async CRUD over the template_fields_v2 table."""

    @classmethod
    async def create_many(
        cls,
        template_id: str,
        fields: list[dict],
    ) -> list[TemplateFieldV2]:
        """Batch insert. Each dict in `fields` carries:
            template_variable, template_property_marker?, aliases?,
            template_identifying_text_match?, description?,
            template_index?, params?.
        Returns the persisted rows (with generated ids).
        """
        async with cls._session() as session:
            try:
                rows = [
                    TemplateFieldV2(
                        id=str(uuid.uuid4()),
                        template_id=template_id,
                        template_variable=f["template_variable"],
                        template_property_marker=f.get("template_property_marker"),
                        template_property_marker_aliases=f.get("template_property_marker_aliases"),
                        template_identifying_text_match=f.get("template_identifying_text_match"),
                        description=f.get("description"),
                        template_index=f.get("template_index", 0),
                        params=f.get("params"),
                    )
                    for f in fields
                ]
                session.add_all(rows)
                await session.commit()
                for row in rows:
                    await session.refresh(row)
                return rows
            except Exception as e:
                await session.rollback()
                logger.exception("TemplateFieldsV2Repository.create_many failed for %s: %s", template_id, e)
                raise

    @classmethod
    async def list_for_template(cls, template_id: str) -> list[TemplateFieldV2]:
        """Return all fields for a template, ordered by template_index."""
        async with cls._session() as session:
            stmt = (
                select(TemplateFieldV2)
                .where(TemplateFieldV2.template_id == template_id)
                .order_by(TemplateFieldV2.template_index)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @classmethod
    async def counts_for_templates(
        cls,
        template_ids: list[str],
    ) -> dict[str, tuple[int, int]]:
        """Return `{template_id: (total_fields, configured_fields)}`
        for every id in `template_ids`. Ids with zero rows are absent
        from the result (caller should default to (0, 0)).

        One grouped query, not N queries — for the rail listing where
        we render N templates' pills without fetching their full
        spec.
        """
        if not template_ids:
            return {}
        async with cls._session() as session:
            # NOTE on `count(params)`: in practice the composer-time
            # agent prefills EVERY field's params with a default
            # `WizardSourceParams` dict, so `params IS NOT NULL` is
            # effectively always true for every row (composer's
            # generate path writes a non-null dict; the wizard's
            # PATCH only overwrites with another non-null dict).
            # Result: `configured_fields` ≈ `total_fields` for every
            # template — the metric IS still useful when the
            # paralegal explicitly clears a field, but the rail
            # grouping deliberately does NOT lean on it. See
            # `TemplatesRail.groupedTemplates` (FE) which groups by
            # `publishedAt` instead — the publish action is the
            # paralegal-meaningful boundary, not field-count parity.
            total_col = func.count().label("total")
            configured_col = func.count(TemplateFieldV2.params).label("configured")
            stmt = (
                select(
                    TemplateFieldV2.template_id,
                    total_col,
                    configured_col,
                )
                .where(TemplateFieldV2.template_id.in_(template_ids))
                .group_by(TemplateFieldV2.template_id)
            )
            result = await session.execute(stmt)
            return {row[0]: (row[1], row[2]) for row in result.all()}

    @classmethod
    async def get(cls, field_id: str) -> TemplateFieldV2 | None:
        async with cls._session() as session:
            stmt = select(TemplateFieldV2).where(TemplateFieldV2.id == field_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @classmethod
    async def patch_params(
        cls,
        field_id: str,
        params: dict | None,
    ) -> TemplateFieldV2 | None:
        """Atomic per-field params update — the wizard's save action.

        Pass `params=None` to clear (e.g. paralegal resets a field).
        Returns None if the field doesn't exist.

        The atomic single-row UPDATE prevents the lost-update race that
        would happen if the wizard read the whole spec, mutated one
        field, and wrote back the whole spec.
        """
        async with cls._session() as session:
            try:
                stmt = select(TemplateFieldV2).where(TemplateFieldV2.id == field_id)
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                row.params = params
                await session.commit()
                await session.refresh(row)
                return row
            except Exception as e:
                await session.rollback()
                logger.exception("TemplateFieldsV2Repository.patch_params failed for %s: %s", field_id, e)
                raise

    @classmethod
    async def re_extract_diff_apply(
        cls,
        template_id: str,
        new_fields: list[dict],
    ) -> "ReExtractDiff":
        """Diff `new_fields` against existing rows by `template_variable`
        name; apply INSERT/UPDATE/DELETE atomically; preserve
        wizard-saved `params` on kept rows.

        Diff rules:
        - Old name not in new → DELETE the row.
        - New name not in old → INSERT with all fields (including
          TemplateAgentV2's pre-populated `params` default).
        - Name in both → UPDATE composer-set fields (marker, aliases,
          identifying text, index, description) from new; KEEP the
          existing row's `params` verbatim.

        Returns a ReExtractDiff summary the FE renders as a
        "what changed" panel.
        """
        async with cls._session() as session:
            try:
                stmt = (
                    select(TemplateFieldV2)
                    .where(TemplateFieldV2.template_id == template_id)
                )
                result = await session.execute(stmt)
                existing = list(result.scalars().all())
                existing_by_name = {row.template_variable: row for row in existing}
                new_by_name = {f["template_variable"]: f for f in new_fields}

                deleted: list[str] = []
                updated: list[str] = []
                inserted: list[str] = []

                # DELETE old rows not present in new spec.
                for name, row in existing_by_name.items():
                    if name not in new_by_name:
                        await session.delete(row)
                        deleted.append(name)

                # INSERT new rows; UPDATE composer-fields on kept rows.
                for name, new_field in new_by_name.items():
                    if name in existing_by_name:
                        row = existing_by_name[name]
                        row.template_property_marker = new_field.get(
                            "template_property_marker",
                        )
                        row.template_property_marker_aliases = new_field.get(
                            "template_property_marker_aliases",
                        )
                        row.template_identifying_text_match = new_field.get(
                            "template_identifying_text_match",
                        )
                        row.description = new_field.get("description")
                        row.template_index = new_field.get("template_index", 0)
                        # PRESERVE row.params verbatim — paralegal's
                        # wizard work is sacred across re-extract.
                        updated.append(name)
                    else:
                        new_row = TemplateFieldV2(
                            id=str(uuid.uuid4()),
                            template_id=template_id,
                            template_variable=name,
                            template_property_marker=new_field.get("template_property_marker"),
                            template_property_marker_aliases=new_field.get(
                                "template_property_marker_aliases",
                            ),
                            template_identifying_text_match=new_field.get(
                                "template_identifying_text_match",
                            ),
                            description=new_field.get("description"),
                            template_index=new_field.get("template_index", 0),
                            params=new_field.get("params"),
                        )
                        session.add(new_row)
                        inserted.append(name)

                await session.commit()
                return ReExtractDiff(
                    inserted=inserted,
                    updated=updated,
                    deleted=deleted,
                )
            except Exception as e:
                await session.rollback()
                logger.exception(
                    "TemplateFieldsV2Repository.re_extract_diff_apply failed for %s: %s",
                    template_id, e,
                )
                raise


from pydantic import BaseModel, Field


class ReExtractDiff(BaseModel):
    """Summary of an `re_extract_diff_apply` run — FE renders as a
    'what changed' panel after the paralegal hits Regenerate.
    """
    inserted: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
