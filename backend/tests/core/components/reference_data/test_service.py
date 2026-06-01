"""Tests for the /reference-data service layer — happy paths and HTTP error shapes around ReferenceDataRepository."""

import pytest
from fastapi import HTTPException

from src.core.common.storage.database import ReferenceData
from src.core.components.reference_data.service import (
    create_reference_data_entry,
    delete_reference_data_entry,
    get_reference_data_entry,
    list_reference_data_entries,
    update_reference_data_entry,
)


def _make_row(
    short_code: str,
    value: str = "v",
    display_name: str | None = None,
    category: str | None = None,
    description: str | None = None,
) -> ReferenceData:
    return ReferenceData(
        id=f"id-{short_code}",
        short_code=short_code,
        display_name=display_name or short_code.replace("_", " ").title(),
        value=value,
        category=category,
        description=description,
    )


class _FakeReferenceDataRepository:
    """In-memory ReferenceDataRepository for isolating the service-layer
    logic from real DB sessions. Mirrors the real repository's classmethod
    surface so monkeypatching a single attribute is enough."""

    def __init__(self):
        self._rows: dict[str, ReferenceData] = {}
        self.delete_calls: list[str] = []
        self.list_calls: list[str | None] = []

    async def get(self, short_code: str) -> ReferenceData | None:
        return self._rows.get(short_code)

    async def create(
        self,
        short_code: str,
        display_name: str,
        value: str,
        category: str | None = None,
        description: str | None = None,
    ) -> ReferenceData:
        row = _make_row(
            short_code=short_code,
            display_name=display_name,
            value=value,
            category=category,
            description=description,
        )
        self._rows[short_code] = row
        return row

    async def list(self, category: str | None = None) -> list[ReferenceData]:
        self.list_calls.append(category)
        rows = list(self._rows.values())
        if category is None:
            return rows
        return [r for r in rows if r.category == category]

    async def update(
        self,
        short_code: str,
        value: str | None,
        description: str | None,
    ) -> ReferenceData | None:
        existing = self._rows.get(short_code)
        if existing is None:
            return None
        if value is not None:
            existing.value = value
        if description is not None:
            existing.description = description
        return existing

    async def delete(self, short_code: str) -> bool:
        self.delete_calls.append(short_code)
        return self._rows.pop(short_code, None) is not None


@pytest.fixture
def fake_repo(monkeypatch):
    fake = _FakeReferenceDataRepository()
    monkeypatch.setattr(
        "src.core.components.reference_data.service.ReferenceDataRepository",
        fake,
    )
    return fake


# ─── delete_reference_data_entry ──────────────────────────────────────


@pytest.mark.unit
async def test_delete_reference_data_reserved_short_code_rejects_with_400(fake_repo):
    """ATTORNEYS is managed via the dedicated /core/attorneys endpoints —
    the generic delete must refuse with 400 and never touch the row."""
    fake_repo._rows["ATTORNEYS"] = _make_row("ATTORNEYS", value="[]")

    with pytest.raises(HTTPException) as exc:
        await delete_reference_data_entry("ATTORNEYS")

    assert exc.value.status_code == 400
    assert "reserved" in exc.value.detail.lower()
    assert fake_repo.delete_calls == []
    assert "ATTORNEYS" in fake_repo._rows  # untouched


@pytest.mark.unit
async def test_delete_reference_data_unknown_short_code_raises_404(fake_repo):
    with pytest.raises(HTTPException) as exc:
        await delete_reference_data_entry("NOT_THERE")

    assert exc.value.status_code == 404
    assert "NOT_THERE" in exc.value.detail
    assert fake_repo.delete_calls == []


@pytest.mark.unit
async def test_delete_reference_data_happy_path_soft_deletes(fake_repo):
    fake_repo._rows["FIRM_PHONE"] = _make_row("FIRM_PHONE", value="555-0100")

    result = await delete_reference_data_entry("FIRM_PHONE")

    assert result is None
    assert fake_repo.delete_calls == ["FIRM_PHONE"]


# ─── create_reference_data_entry ──────────────────────────────────────


@pytest.mark.unit
async def test_create_reference_data_derives_short_code_and_persists(fake_repo):
    resp = await create_reference_data_entry(
        name="Firm Phone",
        value="555-0100",
        description=None,
    )

    assert resp.short_code == "FIRM_PHONE"
    assert resp.display_name == "Firm Phone"
    assert resp.value == "555-0100"
    assert "FIRM_PHONE" in fake_repo._rows


@pytest.mark.unit
async def test_create_reference_data_suffixes_on_collision(fake_repo):
    """When the derived short_code already exists, append _2 (then _3…)."""
    fake_repo._rows["FIRM_PHONE"] = _make_row("FIRM_PHONE", value="existing")

    resp = await create_reference_data_entry(
        name="Firm Phone",
        value="555-0100",
        description=None,
    )

    assert resp.short_code == "FIRM_PHONE_2"
    assert "FIRM_PHONE_2" in fake_repo._rows
    assert fake_repo._rows["FIRM_PHONE"].value == "existing"  # original untouched


# ─── get_reference_data_entry ─────────────────────────────────────────


@pytest.mark.unit
async def test_get_reference_data_returns_response_when_found(fake_repo):
    fake_repo._rows["FIRM_PHONE"] = _make_row(
        "FIRM_PHONE",
        value="555-0100",
        description="Main line",
    )

    resp = await get_reference_data_entry("FIRM_PHONE")

    assert resp.short_code == "FIRM_PHONE"
    assert resp.value == "555-0100"
    assert resp.description == "Main line"


@pytest.mark.unit
async def test_get_reference_data_raises_404_when_missing(fake_repo):
    with pytest.raises(HTTPException) as exc:
        await get_reference_data_entry("NOT_THERE")

    assert exc.value.status_code == 404
    assert "NOT_THERE" in exc.value.detail


# ─── list_reference_data_entries ──────────────────────────────────────


@pytest.mark.unit
async def test_list_reference_data_returns_all_when_no_category(fake_repo):
    fake_repo._rows["A"] = _make_row("A")
    fake_repo._rows["B"] = _make_row("B")
    fake_repo._rows["C"] = _make_row("C")

    resp = await list_reference_data_entries()

    assert {r.short_code for r in resp} == {"A", "B", "C"}
    assert fake_repo.list_calls == [None]


@pytest.mark.unit
async def test_list_reference_data_passes_category_filter_through(fake_repo):
    fake_repo._rows["A"] = _make_row("A", category="firm")
    fake_repo._rows["B"] = _make_row("B", category="court")

    resp = await list_reference_data_entries(category="firm")

    assert {r.short_code for r in resp} == {"A"}
    assert fake_repo.list_calls == ["firm"]


# ─── update_reference_data_entry ──────────────────────────────────────


@pytest.mark.unit
async def test_update_reference_data_returns_response_when_found(fake_repo):
    fake_repo._rows["FIRM_PHONE"] = _make_row("FIRM_PHONE", value="555-0100")

    resp = await update_reference_data_entry(
        short_code="FIRM_PHONE",
        value="555-9999",
        description="Updated",
    )

    assert resp.short_code == "FIRM_PHONE"
    assert resp.value == "555-9999"
    assert resp.description == "Updated"


@pytest.mark.unit
async def test_update_reference_data_raises_404_when_missing(fake_repo):
    with pytest.raises(HTTPException) as exc:
        await update_reference_data_entry(
            short_code="NOT_THERE",
            value="x",
            description=None,
        )

    assert exc.value.status_code == 404
    assert "NOT_THERE" in exc.value.detail
