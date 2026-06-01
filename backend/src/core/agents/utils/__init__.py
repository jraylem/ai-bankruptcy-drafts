"""Small utility modules used across the agents pipeline.

Two utilities live here today:
  - `petition_pdf` — best-effort downloader that resolves the case's
    `petition_pdf_url` (R2 presigned, R2 raw key, or external HTTPS) into
    PDF bytes for the vision-fallback agents.
  - `query_template` — `{{variable}}` reference parsing + substitution
    for source-params query strings (subject_query, body_query, text_query).

Public API is re-exported here so callers can write
`from src.core.agents.utils import fetch_petition_pdf_bytes` regardless of
which submodule a helper lives in.
"""

from .petition_pdf import fetch_petition_pdf_bytes
from .query_template import (
    extract_var_refs,
    extract_var_refs_from_source_params,
    substitute,
    substitute_source_params,
)

__all__ = [
    "fetch_petition_pdf_bytes",
    "extract_var_refs",
    "extract_var_refs_from_source_params",
    "substitute",
    "substitute_source_params",
]
