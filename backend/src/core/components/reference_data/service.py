"""Reference-data CRUD service.

Reference data are reusable short_code-keyed constants (firm name, address,
etc.) that template variables can pull via FieldSource.CONSTANTS. This
module owns the full CRUD lifecycle plus short_code derivation from a
human-readable display name.

Short_code derivation is a one-way door: rename a display name and the
short_code stays frozen so existing template references keep resolving.
Use _ensure_unique_short_code to suffix collisions rather than crash or
overwrite.
"""

import re
import unicodedata

from fastapi import HTTPException

from src.core.common.storage.database import ReferenceDataRepository

from .schemas import ReferenceDataResponse


_SHORT_CODE_NONALNUM = re.compile(r"[^A-Za-z0-9]+")


def _derive_short_code(name: str) -> str:
    """Derive a stable short_code slug from a display name.

    ASCII-fold, collapse non-alphanumeric runs to a single underscore, strip
    trailing underscores, uppercase. Raises 400 when the input has no
    usable alphanumeric content (e.g. "   ", "@#$", "—") since short_code
    is the reference-data primary lookup key.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = _SHORT_CODE_NONALNUM.sub("_", folded).strip("_").upper()
    if not slug:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not derive a short_code from name '{name}': "
                "name must contain at least one ASCII-foldable alphanumeric character"
            ),
        )
    return slug


async def _ensure_unique_short_code(candidate: str) -> str:
    """Suffix _2, _3, … until candidate doesn't collide with an existing row."""
    if await ReferenceDataRepository.get(candidate) is None:
        return candidate
    counter = 2
    while True:
        suffixed = f"{candidate}_{counter}"
        if await ReferenceDataRepository.get(suffixed) is None:
            return suffixed
        counter += 1


def _ref_data_to_response(ref) -> ReferenceDataResponse:
    return ReferenceDataResponse(
        id=ref.id,
        short_code=ref.short_code,
        display_name=ref.display_name,
        value=ref.value,
        category=ref.category,
        description=ref.description,
    )


async def create_reference_data_entry(
    name: str,
    value: str,
    description: str | None,
) -> ReferenceDataResponse:
    """Create a new reference-data row; short_code is derived from the name and de-duplicated if it already exists."""
    short_code = await _ensure_unique_short_code(_derive_short_code(name))
    ref_data = await ReferenceDataRepository.create(
        short_code=short_code,
        display_name=name,
        value=value,
        category=None,
        description=description,
    )
    return _ref_data_to_response(ref_data)


async def list_reference_data_entries(category: str | None = None) -> list[ReferenceDataResponse]:
    """List every reference-data entry, optionally filtered by category."""
    ref_data_list = await ReferenceDataRepository.list(category=category)
    return [_ref_data_to_response(ref) for ref in ref_data_list]


async def get_reference_data_entry(short_code: str) -> ReferenceDataResponse:
    """Fetch a single reference-data entry by short_code; raise 404 if missing."""
    ref_data = await ReferenceDataRepository.get(short_code)
    if not ref_data:
        raise HTTPException(status_code=404, detail=f"Reference data '{short_code}' not found")
    return _ref_data_to_response(ref_data)


async def update_reference_data_entry(
    short_code: str,
    value: str | None,
    description: str | None,
) -> ReferenceDataResponse:
    """Partial-update value and/or description on a reference-data row keyed by short_code."""
    ref_data = await ReferenceDataRepository.update(
        short_code=short_code,
        value=value,
        description=description,
    )
    if not ref_data:
        raise HTTPException(status_code=404, detail=f"Reference data '{short_code}' not found")
    return _ref_data_to_response(ref_data)


# Reserved short_codes that the generic reference-data delete endpoint
# refuses to act on. The attorney roster is owned by the dedicated
# `/core/attorneys` endpoints — deleting the row here would orphan the
# attorney management surface and silently break templates referencing
# it via `dropdown_from_constants`.
_RESERVED_SHORT_CODES: frozenset[str] = frozenset({"ATTORNEYS"})


async def delete_reference_data_entry(short_code: str) -> None:
    """Soft-delete a reference-data row by short_code.

    Existence is verified first so a missing row produces a clean 404
    instead of relying on the repository's blanket-true return. Reserved
    short_codes (e.g. ATTORNEYS) raise 400 — those are managed via
    their own dedicated endpoints and must not be deleted generically.
    """
    if short_code in _RESERVED_SHORT_CODES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{short_code}' is a reserved reference-data row managed via a "
                "dedicated endpoint and cannot be deleted via this route."
            ),
        )
    existing = await ReferenceDataRepository.get(short_code)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Reference data '{short_code}' not found")
    await ReferenceDataRepository.delete(short_code)
