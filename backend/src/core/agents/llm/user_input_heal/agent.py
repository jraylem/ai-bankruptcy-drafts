"""
User-input heal agent.

Runs between UserInputResolver.expand_picks(...) and
DocxTemplateService.fill_template(...) in both the dry-run and draft flows.
For each USER_INPUT-family ResolvedTemplateValue (reco-chip, dropdown,
multi-select, plain-text, or supporting-docs), the agent receives:

  - The template paragraph containing the variable's [[placeholder]] — used
    as the grammatical context the filled value must integrate into. The
    template is name-free and date-free by construction (placeholders where
    original values were), so feeding it carries no case-bleed risk.
  - The user's final picked (and possibly edited) text. For multi-select
    fields this is the Oxford-comma-joined prose string of the picks.
  - Optionally a per-family heal target:
      - Reco-chips / plain-text: `example_sentence` / `example_output_sentence`
        — the author's name-free target sentence.
      - Dropdown / multi-select: `template_property_marker` from the
        TemplateField — the original value extracted from the source
        document at template-generation time, which shows the preferred
        presentation style (casing, phrasing, formatting). For multi-select
        the prompt reinforces that the marker is a SAMPLE from a different
        case — it provides shape, not facts.

The agent returns a single string: the fragment that should replace the
placeholder, with redundant subjects / articles / connectives dropped and
casual phrasings lifted into formal third-person legal prose.

Error policy: on None / exception, return the user's raw value unchanged.
Heal is a quality improvement, never a hard dependency of the fill pipeline.
"""

import asyncio
import logging

from pydantic import BaseModel, Field

from src.core.common.documents.docx_template import DocxTemplateService

from ...types.resolution import ResolvedTemplateValue
from ...types.sources import (
    DropdownCaseVectorSourceParams,
    DropdownEmailSourceParams,
    DropdownFromConstantsSourceParams,
    FieldSource,
    MultiSelectFromCaseVectorSourceParams,
    MultiSelectFromGmailSourceParams,
    RecoChipsCaseVectorSourceParams,
    RecoChipsEmailSourceParams,
    RecoChipsFromDependentVariablesSourceParams,
    UserInputPlainTextSourceParams,
)
from ...types.spec import AgentConfig
from ..base import Agent
from .prompt_builder import HealTargetKind, _build_heal_prompt

logger = logging.getLogger(__name__)


_RECO_CHIP_SOURCES = {
    FieldSource.RECO_CHIPS_FROM_GMAIL,
    FieldSource.RECO_CHIPS_FROM_COURT_DRIVE,
    FieldSource.RECO_CHIPS_FROM_CASE_VECTOR,
    FieldSource.RECO_CHIPS_FROM_DEPENDENT_VARIABLES,
}
_DROPDOWN_SOURCES = {
    FieldSource.DROPDOWN_FROM_GMAIL,
    FieldSource.DROPDOWN_FROM_COURT_DRIVE,
    FieldSource.DROPDOWN_FROM_CASE_VECTOR,
    FieldSource.DROPDOWN_FROM_CONSTANTS,
}
_MULTI_SELECT_SOURCES = {
    FieldSource.MULTI_SELECT_FROM_CASE_VECTOR,
    FieldSource.MULTI_SELECT_FROM_GMAIL,
}
_SUPPORTING_DOCS_SOURCES = {
    FieldSource.USER_INPUT_WITH_SUPPORTING_DOCS,
}
_PLAIN_TEXT_SOURCES = {
    FieldSource.USER_INPUT_PLAIN_TEXT,
}
_INHERIT_FROM_PARENT_SOURCES = {
    FieldSource.INHERIT_FROM_PARENT,
}
# Supporting-docs fields go through ExplanationEnhanceAgent first (which polishes
# tone + corroborates facts from uploaded docs) and THEN through heal here so
# the output grammatically fits the surrounding template paragraph — the
# enhancement agent doesn't see the template paragraph, so without this second
# pass filled paragraphs could read "The Debtor, <name>, The Debtor was laid off..."
# with a duplicated subject. Heal uses heal_target=None for this source because
# neither example_sentence nor a preferred_format marker applies.
#
# Plain-text fields run through heal so the user's typed prose fits the
# surrounding sentence; uses example_sentence as heal_target when set, else None.
#
# INHERIT_FROM_PARENT is heal-eligible ONLY when the value came from a
# real parent (Phase 2 bundling run with parent_context populated). The
# guard lives in `heal_resolved_values` — it inspects each resolved
# value's `reasoning` and skips the heal call when the resolver flagged
# the value as a fallback / unconfigured slot. Without the guard, heal
# would shape-align fallback placeholders to the child's template marker
# and morph "[parent.slot.docket_title]" into the marker's authoring
# content (e.g. "Motion to Modify Plan"), masquerading fake data as a
# high-confidence value.
_USER_INPUT_HEAL_SOURCES = (
    _RECO_CHIP_SOURCES
    | _DROPDOWN_SOURCES
    | _MULTI_SELECT_SOURCES
    | _SUPPORTING_DOCS_SOURCES
    | _PLAIN_TEXT_SOURCES
    | _INHERIT_FROM_PARENT_SOURCES
)


# Reasoning prefix the InheritFromParentResolver writes when no parent
# context was threaded through (fallback / unconfigured-slot path).
# Heal must NOT run on these values — see the comment above
# `_USER_INPUT_HEAL_SOURCES` for the rationale.
_INHERIT_FALLBACK_REASONING_PREFIX = "no parent context"


class _HealedFragment(BaseModel):
    """Structured-output target for the heal LLM call."""
    text: str = Field(
        description="The grammatically-fit, legal-tone enhanced fragment that should replace the placeholder"
    )


class UserInputHealAgent(Agent[_HealedFragment]):
    """Polish a user-supplied or extracted value so it fits the surrounding template paragraph grammatically and stylistically."""

    output_type = _HealedFragment
    max_tokens = 1000
    tags = ["core", "agent", "heal"]
    cost_kind = "user_input_heal"

    @classmethod
    async def run(
        cls,
        template_paragraph: str,
        placeholder: str,
        user_value: str,
        heal_target: str | None = None,
        heal_target_kind: HealTargetKind | None = None,
        author_instruction: str | None = None,
    ) -> str:
        """Return a healed fragment for the placeholder.

        `heal_target` + `heal_target_kind` together describe an optional
        "target presentation" block rendered into the prompt:
          - kind="example_sentence" (reco-chips): a generic GUIDE block.
          - kind="preferred_format" (dropdown): a PREFERRED PRESENTATION block.
        When either is None/empty, no block is rendered.

        `author_instruction` is the per-field `TemplateField.instruction`
        surfaced to heal as an authoritative output-shaping rule. Useful
        when the surrounding paragraph + heal_target alone don't fully
        constrain the desired output (e.g. tense requirements, predicate-
        only output for fields whose docx prose already supplies a
        subject, anti-double-period rules, etc.). When supplied it is
        rendered as an AUTHOR INSTRUCTION block AND a top-level rule
        telling the LLM the instruction overrides shape conflicts.

        On any failure (None result or exception) return `user_value` unchanged
        — the pipeline continues filling the docx with the raw pick.
        """
        prompt = _build_heal_prompt(
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
                run_name="UserInputHeal",
                metadata={"placeholder": placeholder},
            )
        except Exception as e:
            logger.warning(
                f"UserInputHealAgent heal failed for '{placeholder}': {e}; returning raw user value"
            )
            return user_value

        if result is None or not result.text or not result.text.strip():
            logger.warning(
                f"UserInputHealAgent returned empty for '{placeholder}'; returning raw user value"
            )
            return user_value
        return result.text.strip()

    @classmethod
    async def heal_resolved_values(
        cls,
        template_bytes: bytes,
        agent_config: AgentConfig,
        resolved_values: list[ResolvedTemplateValue],
    ) -> list[ResolvedTemplateValue]:
        """Heal every USER_INPUT-eligible ResolvedTemplateValue in parallel and return a new list with substitutions applied.

        Each reco-chip, dropdown, or supporting-docs value runs through the
        heal LLM concurrently. Other values pass through untouched.

        Note: joint-debtor inline vs caption rendering happens at docx fill
        time inside DocxTemplateService (per-paragraph decision), NOT here —
        the same `\\n`-bearing value can land in both a caption paragraph
        (render as soft line break) and an inline body paragraph (render as
        ' and '-joined) within the same template, so the format choice has
        to be per-occurrence, not per-value.
        """
        fields_by_name = {f.property_name: f for f in agent_config.template_fields}

        jobs: list[tuple[int, ResolvedTemplateValue, str, str, str | None, HealTargetKind | None, str | None]] = []
        for idx, rv in enumerate(resolved_values):
            if not rv.value or not rv.value.strip():
                continue
            field = fields_by_name.get(rv.property_name)
            if field is None or field.source not in _USER_INPUT_HEAL_SOURCES:
                continue
            if (
                field.source == FieldSource.INHERIT_FROM_PARENT
                and (rv.reasoning or "").lower().startswith(_INHERIT_FALLBACK_REASONING_PREFIX)
            ):
                # Value is a fallback placeholder, not a real parent fill —
                # skip heal so the marker's authoring content doesn't bleed in.
                continue
            placeholder = field.template_variable_string
            if not placeholder:
                continue
            paragraph = DocxTemplateService.find_paragraph_containing(template_bytes, placeholder)
            if paragraph is None:
                continue

            heal_target: str | None = None
            heal_target_kind: HealTargetKind | None = None
            if field.source in _RECO_CHIP_SOURCES and isinstance(
                field.source_params,
                (
                    RecoChipsEmailSourceParams,
                    RecoChipsCaseVectorSourceParams,
                    RecoChipsFromDependentVariablesSourceParams,
                ),
            ):
                heal_target = field.source_params.example_sentence
                heal_target_kind = "example_sentence"
            elif field.source in _DROPDOWN_SOURCES and isinstance(
                field.source_params,
                (
                    DropdownEmailSourceParams,
                    DropdownCaseVectorSourceParams,
                    DropdownFromConstantsSourceParams,
                ),
            ):
                heal_target = field.template_property_marker
                heal_target_kind = "preferred_format"
            elif field.source in _MULTI_SELECT_SOURCES and isinstance(
                field.source_params,
                (MultiSelectFromCaseVectorSourceParams, MultiSelectFromGmailSourceParams),
            ):
                heal_target = field.template_property_marker
                heal_target_kind = "preferred_format"
            elif field.source in _PLAIN_TEXT_SOURCES and isinstance(
                field.source_params, UserInputPlainTextSourceParams
            ):
                heal_target = field.source_params.example_output_sentence
                heal_target_kind = "example_sentence"
            elif field.source in _INHERIT_FROM_PARENT_SOURCES:
                # Real parent-supplied value (Phase 2 bundling) — shape-align
                # to the child's template marker, same as dropdown / multi-select.
                heal_target = field.template_property_marker
                heal_target_kind = "preferred_format"

            author_instruction = (field.output_instruction or "").strip() or None

            jobs.append((idx, rv, paragraph, placeholder, heal_target, heal_target_kind, author_instruction))

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
                for _, rv, paragraph, placeholder, heal_target, heal_target_kind, author_instruction in jobs
            )
        )

        out = list(resolved_values)
        for (idx, rv, _, _, _, _, _), healed in zip(jobs, healed_texts):
            if healed == rv.value:
                continue
            out[idx] = rv.model_copy(update={
                "value": healed,
                "reasoning": (rv.reasoning or "") + " [grammar/tone healed]",
            })
        return out
