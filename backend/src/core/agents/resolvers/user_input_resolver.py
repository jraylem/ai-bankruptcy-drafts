"""USER_INPUT ResolverStage: pause/resume orchestration for user-picked values.

Runs after the draft agent and system_generated resolver. Handles the four
USER_INPUT-stage field families:

  1. Group dropdowns (GROUP_DROPDOWN_FROM_*) — composite fields where the
     LLM extracts (left, right) pairs from fetched email data; user picks
     one pair and the pick fans out to TWO sibling template variables.
     Pick shape: `GroupDropdownPick { left, right }`.

  2. Recommendation chips (RECO_CHIPS_FROM_*) — single-variable fields where
     the LLM generates up to 3 short text candidates from fetched source
     data; user picks one (optionally edits it), and the final string
     fills ONE template variable. Picks flow through UserInputHealAgent
     before filling. Pick shape: `SingleValuePick { value }`.

  3. Plain dropdowns (DROPDOWN_FROM_*) — single-variable fields where the
     LLM extracts up to 20 option strings matching an author-supplied
     `example_format`; user picks one verbatim, which fills ONE template
     variable. Picks also flow through UserInputHealAgent before filling
     (same grammar-integration pass reco-chips use). Pick shape:
     `SingleValuePick { value }` — same class as reco-chips, since the
     server discriminates behavior by the field's source, not by the
     pick's class.

  4. User-input with supporting docs (USER_INPUT_WITH_SUPPORTING_DOCS) —
     pure user-input form. No pre-pause LLM call. The user supplies a
     free-form text explanation AND uploads supporting documents (PDFs,
     DOCX, TXT/MD, images) pre-uploaded to R2. On resume,
     ExplanationEnhanceAgent reads the user's text in the context of the
     uploaded docs and produces ONE polished paragraph. The result
     bypasses UserInputHealAgent (the enhancement IS the polish). Pick
     shape: `SupportingDocsPick { user_text, file_urls }`.

`apply()` builds pending-envelope descriptors keyed by field.property_name;
the FE renders them and sends back a pick per entry on resume.
`expand_picks()` converts those picks into ResolvedTemplateValues.
`expand_picks` is async because the supporting-docs branch downloads files
from R2 and calls an LLM agent to produce the final value.

The envelope types (PendingGroupDropdown, PendingRecoChips, PendingDropdown,
PendingUserInputWithDocs, GroupDropdownPick, SingleValuePick,
SupportingDocsPick, AwaitingInputResponse) live here so both the dry-run
and draft services can share one contract.
"""

import asyncio
import base64
import logging
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from src.config import settings

from src.core.common.documents.supporting_doc_reader import (
    SupportingDoc,
    read_supporting_doc,
)
from src.core.common.storage.database import (
    ATTORNEYS_SHORT_CODE,
    AttorneyRosterRepository,
)
from src.core.common.storage.r2 import r2_service
from src.core.common.toolbox import ToolBox

from ..utils import query_template
from ..context import FetchedContext
from ..llm.dropdown import DropdownAgent, DropdownParams
from ..llm.explanation_enhance import ExplanationEnhanceAgent
from ..llm.group_dropdown import DropdownOption, GroupDropdownAgent
from ..llm.multi_select_vision import MultiSelectVisionAgent
from ..llm.reco_chips import RecoChipsAgent, RecoChipsParams
from ..utils import fetch_petition_pdf_bytes
from ..types.resolution import ResolvedTemplateValue, ResolverStage
from ..types.sources import (
    DropdownCaseVectorSourceParams,
    DropdownEmailSourceParams,
    DropdownFromConstantsSourceParams,
    GroupDropdownComposite,
    MultiSelectFromCaseVectorSourceParams,
    MultiSelectFromGmailSourceParams,
    RecoChipsCaseVectorSourceParams,
    RecoChipsEmailSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
    UserInputDateSourceParams,
    UserInputPlainTextSourceParams,
    UserInputWithSupportingDocsSourceParams,
)
from ..types.spec import TemplateField, TemplateVariable

# Both multi-select params share the runtime API surface UserInputResolver
# cares about (label, instruction, example_formats, min_picks, max_picks,
# list_joiner, oxford). The vision-fallback branch is gated on the
# case-vector variant only (Gmail has no petition PDF counterpart).
MultiSelectParams = (
    MultiSelectFromCaseVectorSourceParams | MultiSelectFromGmailSourceParams
)

logger = logging.getLogger(__name__)


class PendingGroupDropdown(BaseModel):
    """One awaiting-input descriptor for a group-dropdown composite field."""
    kind: Literal["group_dropdown"] = "group_dropdown"
    group_label: str
    left_variable: str
    left_label: str
    right_variable: str
    right_label: str
    options: list[DropdownOption]


class PendingRecoChips(BaseModel):
    """One awaiting-input descriptor for a reco-chips field.

    The FE renders `chips` as clickable suggestions under `label`; picking
    one pre-fills an editable textfield. The user's final (possibly edited)
    text is sent back as a SingleValuePick.
    """
    kind: Literal["reco_chips"] = "reco_chips"
    label: str
    chips: list[str]


class PendingDropdown(BaseModel):
    """One awaiting-input descriptor for a plain dropdown field.

    The FE renders `options` as a single-select control under `label`; the
    user clicks one, which is sent back verbatim as a SingleValuePick. The
    server heals it before filling the docx.
    """
    kind: Literal["dropdown"] = "dropdown"
    label: str
    options: list[str]


class PendingUserInputWithDocs(BaseModel):
    """One awaiting-input descriptor for a user_input_with_supporting_docs field.

    Pure user-input form: the FE renders a free-text area under `label`
    plus a file picker filtered to `accepted_file_types`. Each uploaded
    file is POSTed to /cases/{case_id}/supporting-docs BEFORE resume; the
    resume pick carries only the R2 keys returned by that endpoint. No
    options or chips are precomputed server-side.
    """
    kind: Literal["user_input_with_docs"] = "user_input_with_docs"
    label: str
    accepted_file_types: list[str]


class PendingDropdownFromConstants(BaseModel):
    """One awaiting-input descriptor for a dropdown_from_constants field.

    Options come from a reserved reference_data list (currently just the
    attorney roster under short_code ATTORNEYS). No pre-pause LLM call —
    options are a direct DB read. Contract matches the other dropdown
    sources (plain `list[str]` of display values, picks come back as
    `SingleValuePick(value=<picked_label>)` verbatim) so the FE can treat
    every dropdown family the same way.
    """
    kind: Literal["dropdown_from_constants"] = "dropdown_from_constants"
    label: str
    options: list[str]


class PendingMultiSelect(BaseModel):
    """One awaiting-input descriptor for a multi_select_from_case_vector field.

    The FE renders `options` as a vertical list of multi-select cards under
    `label` + `instruction`. Each option is a single string (matching one
    of the source's `example_formats`). `min_picks` / `max_picks` drive
    constraint enforcement and live counters in the UI. Picks come back as
    `MultiSelectPick(picked_values=[...])`; the resolved value is the
    Oxford-comma-joined prose string of the picks (e.g. 'A, B, and C')
    ready to fill a docx slot.
    """
    kind: Literal["multi_select"] = "multi_select"
    label: str
    instruction: str | None = None
    options: list[str]
    min_picks: int = 1
    max_picks: int | None = None


class PendingUserInputPlainText(BaseModel):
    """One awaiting-input descriptor for a user_input_plain_text field.

    Lightweight prose form. The FE renders a textarea under `label` with
    `placeholder` as the input hint and `example_output_sentence` as a
    small tone reference shown below the field — the skeleton of what the
    healed output should look like. Picks come back as
    `SingleValuePick(value=<typed_text>)`. The server heals the picked
    text against `example_output_sentence` (kind='example_sentence') so
    the polished prose lands in consistent legal register.
    """
    kind: Literal["user_input_plain_text"] = "user_input_plain_text"
    label: str
    placeholder: str | None = None
    example_output_sentence: str


class PendingUserInputDate(BaseModel):
    """One awaiting-input descriptor for a user_input_date field.

    The FE renders a calendar widget under `label` (with optional
    `placeholder` as a sub-hint). The user picks a date; the FE formats
    the picked ISO date using `format` (strftime) and sends back the
    rendered string as `SingleValuePick(value=<formatted_date>)`. No
    heal pass on the server — the value is already in its final
    docx-ready form.
    """
    kind: Literal["user_input_date"] = "user_input_date"
    label: str
    placeholder: str | None = None
    format: str


PendingUserInput = (
    PendingGroupDropdown
    | PendingRecoChips
    | PendingDropdown
    | PendingUserInputWithDocs
    | PendingDropdownFromConstants
    | PendingUserInputPlainText
    | PendingUserInputDate
    | PendingMultiSelect
)


class GroupDropdownPick(BaseModel):
    """Group-dropdown pick sent back on resume.

    display_value is UI-only and deliberately not part of this shape — the
    server uses only left+right.
    """
    left: str
    right: str


class SingleValuePick(BaseModel):
    """Pick payload for any single-value awaiting-input field (reco-chips or plain dropdown).

    The server discriminates behavior by the field's source (looked up in
    template_fields), not by the pick's class — so the wire shape is the
    same single-value blob regardless of family.

    For reco-chips: the user's final (possibly edited) text; flows into
    UserInputHealAgent then into the variable.
    For dropdowns: one of the options the server sent verbatim; also flows
    through UserInputHealAgent on the server.
    """
    value: str


class MultiSelectPick(BaseModel):
    """Pick payload for multi_select_from_case_vector fields.

    `picked_values` is the user's selection sent back as the picked
    strings themselves. The FE round-trips the strings from
    `PendingMultiSelect.options` so the server doesn't need to remember
    pre-pause state across the pause/resume boundary. Server validates
    min_picks / max_picks and Oxford-comma-joins the picks into a single
    prose string.
    """
    picked_values: list[str] = Field(default_factory=list)


class SupportingDocsPick(BaseModel):
    """Pick payload for user_input_with_supporting_docs fields.

    `user_text` is the author's free-form explanation. `file_urls` are R2
    keys returned by the /cases/{case_id}/supporting-docs upload endpoint
    — the server rejects any URL that doesn't live under that case's
    supporting_docs prefix.
    """
    user_text: str
    file_urls: list[str] = Field(default_factory=list)


UserSelection = GroupDropdownPick | SingleValuePick | SupportingDocsPick | MultiSelectPick


class AwaitingInputResponse(BaseModel):
    """Paused-run response emitted when one or more USER_INPUT fields need the user to pick.

    Returned by execute_dry_run / execute_draft_for_case. Stateless envelope
    — run_id is a correlation UUID (not persisted). template_id / case_id /
    template_spec are echoed so the FE can construct the resume payload
    without having to remember the original request shape. template_spec is
    None for the draft flow (draft always reads its agent_config from the
    DB row and never needs template_spec on resume).

    `bundle_picks` echoes any pre-flight branch picks the FE supplied on
    the initial request so the resumed run schedules the same children.
    None when the parent has no branch companions (or for non-parent
    templates).
    """
    status: Literal["awaiting_input"] = "awaiting_input"
    run_id: str
    template_id: str
    case_id: str
    template_spec: list[TemplateVariable] | None = None
    resolved_values: list[ResolvedTemplateValue]
    pending_inputs: dict[str, PendingUserInput]
    bundle_picks: dict[str, str] | None = None


def _join_oxford(parts: list[str], list_joiner: str, oxford: bool) -> str:
    """Join `parts` with Oxford-comma logic when oxford=True.

    For `oxford=True` and `list_joiner=", "`:
      - 0 items → ""
      - 1 item → "A"
      - 2 items → "A and B"
      - 3+ items → "A, B, and C"

    For `oxford=False`, all items are joined with `list_joiner` literally.
    """
    if not parts:
        return ""
    if not oxford:
        return list_joiner.join(parts)
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return list_joiner.join(parts[:-1]) + f", and {parts[-1]}"


def _supporting_docs_prefix(case_id: str) -> str:
    """Return the canonical R2 key prefix for a case's supporting-docs uploads.

    All file_urls sent in a SupportingDocsPick must start with this prefix
    — prevents callers from steering the enhancement agent at arbitrary R2
    keys.
    """
    return f"cases/{case_id}/supporting_docs/"


def _validate_supporting_doc_urls(
    file_urls: list[str],
    case_id: str,
    errors: list[str],
    key: str,
) -> None:
    expected_prefix = _supporting_docs_prefix(case_id)
    for url in file_urls:
        if not url.startswith(expected_prefix):
            errors.append(
                f"user_picks['{key}'].file_urls contains '{url}' which is not under "
                f"the case's supporting_docs R2 prefix ('{expected_prefix}'); upload "
                f"files via POST /cases/{case_id}/supporting-docs and use the returned URLs."
            )


async def _fetch_constants_dropdown_options(
    fields: list[tuple[str, DropdownFromConstantsSourceParams]],
) -> dict[str, list[str]]:
    """Fetch option lists for every `dropdown_from_constants` field.

    Groups fields by `reference_short_code` so each distinct roster is read
    once, even when multiple fields bind to the same list. Currently the
    only supported code is ATTORNEYS via `AttorneyRosterRepository.list()`;
    anything else logs a warning and emits an empty option list so the
    FE sees an empty dropdown instead of the request failing outright.
    """
    by_code: dict[str, list[str]] = {}
    for name, params in fields:
        by_code.setdefault(params.reference_short_code, []).append(name)

    result: dict[str, list[str]] = {}
    for code, field_names in by_code.items():
        if code == ATTORNEYS_SHORT_CODE:
            roster = await AttorneyRosterRepository.list()
            options = [att.full_name for att in roster]
        else:
            logger.warning(
                "dropdown_from_constants references unsupported short_code '%s'; "
                "emitting empty options. Add a handler in "
                "_fetch_constants_dropdown_options to support new rosters.",
                code,
            )
            options = []
        for name in field_names:
            result[name] = options
    return result


async def _run_supporting_docs_enhancement(
    key: str,
    docs_field: TemplateField,
    pick: "SupportingDocsPick",
    case_id: str,
) -> str:
    """Run the supporting-docs enhancement pipeline for one pick and return the polished paragraph.

    Downloads each file_url from R2, parses each into a SupportingDoc, then
    calls ExplanationEnhanceAgent. Returns `pick.user_text` unchanged on
    download / parse / agent failure (enhancement is best-effort).
    """
    params = docs_field.source_params
    if not isinstance(params, UserInputWithSupportingDocsSourceParams):
        return pick.user_text

    prefix = "cases"
    key_prefix = _supporting_docs_prefix(case_id)
    supporting_docs: list[SupportingDoc] = []

    for url in pick.file_urls:
        # url shape: "cases/{case_id}/supporting_docs/{uuid}.{ext}"
        # r2_service.download_file(template_id, filename, prefix) -> {prefix}/{template_id}/{filename}
        relative = url[len(key_prefix):]  # e.g. "{uuid}.{ext}"
        filename = f"supporting_docs/{relative}"
        try:
            content = await r2_service.download_file(
                template_id=case_id,
                filename=filename,
                prefix=prefix,
            )
        except Exception as e:
            logger.error(
                f"Failed to download supporting doc '{url}' for '{key}': {e}; "
                "skipping this doc"
            )
            continue

        original_filename = Path(relative).name
        try:
            supporting_docs.append(read_supporting_doc(original_filename, content))
        except HTTPException as e:
            logger.error(
                f"Failed to parse supporting doc '{url}' for '{key}': {e.detail}; "
                "skipping this doc"
            )
            continue

    return await ExplanationEnhanceAgent.run(
        variable_name=key,
        label=params.label,
        user_text=pick.user_text,
        supporting_docs=supporting_docs,
    )


def _topological_sort_chained_chip_jobs(
    jobs: list[tuple[str, RecoChipsFromDependentVariablesSourceParams, TemplateField]],
) -> list[tuple[str, RecoChipsFromDependentVariablesSourceParams, TemplateField]]:
    """Order chained chip-from-deps jobs so each runs AFTER its
    `dependent_chip_variables` targets within the same chained set.

    Kahn-style: on each pass place every job whose chained deps are
    already placed; loop until nothing moves. Cycles are caught at
    validate time (`_validate_no_resolution_cycles`), so any leftover
    after a stuck pass is appended in declaration order as a safety net.
    """
    if not jobs:
        return []
    chained_names = {name for name, _, _ in jobs}
    remaining = {name: (name, params, field) for name, params, field in jobs}
    ordered: list[tuple[str, RecoChipsFromDependentVariablesSourceParams, TemplateField]] = []
    while remaining:
        progressed = False
        for name in list(remaining.keys()):
            _, params, _ = remaining[name]
            unmet_chained_deps = [
                d for d in params.dependent_chip_variables
                if d in remaining and d != name and d in chained_names
            ]
            if not unmet_chained_deps:
                ordered.append(remaining.pop(name))
                progressed = True
        if not progressed:
            # Cycle slipped past validate (should be unreachable). Append
            # rest in declaration order.
            for name, _, _ in jobs:
                if name in remaining:
                    ordered.append(remaining.pop(name))
            break
    return ordered


class UserInputResolver:
    """Resolve USER_INPUT-stage fields by pausing the pipeline for user picks across all families (group dropdowns, reco-chips, plain dropdowns, supporting-docs)."""

    stage = ResolverStage.USER_INPUT

    @classmethod
    async def apply(
        cls,
        template_fields: list[TemplateField],
        fetched_context: list[FetchedContext],
        resolved_by_name: dict[str, ResolvedTemplateValue] | None = None,
        case_file_collection: str | None = None,
        petition_pdf_url: str | None = None,
    ) -> dict[str, PendingUserInput]:
        """Produce pending-input descriptors for every USER_INPUT field whose raw context was fetched.

        Dispatches all LLM calls (group-dropdown, reco-chips, and
        plain-dropdown) in parallel via one asyncio.gather so total latency
        is max(call_times) rather than sum(call_times). Supporting-docs
        fields emit their envelope directly without any pre-pause LLM call.

        `resolved_by_name` carries Pass 1 + Pass 2 LLM_DRAFT + system
        values so reco_chips_from_dependent_variables can compose its
        source material here (where ALL upstream values are resolved),
        not at fetch-handler time (where Pass 2 LLM_DRAFT values are
        still pending). Pass `None` for back-compat callers — chip-from-
        deps composition will then be empty.

        Returns {field.property_name: PendingUserInput}. Fields whose
        generation / extraction returned empty are skipped silently — the
        FE sees no pending entry for them, and the pipeline treats them as
        resolved-to-nothing for this run.
        """
        resolved_by_name = resolved_by_name or {}
        context_by_name = {ctx.property_name: ctx for ctx in fetched_context}

        group_dropdown_jobs: list[tuple[str, GroupDropdownComposite, FetchedContext]] = []
        reco_chips_jobs: list[tuple[str, RecoChipsParams, FetchedContext]] = []
        # chip-from-deps jobs are deferred — their source material gets
        # composed at run-time so case_vector_queries can fire (async) and
        # chained jobs can read sibling chips.
        chip_from_deps_independent_jobs: list[
            tuple[str, RecoChipsFromDependentVariablesSourceParams, TemplateField]
        ] = []
        chip_from_deps_chained_jobs: list[
            tuple[str, RecoChipsFromDependentVariablesSourceParams, TemplateField]
        ] = []
        dropdown_jobs: list[tuple[str, DropdownParams, FetchedContext]] = []
        multi_select_jobs: list[
            tuple[str, MultiSelectParams, FetchedContext]
        ] = []
        supporting_docs_fields: list[tuple[str, UserInputWithSupportingDocsSourceParams]] = []
        constants_dropdown_fields: list[tuple[str, DropdownFromConstantsSourceParams]] = []
        plain_text_fields: list[tuple[str, UserInputPlainTextSourceParams]] = []
        date_fields: list[tuple[str, UserInputDateSourceParams]] = []

        for field in template_fields:
            if field.stage != ResolverStage.USER_INPUT:
                continue
            params = field.source_params
            if isinstance(params, UserInputWithSupportingDocsSourceParams):
                # Pure form — no fetched context, no pre-pause LLM call.
                supporting_docs_fields.append((field.property_name, params))
                continue
            if isinstance(params, UserInputPlainTextSourceParams):
                # Pure prose form — same shape as supporting_docs but no file picker.
                plain_text_fields.append((field.property_name, params))
                continue
            if isinstance(params, UserInputDateSourceParams):
                # Calendar form — no LLM call, no heal pass; FE picks a
                # date, formats client-side, sends formatted string.
                date_fields.append((field.property_name, params))
                continue
            if isinstance(params, DropdownFromConstantsSourceParams):
                # Constants-backed list — no LLM call, options come from a DB read at pause time.
                constants_dropdown_fields.append((field.property_name, params))
                continue
            fetched = context_by_name.get(field.property_name)
            if fetched is None or fetched.raw_result is None:
                continue
            if isinstance(params, GroupDropdownComposite):
                group_dropdown_jobs.append((field.property_name, params, fetched))
            elif isinstance(params, RecoChipsFromDependentVariablesSourceParams):
                # Defer composition + agent call so case_vector_queries
                # (async ToolBox calls) and chip-to-chip alignment can run
                # at execution time. Independent jobs go into the parallel
                # gather; chained jobs run sequentially in topological order
                # afterwards.
                if params.dependent_chip_variables:
                    chip_from_deps_chained_jobs.append((field.property_name, params, field))
                else:
                    chip_from_deps_independent_jobs.append((field.property_name, params, field))
            elif isinstance(params, (
                RecoChipsEmailSourceParams,
                RecoChipsCaseVectorSourceParams,
            )):
                reco_chips_jobs.append((field.property_name, params, fetched))
            elif isinstance(params, (DropdownEmailSourceParams, DropdownCaseVectorSourceParams)):
                dropdown_jobs.append((field.property_name, params, fetched))
            elif isinstance(params, (MultiSelectFromCaseVectorSourceParams, MultiSelectFromGmailSourceParams)):
                multi_select_jobs.append((field.property_name, params, fetched))
            else:
                logger.warning(
                    f"USER_INPUT field '{field.property_name}' has unsupported "
                    f"source_params ({type(params).__name__}); skipping."
                )

        if (
            not group_dropdown_jobs
            and not reco_chips_jobs
            and not chip_from_deps_independent_jobs
            and not chip_from_deps_chained_jobs
            and not dropdown_jobs
            and not multi_select_jobs
            and not supporting_docs_fields
            and not constants_dropdown_fields
            and not plain_text_fields
            and not date_fields
        ):
            return {}

        group_dropdown_coros = [
            GroupDropdownAgent.run(name, params, fetched)
            for name, params, fetched in group_dropdown_jobs
        ]
        reco_chips_coros = [
            RecoChipsAgent.run(name, params, fetched)
            for name, params, fetched in reco_chips_jobs
        ]
        independent_chip_from_deps_coros = [
            cls._run_chip_from_deps(
                name=name,
                params=params,
                field=field,
                resolved_by_name=resolved_by_name,
                case_file_collection=case_file_collection,
                chips_so_far={},
            )
            for name, params, field in chip_from_deps_independent_jobs
        ]
        dropdown_coros = [
            DropdownAgent.run(name, params, fetched)
            for name, params, fetched in dropdown_jobs
        ]
        multi_select_coros = [
            DropdownAgent.run(name, params, fetched)
            for name, params, fetched in multi_select_jobs
        ]
        all_results = await asyncio.gather(
            *group_dropdown_coros,
            *reco_chips_coros,
            *independent_chip_from_deps_coros,
            *dropdown_coros,
            *multi_select_coros,
        )
        i = 0
        group_dropdown_results = all_results[i : i + len(group_dropdown_jobs)]
        i += len(group_dropdown_jobs)
        reco_chips_results = all_results[i : i + len(reco_chips_jobs)]
        i += len(reco_chips_jobs)
        independent_chip_from_deps_results = all_results[
            i : i + len(chip_from_deps_independent_jobs)
        ]
        i += len(chip_from_deps_independent_jobs)
        # DropdownAgent now returns _ExtractedOptions (options + completeness).
        # Split into parallel lists so downstream loops keep their existing
        # "options-only" shape and the completeness signal feeds the
        # vision-fallback gate.
        dropdown_extractions = all_results[i : i + len(dropdown_jobs)]
        i += len(dropdown_jobs)
        multi_select_extractions = all_results[i : i + len(multi_select_jobs)]
        dropdown_results: list[list[str]] = [r.options for r in dropdown_extractions]
        dropdown_completeness: list[str] = [r.completeness for r in dropdown_extractions]
        multi_select_results: list[list[str]] = [r.options for r in multi_select_extractions]
        multi_select_completeness: list[str] = [r.completeness for r in multi_select_extractions]

        # Build chips_so_far from independent chip-from-deps results so
        # chained jobs can reference their sibling chips for alignment.
        chips_so_far: dict[str, list[str]] = {
            name: (chips or [])
            for (name, _, _), chips in zip(
                chip_from_deps_independent_jobs, independent_chip_from_deps_results
            )
        }

        # Topologically sort chained jobs and run sequentially. Cycle
        # detection happens at validate time (`_validate_no_resolution_cycles`),
        # so we can trust the ordering here.
        ordered_chained = _topological_sort_chained_chip_jobs(chip_from_deps_chained_jobs)
        chained_chip_results: dict[str, list[str]] = {}
        for name, params, field in ordered_chained:
            chips = await cls._run_chip_from_deps(
                name=name,
                params=params,
                field=field,
                resolved_by_name=resolved_by_name,
                case_file_collection=case_file_collection,
                chips_so_far=chips_so_far,
            )
            chained_chip_results[name] = chips
            chips_so_far[name] = chips or []

        pending: dict[str, PendingUserInput] = {}

        for (name, params, _), options in zip(group_dropdown_jobs, group_dropdown_results):
            if not options:
                continue
            for opt in options:
                opt.display_value = f"{opt.left} - {opt.right}"
            pending[name] = PendingGroupDropdown(
                group_label=params.group_label,
                left_variable=params.left_variable,
                left_label=params.left_label,
                right_variable=params.right_variable,
                right_label=params.right_label,
                options=options,
            )

        for (name, params, _), chips in zip(reco_chips_jobs, reco_chips_results):
            if not chips:
                continue
            pending[name] = PendingRecoChips(
                label=params.label,
                chips=chips,
            )

        for (name, params, _), chips in zip(
            chip_from_deps_independent_jobs, independent_chip_from_deps_results
        ):
            if not chips:
                continue
            pending[name] = PendingRecoChips(
                label=params.label,
                chips=chips,
            )

        for name, params, _ in ordered_chained:
            chips = chained_chip_results.get(name) or []
            if not chips:
                continue
            pending[name] = PendingRecoChips(
                label=params.label,
                chips=chips,
            )

        for (name, params, _), options in zip(dropdown_jobs, dropdown_results):
            if not options:
                continue
            pending[name] = PendingDropdown(
                label=params.label,
                options=options,
            )

        # Vision fallback: re-extract via claude-opus-4-6 reading the
        # petition PDF directly when EITHER:
        #   - DropdownAgent returned fewer options than `min_picks`, OR
        #   - DropdownAgent self-reported `completeness != "full"` (saw
        #     fragmentary chunks like Schedule C exemption pages without
        #     the source Schedule A/B itemized rows).
        # The completeness gate catches today's bug: 2 options came back
        # (passes `min_picks=1`) but the LLM saw only exemption-page
        # chunks. Vision-extracted options are appended to the
        # DropdownAgent's baseline (de-duped case-insensitively).
        # Best-effort — failures log a warning and fall through.
        multi_select_final_options: list[list[str]] = [
            list(options or []) for options in multi_select_results
        ]
        vision_enabled = (
            getattr(settings, "CASE_VECTOR_VISION_FALLBACK_ENABLED", True)
            and bool(petition_pdf_url)
        )
        cached_pdf_b64: str | None = None
        pdf_fetch_attempted = False
        if vision_enabled:
            for idx, (name, params, _) in enumerate(multi_select_jobs):
                # Gmail multi-select has no petition-PDF counterpart — vision
                # fallback is meaningless. Only case-vector multi-selects
                # (whose options live in the petition pages) get vision.
                if not isinstance(params, MultiSelectFromCaseVectorSourceParams):
                    continue
                baseline = multi_select_final_options[idx]
                completeness = multi_select_completeness[idx]
                if len(baseline) >= params.min_picks and completeness == "full":
                    continue
                if not pdf_fetch_attempted:
                    pdf_fetch_attempted = True
                    pdf_bytes = await fetch_petition_pdf_bytes(petition_pdf_url)
                    if pdf_bytes:
                        cached_pdf_b64 = base64.b64encode(pdf_bytes).decode()
                if not cached_pdf_b64:
                    break
                vision_result = await MultiSelectVisionAgent.run(
                    petition_pdf_b64=cached_pdf_b64,
                    params=params,
                    variable_name=name,
                    baseline_options=list(baseline),
                )
                if not vision_result.options and not vision_result.superseded_baseline:
                    continue
                # Drop any baseline strings vision flagged as superseded —
                # vision returns a richer-shaped version of the same item
                # (e.g. baseline 'Mercedes G-Wagon' → vision '2018 Mercedes
                # G-Wagon - VIN# X' which fully matches example_formats).
                # The baseline entry must be removed so the FE picker shows
                # only the better-shaped version.
                if vision_result.superseded_baseline:
                    superseded_lower = {
                        s.strip().lower()
                        for s in vision_result.superseded_baseline
                        if s.strip()
                    }
                    filtered = [
                        o for o in baseline
                        if o.strip().lower() not in superseded_lower
                    ]
                    dropped = len(baseline) - len(filtered)
                    if dropped:
                        logger.info(
                            "MultiSelectVisionAgent[%s] dropped %d baseline "
                            "option(s) superseded by richer-shaped vision "
                            "extractions: %s",
                            name, dropped, vision_result.superseded_baseline,
                        )
                    multi_select_final_options[idx] = filtered
                    baseline = filtered
                # Safety-net string-equality dedup: vision's instruction
                # already prevents duplicates, but if the LLM ignores the
                # rule we drop exact case-insensitive matches.
                seen_lower = {opt.strip().lower() for opt in baseline if opt.strip()}
                for vo in vision_result.options:
                    cleaned = vo.strip()
                    if not cleaned or cleaned.lower() in seen_lower:
                        continue
                    seen_lower.add(cleaned.lower())
                    baseline.append(cleaned)

        for (name, params, _), options in zip(multi_select_jobs, multi_select_final_options):
            # Always emit the envelope, even when extraction returned [].
            # The FE shows the empty-state with skip-or-cancel affordance and
            # min_picks/max_picks constraint copy.
            pending[name] = PendingMultiSelect(
                label=params.label,
                instruction=params.instruction,
                options=list(options or []),
                min_picks=params.min_picks,
                max_picks=params.max_picks,
            )

        for name, params in supporting_docs_fields:
            pending[name] = PendingUserInputWithDocs(
                label=params.label,
                accepted_file_types=list(params.accepted_file_types),
            )

        for name, params in plain_text_fields:
            pending[name] = PendingUserInputPlainText(
                label=params.label,
                placeholder=params.placeholder,
                example_output_sentence=params.example_output_sentence,
            )

        for name, params in date_fields:
            pending[name] = PendingUserInputDate(
                label=params.label,
                placeholder=params.placeholder,
                format=params.format,
            )

        if constants_dropdown_fields:
            options_by_field = await _fetch_constants_dropdown_options(
                constants_dropdown_fields
            )
            for name, params in constants_dropdown_fields:
                pending[name] = PendingDropdownFromConstants(
                    label=params.label,
                    options=options_by_field.get(name, []),
                )

        return pending

    @classmethod
    async def _run_chip_from_deps(
        cls,
        name: str,
        params: RecoChipsFromDependentVariablesSourceParams,
        field: TemplateField,
        resolved_by_name: dict[str, ResolvedTemplateValue],
        case_file_collection: str | None,
        chips_so_far: dict[str, list[str]],
    ) -> list[str]:
        """Compose a chip-from-deps job's source material and call RecoChipsAgent.

        The composed dict carries (in order):
          - dependent_variables: resolved values keyed by variable name.
          - case_vector_queries: each retrieval's results keyed by `__cv__:{label}`.
          - dependent_chip_variables: each sibling's chip array keyed by
            `__chips__:{name}` (only available for chained jobs).

        Skips the agent call entirely when no context source produced
        anything — better to return [] than ask the LLM to chip from
        nothing. Returns the agent's chip list (possibly empty)."""
        composed: dict[str, str] = {}
        for var_name in params.dependent_variables:
            rv = resolved_by_name.get(var_name)
            if rv is None:
                continue
            value = (rv.value or "").strip()
            if not value:
                continue
            composed[var_name] = value

        if params.case_vector_queries and case_file_collection:
            for entry in params.case_vector_queries:
                substituted = query_template.substitute(entry.text_query, resolved_by_name) or ""
                substituted = substituted.strip()
                if not substituted:
                    continue
                try:
                    result = await ToolBox.query_case_specific(
                        collection_name=case_file_collection,
                        query=substituted,
                        k=5,
                    )
                except Exception as e:
                    logger.warning(
                        f"case_vector_queries fetch failed for '{entry.label}' "
                        f"on '{name}': {e}"
                    )
                    continue
                if not result:
                    continue
                composed[f"__cv__:{entry.label}"] = repr(result)

        for sibling_name in params.dependent_chip_variables:
            sibling_chips = chips_so_far.get(sibling_name)
            if not sibling_chips:
                continue
            composed[f"__chips__:{sibling_name}"] = "\n".join(
                f"- {c}" for c in sibling_chips
            )

        if not composed:
            return []

        if params.instruction:
            composed["__instruction__"] = params.instruction

        fetched = FetchedContext(
            property_name=name,
            source=field.source,
            raw_result=composed,
            instruction=field.instruction,
        )
        return await RecoChipsAgent.run(name, params, fetched)

    @staticmethod
    async def expand_picks(
        template_fields: list[TemplateField],
        resolved_values: list[ResolvedTemplateValue],
        user_picks: dict[str, UserSelection],
        case_id: str,
        resource_key: str | None = None,
    ) -> list[ResolvedTemplateValue]:
        """Validate user_picks against USER_INPUT fields and expand each pick into ResolvedTemplateValue(s).

          - Group-dropdown pick → TWO values (left_variable, right_variable).
          - Reco-chips pick → ONE value (field.property_name).
          - Plain-dropdown pick → ONE value (field.property_name).
          - Supporting-docs pick → ONE value; server downloads each file_url
            from R2, parses into SupportingDoc blocks, and calls
            ExplanationEnhanceAgent to produce the final paragraph.

        Async because the supporting-docs branch performs R2 downloads and
        LLM calls. Multiple supporting-docs fields are resolved in parallel
        via asyncio.gather. Raises 400 on mismatches: unknown pick keys,
        missing picks for pending USER_INPUT fields, target variables that
        are already resolved, or file_urls outside the case's
        supporting_docs R2 prefix.
        """
        group_dropdown_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT and isinstance(f.source_params, GroupDropdownComposite)
        }
        reco_chip_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT
            and isinstance(
                f.source_params,
                (
                    RecoChipsEmailSourceParams,
                    RecoChipsCaseVectorSourceParams,
                    RecoChipsFromDependentVariablesSourceParams,
                ),
            )
        }
        dropdown_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT
            and isinstance(f.source_params, (DropdownEmailSourceParams, DropdownCaseVectorSourceParams))
        }
        docs_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT
            and isinstance(f.source_params, UserInputWithSupportingDocsSourceParams)
        }
        constants_dropdown_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT
            and isinstance(f.source_params, DropdownFromConstantsSourceParams)
        }
        plain_text_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT
            and isinstance(f.source_params, UserInputPlainTextSourceParams)
        }
        date_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT
            and isinstance(f.source_params, UserInputDateSourceParams)
        }
        multi_select_fields = {
            f.property_name: f
            for f in template_fields
            if f.stage == ResolverStage.USER_INPUT
            and isinstance(
                f.source_params,
                (MultiSelectFromCaseVectorSourceParams, MultiSelectFromGmailSourceParams),
            )
        }
        user_input_keys = (
            set(group_dropdown_fields)
            | set(reco_chip_fields)
            | set(dropdown_fields)
            | set(docs_fields)
            | set(constants_dropdown_fields)
            | set(plain_text_fields)
            | set(date_fields)
            | set(multi_select_fields)
        )

        errors: list[str] = []

        unknown_keys = sorted(set(user_picks) - user_input_keys)
        if unknown_keys:
            errors.append(
                f"user_picks contains keys that are not USER_INPUT fields: "
                f"{', '.join(unknown_keys)}"
            )
        missing_keys = sorted(user_input_keys - set(user_picks))
        if missing_keys:
            errors.append(
                f"user_picks missing entries for pending user-input fields: "
                f"{', '.join(missing_keys)}"
            )

        already_resolved = {rv.property_name for rv in resolved_values}
        expanded: list[ResolvedTemplateValue] = []
        docs_jobs: list[tuple[str, TemplateField, SupportingDocsPick]] = []

        for key, pick in user_picks.items():
            group_field = group_dropdown_fields.get(key)
            if group_field is not None:
                if not isinstance(pick, GroupDropdownPick):
                    errors.append(
                        f"user_picks['{key}'] must be a GroupDropdownPick (with left/right) for group-dropdown field"
                    )
                    continue
                params = group_field.source_params
                if not isinstance(params, GroupDropdownComposite):
                    continue
                if params.left_variable in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{params.left_variable}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                if params.right_variable in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{params.right_variable}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                reasoning = (
                    f"User picked from '{key}' dropdown "
                    f"(left: '{pick.left}', right: '{pick.right}')."
                )
                expanded.append(ResolvedTemplateValue.high_confidence(
                    params.left_variable, pick.left, reasoning,
                ))
                expanded.append(ResolvedTemplateValue.high_confidence(
                    params.right_variable, pick.right, reasoning,
                ))
                continue

            reco_field = reco_chip_fields.get(key)
            if reco_field is not None:
                if not isinstance(pick, SingleValuePick):
                    errors.append(
                        f"user_picks['{key}'] must be a single-value pick (with `value`) for reco-chips field"
                    )
                    continue
                if reco_field.property_name in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{reco_field.property_name}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                    continue
                reasoning = f"User selected from '{key}' reco-chips."
                expanded.append(ResolvedTemplateValue.high_confidence(
                    reco_field.property_name, pick.value, reasoning,
                ))
                continue

            dropdown_field = dropdown_fields.get(key)
            if dropdown_field is not None:
                if not isinstance(pick, SingleValuePick):
                    errors.append(
                        f"user_picks['{key}'] must be a single-value pick (with `value`) for dropdown field"
                    )
                    continue
                if dropdown_field.property_name in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{dropdown_field.property_name}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                    continue
                reasoning = f"User picked from '{key}' dropdown."
                expanded.append(ResolvedTemplateValue.high_confidence(
                    dropdown_field.property_name, pick.value, reasoning,
                ))
                continue

            constants_field = constants_dropdown_fields.get(key)
            if constants_field is not None:
                if not isinstance(pick, SingleValuePick):
                    errors.append(
                        f"user_picks['{key}'] must be a single-value pick (with `value`) for dropdown_from_constants field"
                    )
                    continue
                if constants_field.property_name in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{constants_field.property_name}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                    continue
                params = constants_field.source_params
                short_code = (
                    params.reference_short_code
                    if isinstance(params, DropdownFromConstantsSourceParams)
                    else "?"
                )
                reasoning = f"User picked from '{key}' ({short_code} roster)."
                expanded.append(ResolvedTemplateValue.high_confidence(
                    constants_field.property_name, pick.value, reasoning,
                ))
                continue

            plain_text_field = plain_text_fields.get(key)
            if plain_text_field is not None:
                if not isinstance(pick, SingleValuePick):
                    errors.append(
                        f"user_picks['{key}'] must be a single-value pick (with `value`) for user_input_plain_text field"
                    )
                    continue
                if plain_text_field.property_name in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{plain_text_field.property_name}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                    continue
                reasoning = f"User typed value for '{key}' (user_input_plain_text)."
                expanded.append(ResolvedTemplateValue.high_confidence(
                    plain_text_field.property_name, pick.value, reasoning,
                ))
                continue

            date_field = date_fields.get(key)
            if date_field is not None:
                if not isinstance(pick, SingleValuePick):
                    errors.append(
                        f"user_picks['{key}'] must be a single-value pick (with `value`) for user_input_date field"
                    )
                    continue
                if date_field.property_name in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{date_field.property_name}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                    continue
                reasoning = f"User picked date for '{key}' (user_input_date)."
                expanded.append(ResolvedTemplateValue.high_confidence(
                    date_field.property_name, pick.value, reasoning,
                ))
                continue

            multi_select_field = multi_select_fields.get(key)
            if multi_select_field is not None:
                if not isinstance(pick, MultiSelectPick):
                    errors.append(
                        f"user_picks['{key}'] must be a MultiSelectPick (with `picked_values`) for multi_select field"
                    )
                    continue
                if multi_select_field.property_name in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{multi_select_field.property_name}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                    continue
                params = multi_select_field.source_params
                if not isinstance(
                    params,
                    (MultiSelectFromCaseVectorSourceParams, MultiSelectFromGmailSourceParams),
                ):
                    continue
                # Normalize: enforce strings, drop empties, dedupe case-insensitively
                # while preserving first-seen order.
                normalized: list[str] = []
                seen_lower: set[str] = set()
                pick_shape_error = False
                for idx, v in enumerate(pick.picked_values):
                    if not isinstance(v, str):
                        errors.append(
                            f"user_picks['{key}'].picked_values[{idx}] must be a string; got {type(v).__name__}"
                        )
                        pick_shape_error = True
                        break
                    cleaned = v.strip()
                    if not cleaned:
                        continue
                    if cleaned.lower() in seen_lower:
                        continue
                    seen_lower.add(cleaned.lower())
                    normalized.append(cleaned)
                if pick_shape_error:
                    continue
                if len(normalized) < params.min_picks:
                    errors.append(
                        f"user_picks['{key}'] requires at least {params.min_picks} pick(s); got {len(normalized)}"
                    )
                    continue
                if params.max_picks is not None and len(normalized) > params.max_picks:
                    errors.append(
                        f"user_picks['{key}'] allows at most {params.max_picks} pick(s); got {len(normalized)}"
                    )
                    continue
                joined_value = _join_oxford(normalized, params.list_joiner, params.oxford)
                reasoning = (
                    f"User picked {len(normalized)} option(s) from '{key}' multi-select; "
                    f"joined into prose."
                )
                expanded.append(ResolvedTemplateValue.high_confidence(
                    multi_select_field.property_name,
                    joined_value,
                    reasoning,
                ))
                continue

            docs_field = docs_fields.get(key)
            if docs_field is not None:
                if not isinstance(pick, SupportingDocsPick):
                    errors.append(
                        f"user_picks['{key}'] must be a SupportingDocsPick (with `user_text` + `file_urls`) for user_input_with_supporting_docs field"
                    )
                    continue
                if docs_field.property_name in already_resolved:
                    errors.append(
                        f"resolved_values already contains '{docs_field.property_name}'; "
                        f"expected it to be provided via user_picks, not twice"
                    )
                    continue
                # Supporting-doc URLs were written with the case's R2 resource
                # key (legacy slug for migrated cases, sanitized case_number
                # for new filed cases). After the Phase 1 UUID rewrite case_id
                # is a UUID — use resource_key for path construction. Falls
                # back to case_id for backwards compat with callers that
                # haven't been updated.
                rk = resource_key or case_id
                _validate_supporting_doc_urls(pick.file_urls, rk, errors, key)
                docs_jobs.append((key, docs_field, pick))

        if errors:
            raise HTTPException(status_code=400, detail={"user_pick_errors": errors})

        if docs_jobs:
            rk = resource_key or case_id
            enhanced_values = await asyncio.gather(
                *(
                    _run_supporting_docs_enhancement(key, docs_field, pick, rk)
                    for key, docs_field, pick in docs_jobs
                )
            )
            for (key, docs_field, _), enhanced in zip(docs_jobs, enhanced_values):
                reasoning = f"User-supplied explanation corroborated from supporting docs for '{key}'."
                expanded.append(ResolvedTemplateValue.high_confidence(
                    docs_field.property_name, enhanced, reasoning,
                ))

        return expanded
