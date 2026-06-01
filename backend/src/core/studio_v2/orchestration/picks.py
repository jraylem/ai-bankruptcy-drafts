"""expand_picks_v2 — convert user picks into resolved values.

For each `(template_variable, UserSelectionV2)` pick:

| Pick type            | Resolved row                                                                  |
|----------------------|-------------------------------------------------------------------------------|
| SingleValuePickV2    | `value=pick.value`, `raw_context=envelope.raw_contexts[i]` (matched by display)|
| MultiSelectPickV2    | `value=oxford_comma_join(picks)`, `raw_context="<a>\\n---\\n<b>\\n---\\n..."` |
| SupportingDocsPickV2 | `value=ExplanationEnhanceAgentV2(user_text, downloaded_docs)` (LLM polish)    |

raw_context matching uses the original `PendingUserInputV2` envelope
the FE sent back — we look up the option in `envelope.options` / `chips`
and forward the matching `envelope.raw_contexts[i]`. This is the
load-bearing invariant: derived children read `raw_context`, not the
cleaned display string.

`with_docs` path is async: downloads every `file_url` from R2,
parses each into a `SupportingDoc` variant via v1's
`read_supporting_doc` helper, then runs `ExplanationEnhanceAgentV2`
to polish. Soft failure: agent returns raw text on LLM/download
failure so the pipeline keeps going.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import HTTPException

from src.core.common.documents.supporting_doc_reader import (
    SupportingDoc,
    read_supporting_doc,
)
from src.core.common.storage.r2 import r2_service

from ..agents.explanation_enhance import ExplanationEnhanceAgentV2
from ..types.fields import TemplateFieldV2
from ..types.pending import (
    PendingAttorneyPickV2,
    PendingChipV2,
    PendingDropdownV2,
    PendingMultiSelectV2,
    PendingUserInputV2,
)
from ..types.picks import (
    MultiSelectPickV2,
    SingleValuePickV2,
    SupportingDocsPickV2,
    UserSelectionV2,
)
from ..types.resolution import ResolvedTemplateValueV2
from ..types.wizard_sources import AuthorInputKind, SourceKind

logger = logging.getLogger(__name__)


def _supporting_docs_prefix(resource_key: str) -> str:
    """R2 key prefix for a case's supporting-docs uploads. Every
    file_url sent in a SupportingDocsPickV2 must start with this
    prefix — security: prevents callers from steering the enhancement
    agent at arbitrary R2 keys.
    """
    return f"cases/{resource_key}/supporting_docs/"


async def expand_picks_v2(
    *,
    template_fields: list[TemplateFieldV2],
    user_picks: dict[str, UserSelectionV2],
    pending_inputs: dict[str, PendingUserInputV2] | None = None,
    resource_key: str | None = None,
) -> list[ResolvedTemplateValueV2]:
    """Convert every pick into a `ResolvedTemplateValueV2`.

    Picks for fields not in `template_fields` are skipped silently
    (defensive — orchestrator already validates).

    `pending_inputs` carries the BE's previous-call envelopes so the
    helper can look up per-option `raw_context` for dropdown / chip /
    multi_select picks. When `pending_inputs` is `None` or doesn't have
    the relevant envelope, the resolved row's `raw_context` falls back
    to empty — derived children then use `value` instead.

    `resource_key` is required for `SupportingDocsPickV2` picks (file_urls
    are validated against the case's R2 prefix + downloaded from
    `cases/{resource_key}/supporting_docs/`). Pass
    `case_resource_key(case)` from
    `src/core/components/cases/identity.py` — for legacy migrated cases
    this returns `case.legacy_id` (the pre-UUID sanitized slug, e.g.
    "26_10700") which is where v1's case-level upload endpoint actually
    writes files. Passing raw `case.id` would miss every legacy upload.
    When None, with_docs picks fall through to a low-confidence row
    with the user's raw text.
    """
    fields_by_name = {f.template_variable: f for f in template_fields}
    pending = pending_inputs or {}
    out: list[ResolvedTemplateValueV2] = []

    for name, pick in user_picks.items():
        field = fields_by_name.get(name)
        if field is None:
            logger.warning(
                "expand_picks_v2: pick for unknown variable '%s' — ignored",
                name,
            )
            continue
        envelope = pending.get(name)
        row = await _expand_one(
            template_variable=name,
            field=field,
            pick=pick,
            envelope=envelope,
            resource_key=resource_key,
        )
        if row is not None:
            out.append(row)

    return out


async def _expand_one(
    *,
    template_variable: str,
    field: TemplateFieldV2,
    pick: UserSelectionV2,
    envelope: PendingUserInputV2 | None,
    resource_key: str | None,
) -> ResolvedTemplateValueV2 | None:
    """Per-pick conversion."""
    if isinstance(pick, MultiSelectPickV2):
        return _expand_multi_select(template_variable, pick, envelope)
    if isinstance(pick, SupportingDocsPickV2):
        return await _expand_supporting_docs(
            template_variable=template_variable,
            field=field,
            pick=pick,
            resource_key=resource_key,
        )
    if isinstance(pick, SingleValuePickV2):
        return _expand_single_value(template_variable, pick, envelope)
    logger.warning(
        "expand_picks_v2: unknown pick type for '%s' (%s) — ignored",
        template_variable, type(pick).__name__,
    )
    return None


def _expand_single_value(
    template_variable: str,
    pick: SingleValuePickV2,
    envelope: PendingUserInputV2 | None,
) -> ResolvedTemplateValueV2:
    """SingleValuePickV2 → resolved row. Looks up the pick's display
    string in the envelope's options/chips to find the matching
    raw_context. Falls back to empty raw_context when the envelope
    isn't a dropdown/chip kind (e.g. for author_text picks).

    Attorney picks are a special case: the FE sends the attorney's
    `id` (UUID) as the pick value but the rendered docx needs the
    attorney's full name. We map id → display_name via the envelope's
    options roster before constructing the resolved row.
    """
    if isinstance(envelope, PendingAttorneyPickV2):
        display = _attorney_display_for_id(envelope, pick.value)
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value=display,
            raw_context="",
            confidence="high",
            note=f"picked by paralegal (attorney id={pick.value})",
        )
    raw_context = _lookup_raw_context_by_display(envelope, pick.value)
    return ResolvedTemplateValueV2(
        template_variable=template_variable,
        value=pick.value,
        raw_context=raw_context,
        confidence="high",
        note="picked by paralegal",
    )


def _expand_multi_select(
    template_variable: str,
    pick: MultiSelectPickV2,
    envelope: PendingUserInputV2 | None,
) -> ResolvedTemplateValueV2:
    """MultiSelectPickV2 → resolved row. Oxford-comma joins picks;
    concatenates each pick's raw_context with `\\n---\\n` separators.

    Attorney multi-select picks send attorney `id`s (UUIDs); we map
    each id → display_name via the envelope's roster before joining.
    """
    deduped = _dedupe_preserve_order_case_insensitive(pick.picked_values)
    if not deduped:
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note="multi_select: no picks",
        )

    if isinstance(envelope, PendingAttorneyPickV2):
        display_names = [_attorney_display_for_id(envelope, pid) for pid in deduped]
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value=_oxford_comma_join(display_names),
            raw_context="",
            confidence="high",
            note=f"picked by paralegal ({len(deduped)} attorneys)",
        )

    joined_value = _oxford_comma_join(deduped)
    joined_raw_context = _join_raw_contexts_by_display(envelope, deduped)
    return ResolvedTemplateValueV2(
        template_variable=template_variable,
        value=joined_value,
        raw_context=joined_raw_context,
        confidence="high",
        note=f"picked by paralegal ({len(deduped)} of N)",
    )


def _attorney_display_for_id(
    envelope: PendingAttorneyPickV2,
    attorney_id: str,
) -> str:
    """Look up an attorney's display_name from the envelope's roster.
    Falls back to the id verbatim if the roster doesn't include it —
    surfaces visibly in the rendered docx so the paralegal can spot
    a stale id rather than silently dropping the value."""
    for row in envelope.options:
        if row.id == attorney_id:
            return row.display_name
    logger.warning(
        "_attorney_display_for_id: id '%s' not in envelope roster (%d entries) — "
        "passing id through verbatim",
        attorney_id, len(envelope.options),
    )
    return attorney_id


async def _expand_supporting_docs(
    *,
    template_variable: str,
    field: TemplateFieldV2,
    pick: SupportingDocsPickV2,
    resource_key: str | None,
) -> ResolvedTemplateValueV2:
    """SupportingDocsPickV2 → resolved row via ExplanationEnhanceAgentV2.

    Pipeline:
    1. Validate user_text is non-empty (else low-confidence empty row).
    2. Validate every `file_url` is under the case's R2
       `supporting_docs/` prefix — security: prevents cross-case
       file references.
    3. Download each file from R2 and parse via v1's
       `read_supporting_doc` (read-only utility).
    4. Run `ExplanationEnhanceAgentV2.run(...)` to polish.
    5. Soft failures: missing resource_key, validation error, download
       error, parse error, or LLM failure all degrade to the user's
       raw text (logged) — enhancement is a quality improvement, not
       a hard dependency.
    """
    user_text = (pick.user_text or "").strip()
    if not user_text:
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value="",
            confidence="none",
            note="author_input with_docs: empty user_text",
        )

    label = _resolve_with_docs_label(field, template_variable)

    if resource_key is None:
        logger.warning(
            "_expand_supporting_docs: no resource_key supplied for '%s'; "
            "returning raw user text (file download requires case scope)",
            template_variable,
        )
        return ResolvedTemplateValueV2(
            template_variable=template_variable,
            value=user_text,
            confidence="low",
            note=(
                f"author_input with_docs: resource_key missing — "
                f"{len(pick.file_urls)} files NOT downloaded, no enhancement run."
            ),
        )

    valid_urls, validation_errors = _validate_supporting_doc_urls(
        pick.file_urls, resource_key=resource_key,
    )
    if validation_errors:
        for err in validation_errors:
            logger.warning(
                "_expand_supporting_docs: %s for '%s'",
                err, template_variable,
            )

    supporting_docs = await _download_and_parse_supporting_docs(
        urls=valid_urls,
        resource_key=resource_key,
        variable_name=template_variable,
    )

    output_expectation = (
        field.params.output_expectation if field.params else None
    )
    enhanced = await ExplanationEnhanceAgentV2.run(
        variable_name=template_variable,
        label=label,
        user_text=user_text,
        supporting_docs=supporting_docs,
        template_property_marker=field.template_property_marker,
        output_expectation=output_expectation,
    )

    return ResolvedTemplateValueV2(
        template_variable=template_variable,
        value=enhanced,
        confidence="high" if enhanced and enhanced != user_text else "medium",
        note=(
            f"author_input with_docs: {len(supporting_docs)} of "
            f"{len(pick.file_urls)} files attached; "
            f"{'polished' if enhanced != user_text else 'raw (LLM unavailable)'}."
        ),
    )


def _resolve_with_docs_label(
    field: TemplateFieldV2,
    template_variable: str,
) -> str:
    """Heal target label for the enhancement prompt — uses the
    wizard-saved label when set, else humanizes the variable name."""
    if field.params and field.params.label and field.params.label.strip():
        return field.params.label.strip()
    pretty = template_variable.replace("_", " ").strip()
    return f"Enter the {pretty}" if pretty else template_variable


def _validate_supporting_doc_urls(
    file_urls: list[str],
    *,
    resource_key: str,
) -> tuple[list[str], list[str]]:
    """Return `(valid_urls, errors)`. URLs that don't start with the
    case's supporting_docs prefix are dropped + reported."""
    prefix = _supporting_docs_prefix(resource_key)
    valid: list[str] = []
    errors: list[str] = []
    for url in file_urls:
        if url.startswith(prefix):
            valid.append(url)
        else:
            errors.append(
                f"file_url '{url}' is not under the case's supporting_docs "
                f"R2 prefix ('{prefix}'); dropped."
            )
    return valid, errors


async def _download_and_parse_supporting_docs(
    *,
    urls: list[str],
    resource_key: str,
    variable_name: str,
) -> list[SupportingDoc]:
    """Download each url from R2 and parse into a SupportingDoc variant.

    Best-effort: per-doc failures (download error, parse error) are
    logged and the doc is skipped — the agent gets the docs that DID
    parse successfully + a polished output is still produced.

    URL shape (per `_supporting_docs_prefix`):
        "cases/{resource_key}/supporting_docs/{uuid}.{ext}"

    `r2_service.download_file(template_id=resource_key, filename=...,
    prefix='cases')` builds the key `cases/{resource_key}/{filename}` so we
    pass `filename = "supporting_docs/{uuid}.{ext}"`.
    """
    key_prefix = _supporting_docs_prefix(resource_key)
    out: list[SupportingDoc] = []

    for url in urls:
        relative = url[len(key_prefix):]   # "{uuid}.{ext}"
        filename = f"supporting_docs/{relative}"

        try:
            content = await r2_service.download_file(
                template_id=resource_key,
                filename=filename,
                prefix="cases",
            )
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "_download_and_parse_supporting_docs: download failed for "
                "'%s' (variable=%s): %s — skipping",
                url, variable_name, err,
            )
            continue

        original_filename = Path(relative).name
        try:
            out.append(read_supporting_doc(original_filename, content))
        except HTTPException as err:
            logger.warning(
                "_download_and_parse_supporting_docs: parse failed for "
                "'%s' (variable=%s): %s — skipping",
                url, variable_name, err.detail,
            )
            continue
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "_download_and_parse_supporting_docs: parse raised for "
                "'%s' (variable=%s): %s — skipping",
                url, variable_name, err,
            )
            continue

    return out


# ─── helpers ─────────────────────────────────────────────────────────


def _dedupe_preserve_order_case_insensitive(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if not v or not v.strip():
            continue
        key = v.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v.strip())
    return out


def _oxford_comma_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _lookup_raw_context_by_display(
    envelope: PendingUserInputV2 | None,
    display: str,
) -> str:
    """Find `display` in the envelope's options/chips and return the
    matching raw_context. Returns empty string when nothing matches —
    derived children then fall back to `value`."""
    if envelope is None:
        return ""
    options: list[str] = []
    raw_contexts: list[str] = []
    if isinstance(envelope, PendingDropdownV2):
        options, raw_contexts = envelope.options, envelope.raw_contexts
    elif isinstance(envelope, PendingMultiSelectV2):
        options, raw_contexts = envelope.options, envelope.raw_contexts
    elif isinstance(envelope, PendingChipV2):
        options, raw_contexts = envelope.chips, envelope.raw_contexts
    else:
        return ""

    for i, opt in enumerate(options):
        if opt == display and i < len(raw_contexts):
            return raw_contexts[i]
    return ""


def _join_raw_contexts_by_display(
    envelope: PendingUserInputV2 | None,
    picks: list[str],
) -> str:
    """Concat raw_contexts of every pick in `picks` with `\\n---\\n`
    separators. Skips picks that don't match a known option."""
    chunks: list[str] = []
    for pick in picks:
        rc = _lookup_raw_context_by_display(envelope, pick)
        if rc:
            chunks.append(rc)
    return "\n---\n".join(chunks)
