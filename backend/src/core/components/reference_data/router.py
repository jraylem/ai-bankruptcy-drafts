"""HTTP routes for the /reference-data endpoints — CRUD over reusable constants keyed by short_code."""

from fastapi import APIRouter, status

from .schemas import (
    ReferenceDataCreateRequest,
    ReferenceDataResponse,
    ReferenceDataUpdateRequest,
)
from .service import (
    create_reference_data_entry,
    delete_reference_data_entry,
    get_reference_data_entry,
    list_reference_data_entries,
    update_reference_data_entry,
)

router = APIRouter(prefix="/reference-data", tags=["reference-data"])


# ─── Routes ───


@router.post("", response_model=ReferenceDataResponse)
async def create_reference_data_endpoint(data: ReferenceDataCreateRequest):
    """Create a new reference data entry. short_code is auto-generated from name."""
    return await create_reference_data_entry(data.name, data.value, data.description)


@router.get("", response_model=list[ReferenceDataResponse])
async def list_reference_data_endpoint(category: str | None = None):
    """List all reference data, optionally filtered by category."""
    return await list_reference_data_entries(category=category)


@router.get("/{short_code}", response_model=ReferenceDataResponse)
async def get_reference_data_endpoint(short_code: str):
    """Get reference data by short_code."""
    return await get_reference_data_entry(short_code)


@router.put("/{short_code}", response_model=ReferenceDataResponse)
async def update_reference_data_endpoint(short_code: str, data: ReferenceDataUpdateRequest):
    """Update reference data value/description by short_code."""
    return await update_reference_data_entry(short_code, data.value, data.description)


@router.delete("/{short_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference_data_endpoint(short_code: str) -> None:
    """Soft-delete a reference-data row by short_code.

    404 if the short_code is unknown; 400 if it's a reserved short_code
    (managed via its own dedicated endpoint, e.g. ATTORNEYS).
    """
    await delete_reference_data_entry(short_code)
