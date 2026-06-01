"""Async CRUD repository for the Case ORM model."""

from __future__ import annotations  # defer annotation evaluation — the
# `list` classmethod below shadows the `list` builtin inside the class
# body, breaking nested annotations like `tuple[list[Case], int]`.

import logging

from sqlalchemy import text

from ..models import Case
from .base import BaseRepository

logger = logging.getLogger(__name__)


def _collection_names(case_id: str) -> tuple[str, str, str]:
    return (
        f"case_file_{case_id}",
        f"gmail_emails_{case_id}",
        f"courtdrive_emails_{case_id}",
    )


# Tuned for personal names. WRatio handles middle-name expansion,
# token reordering, and minor typos. 85 tolerates ~1 letter swap or
# middle-name truncation; rejects clearly different people. Codified
# here so it can be tuned without touching the matcher logic.
NAME_MATCH_THRESHOLD = 85
NAME_TIE_BAND = 5  # warn when top-2 scores are within this many points
UNFILED_CANDIDATES_LIMIT = 10  # pathological-case safety cap


class CaseRepository(BaseRepository):
    """Async CRUD over the Case table — one row per bankruptcy case, anchors the per-case pgvector collection names."""

    @classmethod
    async def create(
        cls,
        *,
        case_id: str,
        case_name: str,
        firm_id: str | None,
        resource_key: str | None,
        case_number: str | None = None,
        case_number_original: str | None = None,
        court_district: str | None = None,
        chapter: int | None = None,
        petition_pdf_url: str | None = None,
        ssn_last4: str | None = None,
        ssn_extraction_status: str = "not_found",
        status: str = "filed",
    ) -> Case:
        """Create a new Case row.

        `case_id` is the UUID PK. `resource_key` (separate) names the
        per-case pgvector collections — sanitized case_number for filed
        cases, the UUID id as fallback for unfiled. When `resource_key`
        is None (unfiled case, no case_number yet), the three collection
        columns stay NULL — Phase 2's `promote_unfiled` materializes
        them with the sanitized case_number once filing occurs.
        """
        if resource_key is not None:
            case_file_collection, gmail_collection, courtdrive_collection = (
                _collection_names(resource_key)
            )
        else:
            case_file_collection = gmail_collection = courtdrive_collection = None

        async with cls._session() as session:
            try:
                case = Case(
                    id=case_id,
                    firm_id=firm_id,
                    case_name=case_name,
                    case_number=case_number,
                    case_number_original=case_number_original,
                    court_district=court_district,
                    chapter=chapter,
                    petition_pdf_url=petition_pdf_url,
                    case_file_collection=case_file_collection,
                    gmail_collection=gmail_collection,
                    courtdrive_collection=courtdrive_collection,
                    ssn_last4=ssn_last4,
                    ssn_extraction_status=ssn_extraction_status,
                    status=status,
                )
                session.add(case)
                await session.commit()
                await session.refresh(case)
                logger.info(
                    "Created case: id=%s firm_id=%s case_number=%s status=%s",
                    case_id, firm_id, case_number, status,
                )
                return case
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to create case {case_id}: {e}")
                raise

    @classmethod
    async def get(cls, case_id: str) -> Case | None:
        """Get a Case row by id, with `legacy_id` fallback.

        Post-Phase-1 the PK is a UUID. Pre-migration the PK was the
        sanitized case_number slug — preserved on the row as `legacy_id`.
        This dual-lookup lets bookmarked URLs like /draft-v2/case/26_01225
        keep resolving after the UUID rewrite. Tries id first (the common
        case), then falls back to legacy_id (older bookmark).
        """
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        "SELECT * FROM cases "
                        "WHERE (id = :case_id OR legacy_id = :case_id) "
                        "AND is_active = true "
                        "ORDER BY (id = :case_id) DESC "
                        "LIMIT 1"
                    ),
                    {"case_id": case_id},
                )
                row = result.fetchone()
                if row:
                    return Case(**dict(row._mapping))
                return None
            except Exception as e:
                logger.error(f"Failed to get case {case_id}: {e}")
                raise

    @classmethod
    async def get_by_case_number(cls, case_number: str) -> Case | None:
        """Lookup a Case row by its normalized case_number."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text("SELECT * FROM cases WHERE case_number = :case_number AND is_active = true"),
                    {"case_number": case_number},
                )
                row = result.fetchone()
                if row:
                    return Case(**dict(row._mapping))
                return None
            except Exception as e:
                logger.error(f"Failed to get case by number {case_number}: {e}")
                raise

    @classmethod
    async def list(cls) -> list[Case]:
        """List all active Case rows, newest first. Kept for callers that
        want the full list (e.g. internal jobs). FE callers should prefer
        `list_paginated` to avoid signing thousands of URLs at once."""
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text("SELECT * FROM cases WHERE is_active = true ORDER BY created_at DESC")
                )
                rows = result.fetchall()
                return [Case(**dict(r._mapping)) for r in rows]
            except Exception as e:
                logger.error(f"Failed to list cases: {e}")
                raise

    @classmethod
    async def find_unfiled_match(
        cls,
        *,
        firm_id: str,
        ssn_last4: str,
        case_name: str,
    ) -> str | None:
        """Find the best unfiled-case match id for an extracted petition.

        Two-step gate:
          1. SQL prefilter on (firm_id, ssn_last4, status='unfiled'). SSN
             is the hard primary key — same SSN is the only way two rows
             can refer to the same client. Hits idx_cases_ssn_match.
          2. rapidfuzz.fuzz.WRatio over case_name. Returns the highest-
             scoring candidate above NAME_MATCH_THRESHOLD, or None.

        Returns the cases.id (UUID) of the matched unfiled row, or None
        when no row clears both the SSN gate and the name threshold.
        """
        async with cls._session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, case_name FROM cases
                    WHERE firm_id = :firm
                      AND status = 'unfiled'
                      AND ssn_last4 = :ssn
                      AND is_active = true
                    ORDER BY created_at DESC
                    LIMIT :cap
                    """
                ),
                {"firm": firm_id, "ssn": ssn_last4, "cap": UNFILED_CANDIDATES_LIMIT},
            )
            candidates = list(result.fetchall())

        if not candidates:
            return None

        from rapidfuzz import fuzz
        scored = sorted(
            (
                (row.id, row.case_name, fuzz.WRatio(case_name, row.case_name or ""))
                for row in candidates
            ),
            key=lambda t: t[2],
            reverse=True,
        )
        top_id, top_name, top_score = scored[0]
        if top_score < NAME_MATCH_THRESHOLD:
            return None
        if len(scored) > 1 and (top_score - scored[1][2]) < NAME_TIE_BAND:
            logger.warning(
                "find_unfiled_match near-tie firm=%s ssn=%s: %r=%d vs %r=%d",
                firm_id, ssn_last4, top_name, top_score, scored[1][1], scored[1][2],
            )
        return top_id

    @classmethod
    async def promote_unfiled(
        cls,
        *,
        case_id: str,
        case_number: str,
        case_number_original: str | None,
        court_district: str | None,
        chapter: int | None,
        resource_key: str,
        petition_pdf_url: str | None,
    ) -> Case:
        """Flip an unfiled cases row to filed in-place.

        Sets case_number / case_number_original / court_district /
        chapter / status='filed', materializes the three collection
        names from the now-derivable sanitized case_number (resource_key),
        and updates petition_pdf_url to point at the new R2 path.

        The R2 PDF object move (cases/<uuid>/petition.pdf →
        cases/<sanitized>/petition.pdf) is the caller's responsibility,
        as is firing PdfIndexer + EmailIndexer first-time indexing —
        the repo only owns the DB row mutation.
        """
        case_file_collection, gmail_collection, courtdrive_collection = (
            _collection_names(resource_key)
        )
        async with cls._session() as session:
            try:
                result = await session.execute(
                    text(
                        """
                        UPDATE cases SET
                            case_number = :case_number,
                            case_number_original = :case_number_original,
                            court_district = :court_district,
                            chapter = :chapter,
                            status = 'filed',
                            case_file_collection = :case_file_collection,
                            gmail_collection = :gmail_collection,
                            courtdrive_collection = :courtdrive_collection,
                            petition_pdf_url = :petition_pdf_url
                        WHERE id = :case_id AND status = 'unfiled'
                        RETURNING *
                        """
                    ),
                    {
                        "case_id": case_id,
                        "case_number": case_number,
                        "case_number_original": case_number_original,
                        "court_district": court_district,
                        "chapter": chapter,
                        "case_file_collection": case_file_collection,
                        "gmail_collection": gmail_collection,
                        "courtdrive_collection": courtdrive_collection,
                        "petition_pdf_url": petition_pdf_url,
                    },
                )
                row = result.fetchone()
                if row is None:
                    raise RuntimeError(
                        f"promote_unfiled: case {case_id} not found or already filed"
                    )
                await session.commit()
                logger.info(
                    "Promoted unfiled case to filed: id=%s case_number=%s",
                    case_id, case_number,
                )
                return Case(**dict(row._mapping))
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to promote unfiled case {case_id}: {e}")
                raise

    @classmethod
    async def list_paginated(cls, *, limit: int, offset: int) -> tuple[list[Case], int]:
        """Return `(rows, total)` — `rows` is the requested page, `total`
        is the count of every active case (so the FE can derive
        has_more). Newest first."""
        async with cls._session() as session:
            try:
                page = await session.execute(
                    text(
                        "SELECT * FROM cases WHERE is_active = true "
                        "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": limit, "offset": offset},
                )
                rows = [Case(**dict(r._mapping)) for r in page.fetchall()]
                count = await session.execute(
                    text("SELECT COUNT(*) FROM cases WHERE is_active = true")
                )
                total = int(count.scalar() or 0)
                return rows, total
            except Exception as e:
                logger.error(f"Failed to paginate cases (limit={limit}, offset={offset}): {e}")
                raise
