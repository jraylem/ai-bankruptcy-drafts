import React, { useMemo, useState } from 'react';

import type { CostsByKindEntry } from '@/types/costs';

import { CostByKindRow } from './CostByKindRow';
import { formatMoneyOrTiny } from './formatting';

interface CostByKindCardProps {
  byKind: CostsByKindEntry[];
  total: number;
}

const TOP_N = 8;

/**
 * Ranked horizontal bar list of `by_kind` rows. Top N shown explicitly,
 * remainder collapsed into one "Other (M)" row with a "Show all" disclosure
 * that expands the full list in place. Treemap / pie were ruled out
 * because long-tail kinds round to <$1 in week view and become
 * unreadable in either viz.
 */
export const CostByKindCard: React.FC<CostByKindCardProps> = ({
  byKind,
  total,
}) => {
  const [showAll, setShowAll] = useState(false);

  // BE serializes Decimal as JSON strings (e.g. "1.67"), not numbers.
  // Coerce each cost_usd via Number() before arithmetic — Number.isFinite
  // alone rejects strings, which would zero every entry out.
  const toFiniteNumber = (v: unknown): number => {
    const n = typeof v === 'number' ? v : Number(v);
    return Number.isFinite(n) ? n : 0;
  };

  const { visible, hidden, hiddenTotal } = useMemo(() => {
    if (showAll || byKind.length <= TOP_N) {
      return { visible: byKind, hidden: [], hiddenTotal: 0 };
    }
    const top = byKind.slice(0, TOP_N);
    const rest = byKind.slice(TOP_N);
    const restTotal = rest.reduce((s, r) => s + toFiniteNumber(r.cost_usd), 0);
    return { visible: top, hidden: rest, hiddenTotal: restTotal };
  }, [byKind, showAll]);

  const totalCoerced = toFiniteNumber(total);
  const totalSafe =
    totalCoerced > 0
      ? totalCoerced
      : byKind.reduce((s, r) => s + toFiniteNumber(r.cost_usd), 0) || 1;

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-text-secondary">
          Cost by activity
        </h2>
        <span className="text-xs text-muted">
          {byKind.length} {byKind.length === 1 ? 'kind' : 'kinds'}
        </span>
      </header>
      {byKind.length === 0 ? (
        <p className="text-sm text-muted">No spend in this range yet.</p>
      ) : (
        <>
          <ul role="list" className="flex flex-col gap-1">
            {visible.map((row) => (
              <CostByKindRow key={row.kind} row={row} total={totalSafe} />
            ))}
            {hidden.length > 0 && (
              <li
                role="listitem"
                aria-label={`Other ${hidden.length}: ${formatMoneyOrTiny(hiddenTotal)}`}
                className="grid grid-cols-[140px_1fr_auto] items-center gap-3 rounded py-2 text-sm text-muted"
              >
                <span className="italic">Other ({hidden.length})</span>
                <span aria-hidden="true" className="h-2 w-full" />
                <span className="font-semibold tabular-nums text-text-secondary">
                  {formatMoneyOrTiny(hiddenTotal)}
                </span>
              </li>
            )}
          </ul>
          {byKind.length > TOP_N && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="self-start text-xs font-semibold text-app-accent-text transition hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
            >
              {showAll
                ? 'Show top 8 only'
                : `Show all (${byKind.length})`}
            </button>
          )}
        </>
      )}
    </section>
  );
};
