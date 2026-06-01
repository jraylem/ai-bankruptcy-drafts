
const MONTH_FULL = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;

const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

const MONTH_FULL_RE = MONTH_FULL.join('|');
const MONTH_ABBR_RE = MONTH_ABBR.join('|');

export interface DetectedDateFormat {
  strftime: string;
  start: number;
  end: number;
  sampleIso: string;
}

interface PatternDef {
  regex: RegExp;
  strftime: string;
  parse: (m: RegExpMatchArray) => Date | null;
}

const safeDate = (year: number, monthIdx: number, day: number): Date | null => {
  if (Number.isNaN(year) || Number.isNaN(monthIdx) || Number.isNaN(day)) return null;
  if (monthIdx < 0 || monthIdx > 11) return null;
  if (day < 1 || day > 31) return null;
  if (year < 1900 || year > 2200) return null;
  const dt = new Date(Date.UTC(year, monthIdx, day));
  if (
    dt.getUTCFullYear() !== year ||
    dt.getUTCMonth() !== monthIdx ||
    dt.getUTCDate() !== day
  ) {
    return null;
  }
  return dt;
};

const PATTERNS: PatternDef[] = [
  {
    regex: new RegExp(`\\b(${MONTH_FULL_RE})\\s+(\\d{1,2}),\\s+(\\d{4})\\b`),
    strftime: '%B %-d, %Y',
    parse: (m) =>
      safeDate(parseInt(m[3]!, 10), MONTH_FULL.indexOf(m[1] as typeof MONTH_FULL[number]), parseInt(m[2]!, 10)),
  },
  {
    regex: new RegExp(`\\b(${MONTH_ABBR_RE})\\s+(\\d{1,2}),\\s+(\\d{4})\\b`),
    strftime: '%b %-d, %Y',
    parse: (m) =>
      safeDate(parseInt(m[3]!, 10), MONTH_ABBR.indexOf(m[1] as typeof MONTH_ABBR[number]), parseInt(m[2]!, 10)),
  },
  {
    regex: new RegExp(`\\b(\\d{1,2})\\s+(${MONTH_FULL_RE})\\s+(\\d{4})\\b`),
    strftime: '%-d %B %Y',
    parse: (m) =>
      safeDate(parseInt(m[3]!, 10), MONTH_FULL.indexOf(m[2] as typeof MONTH_FULL[number]), parseInt(m[1]!, 10)),
  },
  {
    regex: /\b(\d{2})\/(\d{2})\/(\d{4})\b/,
    strftime: '%m/%d/%Y',
    parse: (m) => safeDate(parseInt(m[3]!, 10), parseInt(m[1]!, 10) - 1, parseInt(m[2]!, 10)),
  },
  {
    regex: /\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b/,
    strftime: '%-m/%-d/%Y',
    parse: (m) => safeDate(parseInt(m[3]!, 10), parseInt(m[1]!, 10) - 1, parseInt(m[2]!, 10)),
  },
  {
    regex: /\b(\d{4})-(\d{2})-(\d{2})\b/,
    strftime: '%Y-%m-%d',
    parse: (m) => safeDate(parseInt(m[1]!, 10), parseInt(m[2]!, 10) - 1, parseInt(m[3]!, 10)),
  },
];

const ORDINAL_REJECT_RE = new RegExp(
  `\\b(?:${MONTH_FULL_RE}|${MONTH_ABBR_RE})\\s+\\d{1,2}(?:st|nd|rd|th)\\b`,
  'i',
);

export const detectDateFormat = (
  example: string | null | undefined,
): DetectedDateFormat | null => {
  if (!example) return null;
  if (ORDINAL_REJECT_RE.test(example)) return null;

  for (const p of PATTERNS) {
    const match = p.regex.exec(example);
    if (!match) continue;
    const dt = p.parse(match);
    if (!dt) continue;
    return {
      strftime: p.strftime,
      start: match.index,
      end: match.index + match[0].length,
      sampleIso: dt.toISOString().slice(0, 10),
    };
  }
  return null;
};
