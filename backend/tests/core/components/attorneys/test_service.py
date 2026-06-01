"""Tests for the /core/attorneys service layer — happy paths and HTTP error shapes around AttorneyRosterRepository."""

import pytest
from fastapi import HTTPException

from src.core.common.storage.database import Attorney
from src.core.components.attorneys.service import (
    create_attorney,
    delete_attorney,
    list_attorneys,
    update_attorney,
)


class _FakeRoster:
    """In-memory AttorneyRosterRepository for isolating service-layer logic
    from DB + reference_data plumbing."""

    def __init__(self):
        self._entries: list[Attorney] = []

    async def list(self):
        return list(self._entries)

    async def add(self, full_name: str) -> Attorney:
        entry = Attorney(id=f"att-{len(self._entries)}", full_name=full_name)
        self._entries.append(entry)
        return entry

    async def update(self, attorney_id: str, full_name: str):
        for i, e in enumerate(self._entries):
            if e.id == attorney_id:
                updated = e.model_copy(update={"full_name": full_name})
                self._entries[i] = updated
                return updated
        return None

    async def delete(self, attorney_id: str) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.id != attorney_id]
        return len(self._entries) != before


@pytest.fixture
def fake_roster(monkeypatch):
    fake = _FakeRoster()
    monkeypatch.setattr(
        "src.core.components.attorneys.service.AttorneyRosterRepository",
        fake,
    )
    return fake


@pytest.mark.unit
async def test_list_attorneys_returns_roster_entries(fake_roster):
    await fake_roster.add("Chad Van Horn, Esq.")
    await fake_roster.add("Jane Smith, Esq.")

    result = await list_attorneys()
    assert [a.full_name for a in result] == ["Chad Van Horn, Esq.", "Jane Smith, Esq."]


@pytest.mark.unit
async def test_create_attorney_trims_and_returns_response(fake_roster):
    response = await create_attorney("  Chad Van Horn, Esq.  ")
    assert response.full_name == "Chad Van Horn, Esq."
    assert response.id.startswith("att-")


@pytest.mark.unit
async def test_create_attorney_rejects_blank_name(fake_roster):
    with pytest.raises(HTTPException) as exc:
        await create_attorney("   ")
    assert exc.value.status_code == 400


@pytest.mark.unit
async def test_update_attorney_renames_entry(fake_roster):
    created = await fake_roster.add("Old Name")
    response = await update_attorney(created.id, "New Name")
    assert response.id == created.id
    assert response.full_name == "New Name"


@pytest.mark.unit
async def test_update_attorney_404_on_unknown_id(fake_roster):
    with pytest.raises(HTTPException) as exc:
        await update_attorney("missing", "Anything")
    assert exc.value.status_code == 404


@pytest.mark.unit
async def test_delete_attorney_removes_entry(fake_roster):
    created = await fake_roster.add("To delete")
    await delete_attorney(created.id)
    assert await fake_roster.list() == []


@pytest.mark.unit
async def test_delete_attorney_404_on_unknown_id(fake_roster):
    with pytest.raises(HTTPException) as exc:
        await delete_attorney("missing")
    assert exc.value.status_code == 404
