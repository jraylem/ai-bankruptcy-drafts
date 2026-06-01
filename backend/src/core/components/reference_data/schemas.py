"""HTTP request / response schemas for the /reference-data endpoints."""

from pydantic import BaseModel, Field


# ─── Requests ─────────────────────────────────────────────────────────


class ReferenceDataCreateRequest(BaseModel):
    """Request body for POST /reference-data — create a new reusable constant (short_code is derived server-side from the name)."""

    name: str = Field(description="Human-readable name (e.g., 'Firm Phone')")
    value: str = Field(description="The actual value to use in templates")
    description: str | None = Field(default=None, description="Optional description")


class ReferenceDataUpdateRequest(BaseModel):
    """Request body for PATCH /reference-data/{id} — partial update of value and/or description."""

    value: str | None = Field(default=None, description="The actual value to use in templates")
    description: str | None = Field(default=None, description="Optional description")


# ─── Responses ────────────────────────────────────────────────────────


class ReferenceDataResponse(BaseModel):
    """Response body for /reference-data endpoints — mirrors the ReferenceData ORM row."""

    id: str
    short_code: str
    display_name: str
    value: str
    category: str | None
    description: str | None
