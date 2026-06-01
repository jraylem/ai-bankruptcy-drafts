/**
 * Browser-side download helpers used by the draft viewer + status strip.
 * Pure DOM primitives — no app state, no network calls.
 */

const FILENAME_MAX_LENGTH: number = 120;

function isAllowedFilenameChar(character: string): boolean {
  if (character >= 'a' && character <= 'z') return true;
  if (character >= 'A' && character <= 'Z') return true;
  if (character >= '0' && character <= '9') return true;
  if (character === '_' || character === '.' || character === '-') return true;
  return false;
}

export function sanitizeFilename(name: string): string {
  const trimmed: string = name.trim();
  let cleaned: string = '';
  let previousWasUnderscore: boolean = false;
  for (const character of trimmed) {
    if (isAllowedFilenameChar(character)) {
      cleaned += character;
      previousWasUnderscore = false;
    } else if (!previousWasUnderscore) {
      cleaned += '_';
      previousWasUnderscore = true;
    }
  }
  const bounded: string = cleaned.slice(0, FILENAME_MAX_LENGTH);
  return bounded || 'document';
}

export function triggerFileDownload(url: string, filename: string): void {
  const anchor: HTMLAnchorElement = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } catch {
    // Cross-origin `download` attribute may be ignored by some browsers when
    // the response lacks a Content-Disposition: attachment header. Fall back
    // to opening the URL in a new tab so the user at least gets the file.
    window.open(url, '_blank', 'noopener');
  } finally {
    anchor.remove();
  }
}

const BLOB_URL_REVOKE_DELAY_MS: number = 60_000;

export function triggerBlobDownload(blob: Blob, filename: string): void {
  const blobUrl: string = URL.createObjectURL(blob);
  triggerFileDownload(blobUrl, filename);
  // Delay revoke so the browser has time to read the bytes for the download.
  // 60s matches the existing pattern in features/analytics/utils/common.helpers.ts.
  window.setTimeout((): void => URL.revokeObjectURL(blobUrl), BLOB_URL_REVOKE_DELAY_MS);
}
