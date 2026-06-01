"""Tests for AttorneyRosterRepository — typed wrapper over the reserved ATTORNEYS reference_data row."""

import json

import pytest

from src.core.common.storage.database import (
    ATTORNEYS_SHORT_CODE,
    Attorney,
    AttorneyRosterRepository,
    ReferenceData,
)


class _FakeRefDataRepo:
    """In-memory stand-in for ReferenceDataRepository covering only the surface
    AttorneyRosterRepository actually uses — get, create, update."""

    def __init__(self):
        self.rows: dict[str, ReferenceData] = {}

    async def get(self, short_code):
        return self.rows.get(short_code)

    async def create(self, short_code, display_name, value, category=None, description=None):
        row = ReferenceData(
            short_code=short_code,
            display_name=display_name,
            value=value,
            category=category,
            description=description,
        )
        self.rows[short_code] = row
        return row

    async def update(self, short_code, display_name=None, value=None, category=None, description=None):
        row = self.rows.get(short_code)
        if not row:
            return None
        if value is not None:
            row.value = value
        return row


@pytest.fixture
def fake_repo(monkeypatch):
    fake = _FakeRefDataRepo()
    monkeypatch.setattr(
        "src.core.common.storage.database.repositories.attorney_roster_repository.ReferenceDataRepository",
        fake,
    )
    return fake


@pytest.mark.unit
async def test_ensure_exists_seeds_empty_list_when_missing(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    row = fake_repo.rows[ATTORNEYS_SHORT_CODE]
    assert json.loads(row.value) == []
    assert row.category == "system"


@pytest.mark.unit
async def test_ensure_exists_is_idempotent(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    await AttorneyRosterRepository.add("Chad Van Horn, Esq.")
    await AttorneyRosterRepository.ensure_exists()  # should NOT overwrite
    roster = await AttorneyRosterRepository.list()
    assert len(roster) == 1
    assert roster[0].full_name == "Chad Van Horn, Esq."


@pytest.mark.unit
async def test_add_generates_unique_uuids(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    a1 = await AttorneyRosterRepository.add("A")
    a2 = await AttorneyRosterRepository.add("B")
    assert a1.id != a2.id
    roster = await AttorneyRosterRepository.list()
    assert [a.full_name for a in roster] == ["A", "B"]


@pytest.mark.unit
async def test_update_replaces_full_name_and_keeps_id(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    original = await AttorneyRosterRepository.add("Old Name")
    updated = await AttorneyRosterRepository.update(original.id, "New Name")
    assert updated is not None
    assert updated.id == original.id
    assert updated.full_name == "New Name"


@pytest.mark.unit
async def test_update_returns_none_for_unknown_id(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    assert await AttorneyRosterRepository.update("missing-id", "X") is None


@pytest.mark.unit
async def test_delete_removes_entry(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    a1 = await AttorneyRosterRepository.add("Keep")
    a2 = await AttorneyRosterRepository.add("Drop")

    removed = await AttorneyRosterRepository.delete(a2.id)
    assert removed is True
    roster = await AttorneyRosterRepository.list()
    assert [a.id for a in roster] == [a1.id]


@pytest.mark.unit
async def test_delete_returns_false_for_unknown_id(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    assert await AttorneyRosterRepository.delete("missing-id") is False


@pytest.mark.unit
async def test_list_returns_empty_when_value_json_is_corrupt(fake_repo, caplog):
    await AttorneyRosterRepository.ensure_exists()
    fake_repo.rows[ATTORNEYS_SHORT_CODE].value = "{not valid json"
    roster = await AttorneyRosterRepository.list()
    assert roster == []


@pytest.mark.unit
async def test_get_returns_none_for_unknown_id(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    await AttorneyRosterRepository.add("Chad Van Horn, Esq.")
    assert await AttorneyRosterRepository.get("nope") is None


@pytest.mark.unit
async def test_attorney_model_round_trips(fake_repo):
    await AttorneyRosterRepository.ensure_exists()
    created = await AttorneyRosterRepository.add("Chad Van Horn, Esq.")
    assert isinstance(created, Attorney)
    fetched = await AttorneyRosterRepository.get(created.id)
    assert fetched == created
