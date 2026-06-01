"""Request / response DTOs for the /core/attorneys endpoints."""

from pydantic import BaseModel, Field


class AttorneyCreateRequest(BaseModel):
    """Payload for adding an attorney to the roster."""

    full_name: str = Field(
        min_length=1,
        max_length=255,
        description="Full signed name including suffix (e.g. 'Chad Van Horn, Esq.').",
    )


class AttorneyUpdateRequest(BaseModel):
    """Payload for renaming an attorney; id stays fixed so existing template references keep resolving."""

    full_name: str = Field(
        min_length=1,
        max_length=255,
        description="New full signed name including suffix.",
    )


class AttorneyResponse(BaseModel):
    """Serialized attorney entry returned by every endpoint."""

    id: str
    full_name: str
