"""Tests for the CONNECTORS registry.

Two invariants:

  1. Every `source` value resolves to a `FieldSource` enum value. Typo
     or stale enum → loud failure at test time rather than at request time.
  2. The serialized CONNECTORS JSON matches a committed snapshot. Any
     FE-facing change to the connector shape fails this test and forces
     an explicit snapshot update (--snapshot-update).
"""

import pytest

from src.core.agents.types.sources import FieldSource
from src.core.common.connectors import CONNECTORS


@pytest.mark.unit
def test_every_source_resolves_to_field_source_enum():
    valid_sources = {fs.value for fs in FieldSource}
    for connector in CONNECTORS:
        assert connector.source in valid_sources, (
            f"stale source '{connector.source}' — not a FieldSource enum value"
        )


@pytest.mark.unit
def test_connectors_snapshot(snapshot):
    payload = [c.model_dump(by_alias=True, exclude_none=True) for c in CONNECTORS]
    assert payload == snapshot


@pytest.mark.unit
def test_inherit_from_parent_connector_present_with_expected_shape():
    # Phase 1B regression — child-only templates rely on this entry being
    # in the connectors list with a fallback_value param, otherwise the
    # studio's source picker can't render the slot-marker form.
    inherit = next((c for c in CONNECTORS if c.source == "inherit_from_parent"), None)
    assert inherit is not None, "inherit_from_parent connector missing from CONNECTORS"
    assert inherit.display_name == "Inherit from Parent"
    param_names = {p.name for p in inherit.params}
    assert param_names == {"fallback_value"}
    fallback = next(p for p in inherit.params if p.name == "fallback_value")
    assert fallback.required is False
