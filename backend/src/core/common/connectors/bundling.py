"""Bundling-related connectors — child-side authoring surface.

Currently exports the single `inherit_from_parent` source that lets a
child template's variable declare itself as a slot. Each parent template
that attaches the child fills the slot via per-companion
`slot_configurations` on its own bundling spec — no source params other
than an optional `fallback_value` live on this child-side declaration.

The parent-side surface (companion list + slot configurations) is
authored on the parent template's Bundling tab — not exposed as a
connector here because it lives on a different layer (template-level,
not variable-level).
"""

from src.core.agents.types.sources import FieldSource

from ._schemas import Connector, ConnectorParam


INHERIT_FROM_PARENT_CONNECTOR = Connector(
    source=FieldSource.INHERIT_FROM_PARENT.value,
    display_name="Inherit from Parent",
    description=(
        "Mark this variable as a slot. Each parent template that attaches "
        "this child fills the slot via its own Bundling tab. The same child "
        "can be paired with many parents and have its slots filled "
        "differently for each pairing. Only meaningful for child-only "
        "templates (bundle_role=child_only)."
    ),
    params=[
        ConnectorParam(
            name="fallback_value",
            type="string",
            required=False,
            description=(
                "Optional placeholder shown when this child is dry-run "
                "alone (no parent attached). Useful for studio iteration "
                "before bundling lands."
            ),
        ),
    ],
)
