"""Async CRUD repository for the DraftTemplate ORM model.

Mutations (update, delete) scope their WHERE clause to `is_active = true`
so soft-deleted rows are effectively immutable even if a future caller
forgets the existence pre-check.
"""

import json
import logging

from sqlalchemy import text

from ..models import DraftTemplate
from .base import BaseRepository

logger = logging.getLogger(__name__)


def _filter_companions_for_child(
    companions: list,
    child_template_id: str,
) -> "tuple[list, list[str]]":
    """Pure function — given a parent's bundle_companions list and a
    child template id, return `(filtered, affected_labels)`:

    - `filtered`: the new bundle_companions list with the doomed child
      removed. Fixed companions matching the child are dropped entirely.
      Branch companions have matching options filtered out; the whole
      branch is dropped if filtering would leave fewer than 2 options
      (BranchBundleCompanion requires min_length=2).
    - `affected_labels`: companion labels of anything that was touched
      (fully dropped OR had an option removed).

    Extracted from `DraftTemplateRepository.prune_companion_references_for_child`
    so the JSONB-walking logic is unit-testable without a DB session.
    """
    affected_labels: list[str] = []
    pruned: list = []
    for companion in companions:
        kind = companion.get("kind")
        label = companion.get("label", "")
        if kind == "fixed":
            if companion.get("child_template_id") == child_template_id:
                affected_labels.append(label)
                continue
            pruned.append(companion)
        elif kind == "branch":
            options = companion.get("options", []) or []
            filtered_options = [
                opt for opt in options
                if opt.get("child_template_id") != child_template_id
            ]
            if len(filtered_options) == len(options):
                pruned.append(companion)
                continue
            affected_labels.append(label)
            if len(filtered_options) >= 2:
                new_companion = dict(companion)
                new_companion["options"] = filtered_options
                pruned.append(new_companion)
            # else drop the whole companion (can't satisfy min_length=2).
        else:
            pruned.append(companion)
    return pruned, affected_labels


class DraftTemplateRepository(BaseRepository):
    """Async CRUD over the DraftTemplate table — one row per template, holds template_spec + committed agent_config."""

    @classmethod
    async def create(
        cls,
        template_id: str,
        name: str,
        original_doc_url: str | None = None,
        template_doc_url: str | None = None,
        template_spec: dict | None = None,
        agent_config: dict | None = None,
        bundle_role: str = "standalone",
        bundle_companions: "list | None" = None,
    ) -> DraftTemplate:
        """Create a new draft template."""
        async with cls._session() as session:
            try:
                draft_template = DraftTemplate(
                    id=template_id,
                    name=name,
                    original_doc_url=original_doc_url,
                    template_doc_url=template_doc_url,
                    template_spec=template_spec,
                    agent_config=agent_config,
                    bundle_role=bundle_role,
                    bundle_companions=bundle_companions,
                )
                session.add(draft_template)
                await session.commit()
                await session.refresh(draft_template)
                logger.info(f"Created draft template: {template_id}")
                return draft_template
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to create draft template {template_id}: {e}")
                raise

    @classmethod
    async def get(cls, template_id: str) -> DraftTemplate | None:
        """Get draft template by ID."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text("SELECT * FROM draft_templates WHERE id = :template_id AND is_active = true"),
                    {"template_id": template_id},
                )
                row = result.fetchone()
                if row:
                    return DraftTemplate(**dict(row._mapping))
                return None
            except Exception as e:
                logger.error(f"Failed to get draft template {template_id}: {e}")
                raise

    @classmethod
    async def list(cls) -> list[DraftTemplate]:
        """List all active draft templates."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text("SELECT * FROM draft_templates WHERE is_active = true ORDER BY created_at DESC")
                )
                rows = result.fetchall()
                return [DraftTemplate(**dict(r._mapping)) for r in rows]
            except Exception as e:
                logger.error(f"Failed to list draft templates: {e}")
                raise

    @classmethod
    async def update(
        cls,
        template_id: str,
        name: str | None = None,
        original_doc_url: str | None = None,
        template_doc_url: str | None = None,
        template_spec: dict | None = None,
        agent_config: dict | None = None,
        clear_agent_config: bool = False,
        bundle_role: str | None = None,
        bundle_companions: "list | None" = None,
        clear_bundle_companions: bool = False,
    ) -> DraftTemplate | None:
        """Update a draft template by ID, applying only the fields that are non-None.

        Pass `clear_agent_config=True` to explicitly write NULL to the
        agent_config column — `agent_config=None` by itself is treated as
        'do not touch'.

        Pass `clear_bundle_companions=True` to explicitly write NULL to
        bundle_companions (e.g. when toggling a template back to standalone).
        `bundle_companions=None` by itself is treated as 'do not touch'.
        """
        async with cls._session() as session:
            try:
                sets = []
                params = {"template_id": template_id}

                if name is not None:
                    sets.append("name = :name")
                    params["name"] = name
                if original_doc_url is not None:
                    sets.append("original_doc_url = :original_doc_url")
                    params["original_doc_url"] = original_doc_url
                if template_doc_url is not None:
                    sets.append("template_doc_url = :template_doc_url")
                    params["template_doc_url"] = template_doc_url
                if template_spec is not None:
                    sets.append("template_spec = :template_spec")
                    params["template_spec"] = json.dumps(template_spec)
                if clear_agent_config:
                    sets.append("agent_config = NULL")
                elif agent_config is not None:
                    sets.append("agent_config = :agent_config")
                    params["agent_config"] = json.dumps(agent_config)
                if bundle_role is not None:
                    sets.append("bundle_role = :bundle_role")
                    params["bundle_role"] = bundle_role
                if clear_bundle_companions:
                    sets.append("bundle_companions = NULL")
                elif bundle_companions is not None:
                    sets.append("bundle_companions = :bundle_companions")
                    params["bundle_companions"] = json.dumps(bundle_companions)

                if not sets:
                    return None

                sets.append("updated_at = now()")
                set_clause = ", ".join(sets)

                await session.execute(
                    text(
                        f"UPDATE draft_templates SET {set_clause} "
                        "WHERE id = :template_id AND is_active = true"
                    ),
                    params,
                )
                await session.commit()

                result = await session.execute(
                    text(
                        "SELECT * FROM draft_templates "
                        "WHERE id = :template_id AND is_active = true"
                    ),
                    {"template_id": template_id},
                )
                row = result.fetchone()
                return DraftTemplate(**dict(row._mapping)) if row else None
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to update draft template {template_id}: {e}")
                raise

    @classmethod
    async def delete(cls, template_id: str) -> bool:
        """Soft-delete draft template by ID."""
        async with cls._session() as session:
            try:
                await session.execute(
                    text("UPDATE draft_templates SET is_active = false WHERE id = :template_id"),
                    {"template_id": template_id},
                )
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to delete draft template {template_id}: {e}")
                raise

    @classmethod
    async def find_parents_referencing_child(
        cls, child_template_id: str,
    ) -> "list[DraftTemplate]":
        """Return active templates whose bundle_companions JSONB references
        the given child template id. Walks both companion shapes:
          - FixedBundleCompanion: top-level `child_template_id`.
          - BranchBundleCompanion: nested `options[].child_template_id`.

        Used by `delete_template_by_id` to surface incoming references
        before a destructive soft-delete.
        """
        async with cls._session() as session:
            try:
                # JSONB containment with `@>` finds rows where bundle_companions
                # contains either a fixed companion pointing at the child OR a
                # branch companion with any option pointing at the child.
                result = await session.execute(
                    text(
                        "SELECT * FROM draft_templates "
                        "WHERE is_active = true "
                        "  AND bundle_companions IS NOT NULL "
                        "  AND ("
                        "    bundle_companions @> CAST(:fixed_match AS jsonb) "
                        "    OR bundle_companions @> CAST(:branch_match AS jsonb)"
                        "  ) "
                        "ORDER BY created_at DESC"
                    ),
                    {
                        "fixed_match": json.dumps([{"child_template_id": child_template_id}]),
                        "branch_match": json.dumps(
                            [{"options": [{"child_template_id": child_template_id}]}]
                        ),
                    },
                )
                rows = result.fetchall()
                return [DraftTemplate(**dict(r._mapping)) for r in rows]
            except Exception as e:
                logger.error(
                    f"Failed to find parents referencing child {child_template_id}: {e}"
                )
                raise

    @classmethod
    async def prune_companion_references_for_child(
        cls, parent_id: str, child_template_id: str,
    ) -> "list[str]":
        """Filter the given child out of a parent's bundle_companions and
        persist the result. Returns the list of companion labels that were
        affected (either fully dropped, or had a branch option removed).

        Rules:
          - FixedBundleCompanion with the target child_template_id → dropped entirely.
          - BranchBundleCompanion: filter `options` to exclude the target.
            If fewer than 2 options remain (BranchBundleCompanion requires
            min_length=2), drop the whole companion. Otherwise keep with
            filtered options.
          - When the filtered list ends up empty (the doomed child was
            this parent's only reason to be a parent), also demote
            `bundle_role` from 'parent' to 'standalone' in the SAME
            UPDATE. Otherwise the parent's role badge in the Studio
            stays "Parent" even though there's nothing to bundle —
            confusing and a state-consistency issue.

        Used only on force-delete from `delete_template_by_id`.
        """
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        "SELECT bundle_companions FROM draft_templates "
                        "WHERE id = :template_id AND is_active = true"
                    ),
                    {"template_id": parent_id},
                )
                row = result.fetchone()
                if row is None or row._mapping["bundle_companions"] is None:
                    return []

                companions = list(row._mapping["bundle_companions"])
                pruned, affected_labels = _filter_companions_for_child(
                    companions, child_template_id,
                )

                if pruned:
                    await session.execute(
                        text(
                            "UPDATE draft_templates "
                            "SET bundle_companions = CAST(:companions AS jsonb), "
                            "    updated_at = NOW() "
                            "WHERE id = :template_id AND is_active = true"
                        ),
                        {
                            "template_id": parent_id,
                            "companions": json.dumps(pruned),
                        },
                    )
                else:
                    # No companions left — demote role to standalone so the
                    # Studio stops showing a misleading "Parent" badge.
                    await session.execute(
                        text(
                            "UPDATE draft_templates "
                            "SET bundle_companions = NULL, "
                            "    bundle_role = 'standalone', "
                            "    updated_at = NOW() "
                            "WHERE id = :template_id AND is_active = true"
                        ),
                        {"template_id": parent_id},
                    )
                await session.commit()
                return affected_labels
            except Exception as e:
                await session.rollback()
                logger.error(
                    f"Failed to prune companion references on parent {parent_id} "
                    f"for child {child_template_id}: {e}"
                )
                raise
