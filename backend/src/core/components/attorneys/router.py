"""HTTP routes for /core/attorneys — entry-level CRUD over the attorney roster stored as a reserved reference_data row."""

from fastapi import APIRouter, status

from .schemas import AttorneyCreateRequest, AttorneyResponse, AttorneyUpdateRequest
from .service import create_attorney, delete_attorney, list_attorneys, update_attorney

router = APIRouter(prefix="/attorneys", tags=["attorneys"])


@router.get("", response_model=list[AttorneyResponse])
async def list_attorneys_endpoint():
    """Return every attorney in the roster, in insertion order."""
    return await list_attorneys()


@router.post("", response_model=AttorneyResponse, status_code=status.HTTP_201_CREATED)
async def create_attorney_endpoint(data: AttorneyCreateRequest):
    """Append a new attorney. UUID is generated server-side; existing entries are untouched."""
    return await create_attorney(data.full_name)


@router.put("/{attorney_id}", response_model=AttorneyResponse)
async def update_attorney_endpoint(attorney_id: str, data: AttorneyUpdateRequest):
    """Rename an existing attorney; 404 if the id is unknown."""
    return await update_attorney(attorney_id, data.full_name)


@router.delete("/{attorney_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attorney_endpoint(attorney_id: str):
    """Remove an attorney from the roster; 404 if the id is unknown."""
    await delete_attorney(attorney_id)
