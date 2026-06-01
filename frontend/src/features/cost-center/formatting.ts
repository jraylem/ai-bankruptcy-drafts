/** Shared money + kind-label formatters for the cost-center page. */

const USD = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
});

const USD_TIGHT = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
});

/** Coerce inputs to a finite Number, falling back to 0 on NaN /
 *  Infinity / null / undefined / unparseable strings.
 *
 *  Important: the BE serializes `Decimal` fields as JSON STRINGS (Pydantic
 *  preserves precision that way), so cost_usd lands at the FE typed as
 *  `number` but is actually a string like "1.67" at runtime. `Number.isFinite`
 *  rejects strings entirely, so we must coerce via `Number()` FIRST and
 *  then check finiteness — otherwise every cost on the page renders $0.00. */
const safeNumber = (n: unknown): number => {
  const num = typeof n === 'number' ? n : Number(n);
  return Number.isFinite(num) ? num : 0;
};

export const formatMoney = (n: number): string => USD.format(safeNumber(n));

/** Round-to-no-cents for big projection numbers ($14,510 not $14,510.00).
 *  Falls back to cents below $1,000 so small values still read precisely. */
export const formatMoneyDisplay = (n: number): string => {
  const safe = safeNumber(n);
  if (Math.abs(safe) >= 1000) {
    return USD_TIGHT.format(Math.round(safe));
  }
  return USD.format(safe);
};

/** Tiny non-zero amounts show as `<$0.01` rather than rounded $0.00 — keeps
 *  the long tail of by-kind rows honest. */
export const formatMoneyOrTiny = (n: number): string => {
  const safe = safeNumber(n);
  if (safe > 0 && safe < 0.01) return '<$0.01';
  return USD.format(safe);
};

const KIND_LABELS: Record<string, string> = {
  chat: 'Chat',
  chat_guardrail: 'Chat guardrail',
  draft: 'Draft',
  template: 'Template',
  case_ingest: 'Case ingest',
  embeddings: 'Embeddings',
  auto_derive: 'Auto-derive',
  dropdown: 'Dropdown',
  group_dropdown: 'Group dropdown',
  reco_chips: 'Reco chips',
  user_input_heal: 'User input heal',
  explanation_enhance: 'Explanation enhance',
  extract_from_draft: 'Extract from draft',
  case_vector_vision: 'Case vector vision',
  multi_select_vision: 'Multi-select vision',
  web_search_enhance: 'Web search enhance',
};

export const labelForKind = (kind: string): string =>
  KIND_LABELS[kind] ??
  kind.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/** "Xm ago" / "Xh ago" — short, ambient timestamps for the header. */
export const formatRelative = (ms: number, now: number = Date.now()): string => {
  const diffSec = Math.max(0, Math.round((now - ms) / 1000));
  if (diffSec < 60) return 'just now';
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay}d ago`;
};
