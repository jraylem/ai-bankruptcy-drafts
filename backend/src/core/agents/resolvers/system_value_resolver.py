"""
System-generated value resolver.

Produces deterministic values from runtime state (currently just the server
clock) for template variables marked with FieldSource.SYSTEM_GENERATED.
Runs after the draft agent, alongside the derivative rule executor, so the
LLM never sees these fields.

Pure, synchronous, and IO-free: no LLM, no network, no DB.
"""

from datetime import datetime

from ..types.resolution import ResolvedTemplateValue, ResolverStage
from ..types.sources import SystemGeneratedSourceParams, SystemGeneratedType
from ..types.spec import TemplateField


def _resolve_current_date(
    property_name: str,
    params: SystemGeneratedSourceParams,
    now: datetime,
) -> ResolvedTemplateValue:
    try:
        rendered = now.strftime(params.format)
    except ValueError as exc:
        return ResolvedTemplateValue.low_confidence(
            property_name,
            f"Failed to render current date with format '{params.format}': {exc}",
        )
    return ResolvedTemplateValue.high_confidence(
        property_name,
        rendered,
        f"Generated from server clock at draft time with format '{params.format}'.",
    )


class SystemValueResolver:
    """Resolve SYSTEM_GENERATED-stage fields from runtime state (e.g. the server clock)."""

    stage = ResolverStage.SYSTEM_GENERATED

    @classmethod
    def apply(
        cls,
        template_fields: list[TemplateField],
        now: datetime | None = None,
    ) -> list[ResolvedTemplateValue]:
        """Compute resolved values for every system_generated entry in the spec.

        `now` is an injection seam for tests — production callers pass None and
        the function uses `datetime.now()`. A single `now` is threaded through
        every variable in one invocation so that two system_generated fields
        rendered in the same draft are guaranteed to report the same instant.
        """
        if now is None:
            now = datetime.now()

        resolved: list[ResolvedTemplateValue] = []
        for field in template_fields:
            if field.stage != ResolverStage.SYSTEM_GENERATED:
                continue
            params = field.source_params
            if not isinstance(params, SystemGeneratedSourceParams):
                resolved.append(
                    ResolvedTemplateValue.low_confidence(
                        field.property_name,
                        "source_params did not match SystemGeneratedSourceParams.",
                    )
                )
                continue

            if params.type == SystemGeneratedType.CURRENT_DATE:
                resolved.append(_resolve_current_date(field.property_name, params, now))
                continue

            resolved.append(
                ResolvedTemplateValue.low_confidence(
                    field.property_name,
                    f"Unsupported system_generated type '{params.type.value}'.",
                )
            )

        return resolved
