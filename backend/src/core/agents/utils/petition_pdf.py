"""Petition-PDF download helper for the case_vector vision-fallback agent.

The agent feeds the case's petition PDF to claude-opus-4-6 (Document
content block) so checkbox state, tabular data, and form layout that
pgvector chunks lose are visible at re-extraction time. This helper
fetches the bytes from whatever shape `Case.petition_pdf_url` is
stored in:

  - **R2 presigned URL** (most common): `https://<account>.r2.cloudflarestorage.com/<bucket>/<key>?X-Amz-...`.
    Presigned URLs expire (default TTL 1h), so we DON'T httpx-GET them
    — we parse the bucket+key out of the path and re-sign via boto3 by
    routing through `r2_service.download_by_key`. Lets the original
    URL's signature be arbitrarily stale without breaking the pass.
  - **External HTTPS URL** (non-R2): `httpx` GET as-is.
  - **Raw R2 key**: split into `prefix/template_id/filename` and route
    through `r2_service.download_file` (legacy path; rarely used).

Best-effort: any failure (network, 404, parse) returns `None` so the
caller can no-op the vision pass without breaking the pipeline.
"""

import logging
from urllib.parse import urlparse

import httpx

from src.core.common.storage.r2 import r2_service

logger = logging.getLogger(__name__)


_PDF_FETCH_TIMEOUT_SECONDS = 30
_R2_HOSTNAME_SUFFIX = "r2.cloudflarestorage.com"


def _extract_r2_key(parsed_url) -> str | None:
    """Pull the bucket-relative key out of an R2 URL's path.

    R2 path-style routing puts the bucket once (`/<bucket>/<key>`), but
    historical uploads sometimes baked the bucket name into the key
    itself, so the URL path ends up with the bucket appearing TWICE
    (e.g. `/bkdrafts-agt/bkdrafts-agt/cases/.../petition.pdf`). We
    iteratively strip the configured bucket-name prefix until none
    remains — the leftover is the actual S3 key to feed to
    `get_object(Bucket=..., Key=...)`. Returns `None` if the path is
    empty or fully consumed by bucket prefixes.
    """
    raw_path = (parsed_url.path or "").lstrip("/")
    if not raw_path:
        return None
    bucket_name = r2_service.bucket_name
    while bucket_name and raw_path.startswith(f"{bucket_name}/"):
        raw_path = raw_path[len(bucket_name) + 1 :]
    return raw_path or None


async def fetch_petition_pdf_bytes(petition_pdf_url: str | None) -> bytes | None:
    """Download a case's petition PDF as raw bytes.

    Returns `None` on any failure (with a logged warning); never raises.
    """
    if not petition_pdf_url:
        return None
    url = petition_pdf_url.strip()
    if not url:
        return None

    parsed = urlparse(url)

    # R2 URL → re-sign via boto3 (sidesteps stale presigned URLs).
    if (
        parsed.scheme in ("http", "https")
        and parsed.hostname is not None
        and _R2_HOSTNAME_SUFFIX in parsed.hostname
    ):
        key = _extract_r2_key(parsed)
        if not key:
            logger.warning(
                f"Petition PDF URL '{url}' is on R2 but has no extractable key; skipping."
            )
            return None
        try:
            return await r2_service.download_by_key(key)
        except Exception as e:
            logger.warning(
                f"Petition PDF R2 re-sign download failed for key '{key}': {e}"
            )
            return None

    # External HTTPS URL — httpx GET.
    if parsed.scheme in ("http", "https"):
        try:
            async with httpx.AsyncClient(timeout=_PDF_FETCH_TIMEOUT_SECONDS) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.warning(f"Petition PDF HTTP fetch failed for '{url}': {e}")
            return None

    # Raw R2 key (legacy) — needs at minimum {prefix}/{template_id}/{filename}.
    parts = url.lstrip("/").split("/")
    if len(parts) < 3:
        logger.warning(
            f"Petition PDF URL '{url}' is not an HTTP URL and not a valid "
            "R2 key (expected at least prefix/template_id/filename); skipping."
        )
        return None
    prefix = parts[0]
    template_id = parts[1]
    filename = "/".join(parts[2:])
    try:
        return await r2_service.download_file(
            template_id=template_id,
            filename=filename,
            prefix=prefix,
        )
    except Exception as e:
        logger.warning(f"Petition PDF R2 fetch failed for key '{url}': {e}")
        return None
