"""Attorney roster orchestration — wraps AttorneyRosterRepository with HTTP-shaped error handling."""

from fastapi import HTTPException

from src.core.common.storage.database import Attorney, AttorneyRosterRepository

from .schemas import AttorneyResponse


def _to_response(attorney: Attorney) -> AttorneyResponse:
    return AttorneyResponse(id=attorney.id, full_name=attorney.full_name)


async def list_attorneys() -> list[AttorneyResponse]:
    """Return every attorney in the roster in insertion order."""
    return [_to_response(a) for a in await AttorneyRosterRepository.list()]


async def create_attorney(full_name: str) -> AttorneyResponse:
    """Append a new attorney; UUID is generated server-side."""
    cleaned = full_name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="full_name must not be blank")
    attorney = await AttorneyRosterRepository.add(cleaned)
    return _to_response(attorney)


async def update_attorney(attorney_id: str, full_name: str) -> AttorneyResponse:
    """Rename the attorney with the given id; 404 if not found."""
    cleaned = full_name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="full_name must not be blank")
    updated = await AttorneyRosterRepository.update(attorney_id, cleaned)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Attorney '{attorney_id}' not found")
    return _to_response(updated)


async def delete_attorney(attorney_id: str) -> None:
    """Remove the attorney with the given id; 404 if not found."""
    removed = await AttorneyRosterRepository.delete(attorney_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Attorney '{attorney_id}' not found")
