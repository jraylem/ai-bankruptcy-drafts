"""Pydantic schemas for the FE-facing connector registry.

These are the wire types the `/template/connectors` endpoint serves.
`Connector` describes one `FieldSource`, `ConnectorParam` describes one
field in that connector's author-configuration form.
"""

from enum import Enum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field


class ConnectorParamOption(BaseModel):
    """One discrete choice for an enum-typed ConnectorParam (value + human-readable label + optional preview)."""

    value: str
    label: str
    preview: str | None = None


class ConnectorParamCondition(BaseModel):
    """Rule the FE evaluates against other param values in the same form."""
    model_config = ConfigDict(populate_by_name=True)

    field: str
    equals: str | None = None
    not_equals: str | None = None
    in_: list[str] | None = Field(default=None, alias="in")
    not_in: list[str] | None = None


class ConnectorParam(BaseModel):
    """One field in a connector's author-configuration form (name, type, required flag, optional FE visibility rules)."""

    name: str
    type: str
    required: bool
    description: str
    options: list[ConnectorParamOption] | None = None
    visible_when: ConnectorParamCondition | None = None
    required_when: ConnectorParamCondition | None = None
    allow_custom: bool | None = None


class Connector(BaseModel):
    """FE-facing descriptor for one FieldSource — display name, description, and the param form the author fills out."""

    source: str
    display_name: str
    description: str
    params: list[ConnectorParam]


def _options_from_enum(
    enum_class: type[Enum],
    labels: Mapping[str, str],
    previews: Mapping[str, str] | None = None,
) -> list[ConnectorParamOption]:
    """Derive a list of ConnectorParamOption from a string-enum.

    `labels` MUST cover every enum value — iteration raises KeyError on a
    missing label, which is the loud failure we want if someone adds a
    new enum value without updating the connector's human-readable label.
    """
    previews = previews or {}
    return [
        ConnectorParamOption(
            value=member.value,
            label=labels[member.value],
            preview=previews.get(member.value),
        )
        for member in enum_class
    ]
