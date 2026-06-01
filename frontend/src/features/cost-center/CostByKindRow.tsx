import React, { useState } from 'react';

import type { CostsByKindEntry } from '@/types/costs';

import { formatMoneyOrTiny, labelForKind } from './formatting';

interface CostByKindRowProps {
  row: CostsByKindEntry;
  total: number;
}

/** One ranked-list row: label · proportional bar · $value + %. Hover /
 *  focus reveals input/output token counts for debugging. */
export const CostByKindRow: React.FC<CostByKindRowProps> = ({ row, total }) => {
  const [showTokens, setShowTokens] = useState(false);
  const pct = total > 0 ? (row.cost_usd / total) * 100 : 0;
  const label = labelForKind(row.kind);

  return (
    <li
      role="listitem"
      aria-label={`${label}: ${formatMoneyOrTiny(row.cost_usd)}, ${pct.toFixed(0)} percent of total`}
      onMouseEnter={() => setShowTokens(true)}
      onMouseLeave={() => setShowTokens(false)}
      onFocus={() => setShowTokens(true)}
      onBlur={() => setShowTokens(false)}
      tabIndex={0}
      className="grid grid-cols-[140px_1fr_auto] items-center gap-3 rounded py-2 transition focus-within:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent hover:bg-surface-muted/50"
    >
      <span
        className="truncate text-sm text-text-secondary"
        title={label}
      >
        {label}
      </span>
      <div className="flex flex-col gap-1">
        <span
          aria-hidden="true"
          className="h-2 w-full overflow-hidden rounded-full bg-app-accent-soft"
        >
          <span
            className="block h-full rounded-full bg-app-accent transition-[width] motion-reduce:transition-none"
            style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
          />
        </span>
        {showTokens && (
          <span className="text-[10px] tabular-nums text-subtle">
            in: {row.input_tokens.toLocaleString()} · out: {row.output_tokens.toLocaleString()}
          </span>
        )}
      </div>
      <span className="flex flex-col items-end gap-0.5 tabular-nums">
        <span className="text-sm font-semibold text-text-secondary">
          {formatMoneyOrTiny(row.cost_usd)}
        </span>
        <span className="text-[10px] text-subtle">{pct.toFixed(0)}%</span>
      </span>
    </li>
  );
};
