/** Shared formatters for the v2 Case Inbox page. */

// Case-number normalization — mirrors `bkdrafts-be/src/core/components/cases/identity.py`
// regex patterns. Inbox rows store the raw value parsed out of the
// gmail/CM-ECF email body, but the firm-canonical display shape is
// 'YY-NNNNN'. This helper is the FE-side display canonicalizer (per
// Nelmin: keep BE intake untouched; normalize on read in the FE).
const CASE_WITH_CHAPTER: RegExp = /^(\d{1,2})[\s_:-](\d{2})[\s_-]bk[\s_-](\d{4,7})(?:[\s_-][A-Za-z]{2,5})?$/i;
const CASE_BK: RegExp = /^(\d{2})[\s_-]bk[\s_-](\d{4,7})(?:[\s_-][A-Za-z]{2,5})?$/i;
const CASE_SHORT: RegExp = /^(\d{2})[\s_-](\d{4,7})(?:[\s_-][A-Za-z]{2,5})?$/;

/** Canonicalize a raw case number into 'YY-NNNNN'. Returns the trimmed
 *  raw value if no known shape matches (display-safe — never throws),
 *  and `null` for empty/null/undefined input. */
export const normalizeCaseNumber = (raw: string | null | undefined): string | null => {
  if (raw === null || raw === undefined) return null;
  const value: string = raw.trim();
  if (!value) return null;

  const withChapter: RegExpMatchArray | null = value.match(CASE_WITH_CHAPTER);
  if (withChapter) {
    return `${withChapter[2]}-${withChapter[3]}`;
  }

  const bk: RegExpMatchArray | null = value.match(CASE_BK);
  if (bk) {
    return `${bk[1]}-${bk[2]}`;
  }

  const short: RegExpMatchArray | null = value.match(CASE_SHORT);
  if (short) {
    return `${short[1]}-${short[2]}`;
  }

  return value;
};

/** "Xm ago" / "Xh ago" / "Xd ago" — ambient short timestamps.
 *  Re-implemented here (not imported from cost-center) so the inbox
 *  feature doesn't take a cross-feature dependency for a 10-line helper. */
export const formatRelative = (
  iso: string | number | Date | null | undefined,
  now: number = Date.now(),
): string => {
  if (iso == null) return '';
  const ms = iso instanceof Date ? iso.getTime() : typeof iso === 'number' ? iso : Date.parse(iso);
  if (!Number.isFinite(ms)) return '';
  const diffSec = Math.max(0, Math.round((now - ms) / 1000));
  if (diffSec < 60) return 'just now';
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
};

/** Format the absolute timestamp shown on row hover. */
export const formatAbsolute = (iso: string | null | undefined): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString();
};

/** District color palette (per the architect's "small chip with color per court").
 *  Falls back to neutral for unknown districts so a new court won't crash. */
const DISTRICT_CLASSES: Record<string, string> = {
  FLMB: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  FLNB: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  FLSB: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  PAWB: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
};

export const districtChipClasses = (district: string | null | undefined): string => {
  const base =
    'inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide';
  const palette =
    DISTRICT_CLASSES[district ?? ''] ??
    'bg-surface-muted text-text-secondary';
  return `${base} ${palette}`;
};
