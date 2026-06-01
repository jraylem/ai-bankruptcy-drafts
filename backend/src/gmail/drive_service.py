"""
Google Drive retrieval for archived petitions and document templates.

Flow:
  1. Search "Archived Petitions" folder by case number (and optionally debtor name)
  2. Download matching file to local uploads/
  3. Delete the file from Drive after successful download
"""

import io
import re
import tempfile
from pathlib import Path
from typing import Optional

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
DRIVE_FOLDER_NAME = "Archived Petitions"


def _get_drive_folder_id(service, folder_name: str) -> Optional[str]:
    """Return the Drive folder ID for the given folder name, or None if not found."""
    result = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
        pageSize=1,
    ).execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def _normalize_for_search(case_number: str) -> list[str]:
    """Return variants of the case number useful for filename matching."""
    variants = [case_number.strip()]
    # XX-XXXXX → also try with underscore (as stored in filenames)
    variants.append(case_number.strip().replace(":", "_"))
    # Short form: 3:26-bk-00635 → 26-00635
    short = re.sub(r"^\d+[:\-]\d{2}-bk-0*", "", case_number)
    if short and short != case_number:
        variants.append(short)
    return list(dict.fromkeys(v for v in variants if v))


def download_docx_template(file_id: str) -> Optional[Path]:
    """
    Download a Google Drive file as a .docx to a temp file.

    Handles both Google Docs (exported via files().export) and regular .docx
    files uploaded to Drive (downloaded via files().get_media).

    Returns the local Path to the temp .docx, or None on failure.
    """
    try:
        from .auth import get_drive_service
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as e:
        print(f"[drive] Google Drive libraries not available: {e}")
        return None

    try:
        service = get_drive_service()
    except Exception as e:
        print(f"[drive] Failed to authenticate Drive API: {e}")
        return None

    try:
        meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
        mime = meta.get("mimeType", "")

        buffer = io.BytesIO()
        if mime == "application/vnd.google-apps.document":
            # Google Docs file — export as .docx
            request = service.files().export(
                fileId=file_id,
                mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        else:
            # Regular .docx uploaded directly to Drive
            request = service.files().get_media(fileId=file_id)

        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp.write(buffer.getvalue())
        tmp.close()
        print(f"[drive] Downloaded template '{meta.get('name')}' ({file_id}) to {tmp.name}")
        return Path(tmp.name)
    except Exception as e:
        print(f"[drive] Failed to download template {file_id}: {e}")
        return None


def list_archived_petition_filenames() -> list[str]:
    """
    Return the filenames of all files currently in the "Archived Petitions"
    Drive folder. Handles pagination. Returns an empty list on any error.
    """
    try:
        from .auth import get_drive_service
    except ImportError:
        return []

    try:
        service = get_drive_service()
    except Exception as e:
        print(f"[drive] Failed to authenticate Drive API: {e}")
        return []

    folder_id = _get_drive_folder_id(service, DRIVE_FOLDER_NAME)
    if not folder_id:
        print(f"[drive] Folder '{DRIVE_FOLDER_NAME}' not found in Drive")
        return []

    filenames: list[str] = []
    page_token = None

    while True:
        kwargs = dict(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(name)",
            pageSize=1000,
        )
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.files().list(**kwargs).execute()
        filenames.extend(f["name"] for f in result.get("files", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return filenames


def retrieve_petition_from_drive(
    case_number: str,
    debtor_name: Optional[str] = None,
) -> Optional[Path]:
    """
    Search Google Drive "Archived Petitions" folder for a petition matching
    the given case number, download it locally, delete it from Drive.

    Returns the local Path to the downloaded file, or None if not found.
    """
    try:
        from .auth import get_drive_service
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as e:
        print(f"[drive] Google Drive libraries not available: {e}")
        return None

    try:
        service = get_drive_service()
    except Exception as e:
        print(f"[drive] Failed to authenticate Drive API: {e}")
        return None

    # Locate the "Archived Petitions" folder
    folder_id = _get_drive_folder_id(service, DRIVE_FOLDER_NAME)
    if not folder_id:
        print(f"[drive] Folder '{DRIVE_FOLDER_NAME}' not found in Drive")
        return None

    # Build search query — match case number variants in filename
    variants = _normalize_for_search(case_number)
    name_clauses = " or ".join(f"name contains '{v}'" for v in variants)
    query = f"({name_clauses}) and '{folder_id}' in parents and trashed=false and mimeType='application/pdf'"

    result = service.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=10,
    ).execute()
    files = result.get("files", [])

    if not files and debtor_name:
        # Fallback: search by debtor name fragment
        safe_name = debtor_name.strip().split()[0] if debtor_name.strip() else ""
        if safe_name:
            query2 = f"name contains '{safe_name}' and '{folder_id}' in parents and trashed=false and mimeType='application/pdf'"
            result2 = service.files().list(q=query2, fields="files(id, name)", pageSize=10).execute()
            files = result2.get("files", [])

    if not files:
        print(f"[drive] No petition found in Drive for case number '{case_number}'")
        return None

    file_meta = files[0]
    file_id = file_meta["id"]
    filename = file_meta["name"]
    print(f"[drive] Found petition in Drive: {filename}")

    # Download to uploads/active/ — these are petitions for active cases.
    dest_path = UPLOADS_DIR / "active" / filename
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    dest_path.write_bytes(buffer.getvalue())
    print(f"[drive] Downloaded {filename} to {dest_path}")

    # Delete from Drive after successful download
    try:
        service.files().delete(fileId=file_id).execute()
        print(f"[drive] Deleted {filename} from Drive")
    except Exception as e:
        print(f"[drive] Warning: failed to delete {filename} from Drive: {e}")

    return dest_path
