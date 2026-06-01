/**
 * Format a raw `case_name` from the BE for display.
 *
 * Joint filings arrive as newline-separated debtors:
 *   "Ruben Soto Rodriguez\nRoxana Ivette Ampuero Rocafuerte"
 *
 * Rendered verbatim, the newline collapses into whitespace and the two
 * debtors run into each other. We join them with " and " to match the
 * legal-domain convention for joint petitions.
 */
export const formatCaseName = (caseName: string): string =>
  caseName
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
    .join(' and ');

// ─── deriveCaseInitials ───────────────────────────────────────────────

const TRAILING_CASE_NUMBER = /\s+\d{2}-\d{4,}\s*$/;
const LEADING_PREFIX = /^(in re:?|estate of)\s+/i;
const TRAILING_ENTITY_SUFFIX =
  /[\s,]+(llc|llp|inc|corp|ltd|co|pc|pllc|trust)\.?\s*$/i;
const DEBTOR_SEPARATOR = /\s*(?:&|\sand\s|;|\n)\s*/i;
// Apostrophes are deleted (so "O'Brien" stays one token).
const SEGMENT_APOSTROPHE = /[']/g;
// Other punctuation collapses to whitespace AFTER splitting. Must NOT strip
// commas (used to detect "Last, First" form) or hyphens (token-internal).
const SEGMENT_PUNCTUATION = /[./"]/g;
const HAS_LATIN_LETTER = /[A-Za-zÀ-ÿ]/;
const LATIN_LETTER_UPPER = /[A-Z]/;

const initialsCache = new Map<string, string>();

const asciiFoldLatin = (s: string): string =>
  s.normalize('NFD').replace(/\p{M}/gu, '');

const isAllCaps = (s: string): boolean =>
  LATIN_LETTER_UPPER.test(s) && s === s.toUpperCase();

const titleCaseAllCaps = (s: string): string =>
  s.replace(/\b[A-ZÀ-Þ]+\b/g, (w) => w.charAt(0) + w.slice(1).toLowerCase());

const cleanSegment = (segment: string): string =>
  segment
    .replace(SEGMENT_APOSTROPHE, '')
    .replace(SEGMENT_PUNCTUATION, ' ')
    .replace(/\s+/g, ' ')
    .trim();

// "Last, First Middle" → "First Middle Last". If no comma, return as-is.
const normalizeNameOrder = (segment: string): string => {
  if (!segment.includes(',')) return segment;
  const [last, ...rest] = segment.split(',');
  const front = rest.join(',').trim();
  if (!front) return last.trim();
  return `${front} ${last.trim()}`.trim();
};

const firstInitialOfSegment = (segment: string): string => {
  const reordered = normalizeNameOrder(cleanSegment(segment));
  const firstToken = reordered.split(/\s+/).filter(Boolean)[0] ?? '';
  return firstToken.charAt(0);
};

const pairFromSingleSegment = (segment: string): string => {
  const reordered = normalizeNameOrder(cleanSegment(segment));
  const tokens = reordered.split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return '';
  if (tokens.length >= 2) {
    return tokens[0].charAt(0) + tokens[tokens.length - 1].charAt(0);
  }
  const only = tokens[0];
  if (HAS_LATIN_LETTER.test(only)) return only.slice(0, 2);
  // Non-Latin (CJK, etc.): take first two grapheme clusters as-is.
  const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
  const graphemes: string[] = [];
  for (const g of segmenter.segment(only)) {
    graphemes.push(g.segment);
    if (graphemes.length === 2) break;
  }
  return graphemes.join('');
};

const computeInitials = (raw: string): string => {
  let s = raw.trim();
  if (!s) return '';
  s = s.replace(TRAILING_CASE_NUMBER, '');
  s = s.replace(LEADING_PREFIX, '').trim();
  // Loop the suffix strip in case a name carries multiple trailing tokens
  // ("Acme Holdings LLC Trust" → "Acme Holdings").
  let prev: string;
  do {
    prev = s;
    s = s.replace(TRAILING_ENTITY_SUFFIX, '').trim();
  } while (s !== prev);
  if (!s) return '';
  if (isAllCaps(s)) s = titleCaseAllCaps(s);
  if (HAS_LATIN_LETTER.test(s)) s = asciiFoldLatin(s);
  const segments = s.split(DEBTOR_SEPARATOR).map((x) => x.trim()).filter(Boolean);
  if (segments.length === 0) return '';
  const glyphs =
    segments.length >= 2
      ? firstInitialOfSegment(segments[0]) + firstInitialOfSegment(segments[1])
      : pairFromSingleSegment(segments[0]);
  // Preserve non-Latin scripts (CJK has no case); only uppercase ASCII/Latin.
  return glyphs.replace(/[a-zà-ÿ]/gi, (c) => c.toUpperCase());
};

/**
 * Derive up to 2 display glyphs from a `case_name` for compact avatar tiles
 * (e.g. the collapsed case sidebar). The full name remains the source of
 * truth — initials are a glance affordance, never an identifier.
 *
 * Returns "" for empty / null / whitespace-only input (caller falls back
 * to a placeholder icon).
 *
 * Examples:
 *   "John Doe"               → "JD"
 *   "John & Jane Smith"      → "JJ"
 *   "Smith, John A."         → "JS"
 *   "Acme Holdings LLC"      → "AH"
 *   "Acme"                   → "AC"
 *   "Estate of Mary O'Brien" → "MO"
 *   "김민준"                 → "김민"
 *
 * Pure + memoized per input. Safe to call inside render.
 */
export const deriveCaseInitials = (
  caseName: string | null | undefined,
): string => {
  if (!caseName) return '';
  const cached = initialsCache.get(caseName);
  if (cached !== undefined) return cached;
  const result = computeInitials(caseName);
  initialsCache.set(caseName, result);
  return result;
};
