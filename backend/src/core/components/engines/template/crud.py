"""DraftTemplate CRUD — list / update / delete endpoints.

Thin service layer over DraftTemplateRepository that also handles R2
presigned-URL generation for the response DTO. The composer and dry-run
flows live elsewhere (composer.py / dry_run.py); this module is purely
about managing existing DraftTemplate rows.
"""

from fastapi import HTTPException

from src.core.agents.types.bundling import (
    BranchBundleCompanion,
    BundleCompanion,
    ExtractFromDraftSlotConfig,
    FixedBundleCompanion,
    LiteralSlotConfig,
    ParentVariableSlotConfig,
    SlotConfig,
)
from src.core.agents.types.sources import FieldSource
from src.core.agents.types.spec import TemplateVariable
from src.core.common.storage.database import DraftTemplateRepository
from src.core.common.storage.r2 import r2_service

from .schemas import (
    CleanedParentEntry,
    DeleteTemplateConflictDetail,
    DeleteTemplateResponse,
    DraftTemplateResponse,
    ReferencingParent,
)
from .validators import assert_child_only_has_no_user_input


async def _build_template_response(template) -> DraftTemplateResponse:
    original_doc_url = (
        await r2_service.get_presigned_url(template.id, "original.docx", prefix="template")
        if template.original_doc_url else None
    )
    template_doc_url = (
        await r2_service.get_presigned_url(template.id, "template.docx", prefix="template")
        if template.template_doc_url else None
    )
    return DraftTemplateResponse(
        id=template.id,
        name=template.name,
        original_doc_url=original_doc_url,
        template_doc_url=template_doc_url,
        template_spec=template.template_spec,
        agent_config=template.agent_config,
        bundle_role=template.bundle_role or "standalone",
        bundle_companions=template.bundle_companions,
        created_at=str(template.created_at) if template.created_at else None,
        is_active=template.is_active,
    )


async def list_template_responses() -> list[DraftTemplateResponse]:
    """List every active draft template with its presigned R2 URLs."""
    templates = await DraftTemplateRepository.list()
    return [await _build_template_response(t) for t in templates]


async def update_template_name(template_id: str, name: str) -> DraftTemplateResponse:
    """Rename an active draft template; raise 404 if missing or soft-deleted."""
    existing = await DraftTemplateRepository.get(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    updated = await DraftTemplateRepository.update(template_id, name=name)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    return await _build_template_response(updated)


def _is_slot_config_complete(config: SlotConfig) -> bool:
    """`literal` allows empty string; the other two require non-empty payload."""
    if isinstance(config, ParentVariableSlotConfig):
        return bool(config.parent_variable.strip())
    if isinstance(config, ExtractFromDraftSlotConfig):
        return bool(config.extract_instruction.strip())
    if isinstance(config, LiteralSlotConfig):
        return True
    return False  # defensive; pydantic discriminator should make this unreachable


def _slots_required_for_child(child_template_spec: "list[dict] | None") -> list[str]:
    """Return variable names on the child that are `inherit_from_parent` —
    those are the slots a parent companion MUST fill."""
    if not child_template_spec:
        return []
    out: list[str] = []
    for v in child_template_spec:
        if v.get("source") == FieldSource.INHERIT_FROM_PARENT.value:
            name = v.get("template_variable")
            if name:
                out.append(name)
    return out


async def _validate_companion_slots(
    *,
    label: str,
    child_template_id: str,
    slot_configurations: dict[str, SlotConfig],
) -> list[str]:
    """Return human-readable error strings for this companion entry's slots.

    Empty list = OK. Aggregates so the caller can list every problem in a
    single 400 response (instead of failing one slot at a time)."""
    errors: list[str] = []
    child = await DraftTemplateRepository.get(child_template_id)
    if child is None:
        errors.append(
            f"Companion '{label}' references missing child template '{child_template_id}'."
        )
        return errors

    required = _slots_required_for_child(child.template_spec)
    for slot in required:
        config = slot_configurations.get(slot)
        if config is None:
            errors.append(
                f"Companion '{label}' is missing a slot configuration for '{slot}'."
            )
            continue
        if not _is_slot_config_complete(config):
            errors.append(
                f"Companion '{label}': slot '{slot}' ({config.kind}) is incomplete — "
                "fill in the required value."
            )
    return errors


async def _validate_all_companions(
    companions: "list[BundleCompanion]",
) -> list[str]:
    """Walk every Fixed companion and every BranchOption, collecting errors."""
    errors: list[str] = []
    for companion in companions:
        if isinstance(companion, FixedBundleCompanion):
            errors.extend(
                await _validate_companion_slots(
                    label=companion.label,
                    child_template_id=companion.child_template_id,
                    slot_configurations=companion.slot_configurations,
                )
            )
        elif isinstance(companion, BranchBundleCompanion):
            for option in companion.options:
                errors.extend(
                    await _validate_companion_slots(
                        label=f"{companion.label} → {option.label}",
                        child_template_id=option.child_template_id,
                        slot_configurations=option.slot_configurations,
                    )
                )
    return errors


async def update_template_bundling_config(
    template_id: str,
    bundle_role: str,
    bundle_companions: "list[BundleCompanion] | None",
) -> DraftTemplateResponse:
    """Update a template's bundle_role + bundle_companions.

    Phase 1B: child_only / standalone templates must not carry companions.
    parent templates may carry an empty list (default) or a populated one.
    Strict: parent templates with companions must have COMPLETE slot
    configurations for every `inherit_from_parent` variable on every
    referenced child — partial saves are rejected with HTTP 400.
    """
    existing = await DraftTemplateRepository.get(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    if bundle_role in ("standalone", "child_only") and bundle_companions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Templates with bundle_role='{bundle_role}' cannot carry "
                "bundle_companions — only 'parent' templates may attach children."
            ),
        )

    if bundle_role == "child_only" and existing.template_spec:
        spec_models = [TemplateVariable(**v) for v in existing.template_spec]
        assert_child_only_has_no_user_input(template_id, spec_models)

    if bundle_role == "parent" and bundle_companions:
        slot_errors = await _validate_all_companions(bundle_companions)
        if slot_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "BUNDLE_SLOTS_INCOMPLETE",
                    "message": "One or more companions have incomplete slot configurations.",
                    "errors": slot_errors,
                },
            )

    # Coerce Pydantic models → plain dicts at the service-layer boundary so
    # `DraftTemplateRepository.update` can `json.dumps(...)` the payload. We
    # tightened the request schema to `list[BundleCompanion] | None`, which
    # means typed model instances flow in here; the repo stays generic and
    # shouldn't need to know about Pydantic.
    companions_payload: "list[dict] | None" = (
        [c.model_dump() for c in bundle_companions]
        if bundle_companions is not None
        else None
    )

    updated = await DraftTemplateRepository.update(
        template_id,
        bundle_role=bundle_role,
        bundle_companions=companions_payload,
        clear_bundle_companions=(companions_payload is None or companions_payload == []),
    )
    if not updated:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    return await _build_template_response(updated)


def _companion_labels_referencing_child(
    bundle_companions: list | None,
    child_template_id: str,
) -> list[str]:
    """Return labels of companions on this parent that point at the child.

    Mirrors the prune logic in `DraftTemplateRepository.prune_companion_references_for_child`:
    a FixedBundleCompanion matches when its `child_template_id` equals the
    target; a BranchBundleCompanion matches when ANY of its options points
    at the target.
    """
    if not bundle_companions:
        return []
    labels: list[str] = []
    for companion in bundle_companions:
        kind = companion.get("kind")
        label = companion.get("label", "")
        if kind == "fixed":
            if companion.get("child_template_id") == child_template_id:
                labels.append(label)
        elif kind == "branch":
            options = companion.get("options", []) or []
            if any(opt.get("child_template_id") == child_template_id for opt in options):
                labels.append(label)
    return labels


async def delete_template_by_id(
    template_id: str, force: bool = False,
) -> DeleteTemplateResponse:
    """Soft-delete a draft template. Surfaces incoming references from
    other parent templates before the destructive flip.

    - `force=False` (default): if any active parent template's
      bundle_companions reference this template, raise 409 with the list
      of referencing parents so the author can cancel or retry with
      force=True.
    - `force=True`: cascade-clean every referencing parent's
      bundle_companions (removing the doomed child), then soft-delete
      the target. Response carries the `cleaned_parents` list so the
      author has a record of which parents were edited.

    Always raises 404 if the target template is missing or already
    soft-deleted.
    """
    existing = await DraftTemplateRepository.get(template_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    referencing = await DraftTemplateRepository.find_parents_referencing_child(template_id)

    if referencing and not force:
        parents_payload = [
            ReferencingParent(
                template_id=p.id,
                name=p.name,
                companion_labels=_companion_labels_referencing_child(
                    p.bundle_companions, template_id,
                ),
            )
            for p in referencing
        ]
        detail = DeleteTemplateConflictDetail(
            message=(
                f"Template '{existing.name}' is referenced by {len(referencing)} parent "
                f"template(s). Retry with force=true to cascade-clean their "
                f"bundle_companions and delete anyway."
            ),
            referencing_parents=parents_payload,
        )
        raise HTTPException(status_code=409, detail=detail.model_dump())

    cleaned: list[CleanedParentEntry] = []
    if referencing and force:
        for parent in referencing:
            removed_labels = await DraftTemplateRepository.prune_companion_references_for_child(
                parent_id=parent.id, child_template_id=template_id,
            )
            cleaned.append(
                CleanedParentEntry(
                    template_id=parent.id,
                    name=parent.name,
                    removed_companion_labels=removed_labels,
                )
            )

    await DraftTemplateRepository.delete(template_id)
    return DeleteTemplateResponse(success=True, id=template_id, cleaned_parents=cleaned)
