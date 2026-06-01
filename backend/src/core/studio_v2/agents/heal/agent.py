"""UserInputHealAgentV2 — LLM prose shaper for v2 user-input fields.

Mirrors v1's UserInputHealAgent contract:
- Per-field LLM call with the surrounding template paragraph as
  context, the user's pick as input, and an optional shape target.
- Soft failure mode: on None / exception / empty output, return the
  user's raw value unchanged. Heal is a quality improvement, NEVER a
  hard dependency of the fill pipeline.
- Heals only USER-INPUT-family fields (the four wizard families that
  produce a pick: dropdown / chip / multi_select / author_input).
  Other source kinds (constants, current_date, derived, attorney-raw,
  value_from_parent_bundle) skip heal — they're already
  template-aware by construction.

v2 differences from v1:
- Source discrimination is by `(WizardSourceParams.source,
  presentation_shape)` not v1's `FieldSource` enum.
- Reuses v1's `DocxTemplateService.find_paragraph_containing` via
  read-only import — pure utility, no v1 modification.
- `output_expectation` (v2's per-field author instruction) maps to v1's
  `field.output_instruction`.
- `example_format` (v2) maps to v1's `field.template_property_marker`
  for dropdown / multi-select shapes — but is the AUTHOR's literal
  example string rather than the source-doc's original value.
"""

from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from pydantic import BaseModel, Field

from src.core.studio_v2.agents._v1_base import StudioV2Agent
from src.core.common.constants import CLAUDE_MODEL_ADVANCED
from src.core.common.documents.docx_template import DocxTemplateService

from ...types.fields import TemplateFieldV2
from ...types.resolution import ResolvedTemplateValueV2
from ...types.wizard_sources import (
    AuthorInputKind,
    PresentationShape,
    SourceKind,
    WizardSourceParams,
)
from .prompt_builder import HealTargetKindV2, build_user_input_heal_prompt

logger = logging.getLogger(__name__)


# Source families eligible for prose-heal. Other sources (constants /
# current_date / derived / attorney-raw / value_from_parent_bundle) skip
# heal — they're already template-aware or deterministic.
_USER_INPUT_HEAL_SOURCES = frozenset({
    SourceKind.AUTHOR_INPUT,
})


def _needs_heal(params: WizardSourceParams) -> bool:
    """Heal eligibility per (source, shape).

    Every value that flows through an LLM extractor (gmail / case_file)
    OR through a paralegal pick (author_input / dropdown / chip /
    multi_select / attorney pick) gets a final shape pass against the
    template's original sample (`template_property_marker`) +
    optional `output_expectation`. This ensures the rendered docx is
    consistent regardless of which path produced the value.

    Deterministic-verbatim sources opt OUT: constants are firm-config
    lookups, current_date already runs through date_healing,
    attorney-raw is a literal roster row, derived_from_variable was
    already shaped by DeriveAgent's prompt, value_from_parent_bundle
    inherits the parent's already-healed value.
    """
    if params.source in _USER_INPUT_HEAL_SOURCES:
        return True
    # gmail / case_file always heal — raw shape (LLM-extracted single
    # value) gets the same shape pass as the user-pick shapes
    # (dropdown / chip / multi_select). The marker is the most common
    # heal target for raw — the value needs to LOOK like the document's
    # original at this position.
    if params.source in (SourceKind.GMAIL, SourceKind.CASE_FILE):
        return True
    # attorney with dropdown / multi_select (user picks at draft time).
    if params.source == SourceKind.ATTORNEY:
        return params.presentation_shape != PresentationShape.RAW
    return False


def _resolve_heal_target(
    params: WizardSourceParams,
    template_property_marker: str | None = None,
) -> tuple[str | None, HealTargetKindV2 | None]:
    """Pick the per-shape heal target + its kind.

    Priority order (per shape):
    - **AUTHOR_INPUT plain_text / CHIP**: `output_expectation` if the
      author set it, otherwise fall back to `template_property_marker`
      (the original phrase at this placeholder position in the source
      doc — a real sample sentence with the right tone/grammar).
      Rendered as the GUIDE block.
    - **DROPDOWN / MULTI_SELECT**: `example_format` (the author's literal
      sample), falling back through `output_expectation` then
      `template_property_marker`. Rendered as PREFERRED PRESENTATION
      so the LLM only copies SHAPE, not facts.
    """
    if (
        params.source == SourceKind.AUTHOR_INPUT
        and params.author_input_kind == AuthorInputKind.PLAIN_TEXT
    ):
        target = (
            (params.output_expectation or "").strip()
            or (template_property_marker or "").strip()
            or None
        )
        return target, "example_sentence"

    if params.presentation_shape == PresentationShape.CHIP:
        target = (
            (params.output_expectation or "").strip()
            or (template_property_marker or "").strip()
            or None
        )
        return target, "example_sentence"

    if params.presentation_shape in (
        PresentationShape.DROPDOWN, PresentationShape.MULTI_SELECT,
    ):
        target = (
            (params.example_format or "").strip()
            or (params.output_expectation or "").strip()
            or (template_property_marker or "").strip()
            or None
        )
        return target, "preferred_format"

    target = (
        (params.output_expectation or "").strip()
        or (template_property_marker or "").strip()
        or None
    )
    return target, "example_sentence"


class _HealedFragmentV2(BaseModel):
    """Structured-output target for the heal LLM call."""

    text: str = Field(
        description=(
            "The grammatically-fit, legal-tone enhanced fragment that "
            "should replace the placeholder."
        ),
    )


class UserInputHealAgentV2(StudioV2Agent[_HealedFragmentV2]):
    """Per-field LLM heal pass for v2 user-input fields."""

    output_type: ClassVar[type[BaseModel]] = _HealedFragmentV2
    model: ClassVar[str] = CLAUDE_MODEL_ADVANCED
    max_tokens: ClassVar[int] = 1000
    tags: ClassVar[list[str]] = ["core", "agent", "studio_v2", "heal"]
    cost_kind: ClassVar[str] = "user_input_heal_v2"

    @classmethod
    async def run(
        cls,
        *,
        template_paragraph: str,
        placeholder: str,
        user_value: str,
        heal_target: str | None = None,
        heal_target_kind: HealTargetKindV2 | None = None,
        author_instruction: str | None = None,
    ) -> str:
        """Return a healed fragment for the placeholder.

        Soft failure: on None / exception / empty output, return
        `user_value` unchanged so the fill pipeline keeps going.
        """
        prompt = build_user_input_heal_prompt(
            template_paragraph=template_paragraph,
            placeholder=placeholder,
            user_value=user_value,
            heal_target=heal_target,
            heal_target_kind=heal_target_kind,
            author_instruction=author_instruction,
        )
        try:
            result = await cls._invoke(
                prompt,
                run_name=f"UserInputHealV2:{placeholder}",
                metadata={"placeholder": placeholder},
            )
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "UserInputHealAgentV2: heal LLM failed for %s (%s); "
                "returning raw user value",
                placeholder, err,
            )
            return user_value

        if result is None or not result.text or not result.text.strip():
            logger.warning(
                "UserInputHealAgentV2: heal LLM returned empty for %s; "
                "returning raw user value",
                placeholder,
            )
            return user_value
        return result.text.strip()

    @classmethod
    async def heal_resolved_values(
        cls,
        *,
        template_bytes: bytes,
        template_fields: list[TemplateFieldV2],
        resolved_values: list[ResolvedTemplateValueV2],
    ) -> list[ResolvedTemplateValueV2]:
        """Heal every eligible row in parallel; return a new list.

        Walks `resolved_values`, looks up each row's `TemplateFieldV2`
        in `template_fields`, decides eligibility via `_needs_heal`,
        and fires `cls.run(...)` for each. Returns the original list
        with healed values substituted in place.
        """
        fields_by_name = {f.template_variable: f for f in template_fields}

        jobs: list[
            tuple[int, ResolvedTemplateValueV2, str, str,
                  str | None, HealTargetKindV2 | None, str | None]
        ] = []
        for idx, rv in enumerate(resolved_values):
            if not rv.value or not rv.value.strip():
                continue
            field = fields_by_name.get(rv.template_variable)
            if field is None or field.params is None or not _needs_heal(field.params):
                continue

            placeholder = f"[[{field.template_variable}]]"
            paragraph = DocxTemplateService.find_paragraph_containing(
                template_bytes, placeholder,
            )
            if paragraph is None:
                continue

            heal_target, heal_target_kind = _resolve_heal_target(
                field.params,
                template_property_marker=field.template_property_marker,
            )
            author_instruction = (
                (field.params.output_expectation or "").strip() or None
            )
            jobs.append((
                idx, rv, paragraph, placeholder,
                heal_target, heal_target_kind, author_instruction,
            ))

        if not jobs:
            return resolved_values

        healed_texts = await asyncio.gather(
            *(
                cls.run(
                    template_paragraph=paragraph,
                    placeholder=placeholder,
                    user_value=rv.value,
                    heal_target=heal_target,
                    heal_target_kind=heal_target_kind,
                    author_instruction=author_instruction,
                )
                for _, rv, paragraph, placeholder,
                heal_target, heal_target_kind, author_instruction in jobs
            ),
        )

        out = list(resolved_values)
        for (idx, rv, _, _, _, _, _), healed in zip(jobs, healed_texts):
            if healed == rv.value:
                continue
            out[idx] = rv.model_copy(
                update={
                    "value": healed,
                    "note": _append_note(rv.note, "grammar/tone healed"),
                },
            )
        return out


def _append_note(existing: str, addition: str) -> str:
    if not existing:
        return addition
    return f"{existing}; {addition}"
