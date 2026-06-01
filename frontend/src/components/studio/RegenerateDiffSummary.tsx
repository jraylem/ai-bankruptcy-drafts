import { useState, type ReactElement } from 'react';
import type { RegenerateDiff } from '@/types/studio';

/**
 * Diff summary surfaced after a successful regenerate (Variant B).
 *
 * Three sections:
 *   - Added (n)     → all variables the agent introduced this pass.
 *                     Highlighted in amber since the user didn't request
 *                     these — they're drift to audit.
 *   - Removed (n)   → baseline variables missing from the new spec. Each
 *                     entry carries a reason annotation: "merged into X",
 *                     "ignored", or "unexpected drop" (the last one also
 *                     surfaces in amber as drift).
 *   - Preserved (n) → intersection. Collapsed to first 3 + "+N more"
 *                     expander to keep the modal scan-friendly.
 */

interface RegenerateDiffSummaryProps {
  diff: RegenerateDiff;
  /** Optional close handler. When provided, the summary renders an
   * × button so the author can dismiss after auditing. The studio
   * page wires this to `clearRegenerateDiff` in the store. */
  onDismiss?: () => void;
}

const COLLAPSED_PRESERVED = 3;

export const RegenerateDiffSummary = ({
  diff,
  onDismiss,
}: RegenerateDiffSummaryProps): ReactElement => {
  const [preservedExpanded, setPreservedExpanded] = useState<boolean>(false);
  const overflow = Math.max(0, diff.preserved.length - COLLAPSED_PRESERVED);
  const visiblePreserved = preservedExpanded
    ? diff.preserved
    : diff.preserved.slice(0, COLLAPSED_PRESERVED);

  const isEmpty =
    diff.added.length === 0 &&
    diff.removed.length === 0 &&
    diff.preserved.length === 0;

  if (isEmpty) {
    return (
      <div className="flex items-start gap-2.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-xs text-emerald-900">
        <svg
          className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
        <p className="flex-1 leading-relaxed">
          Template regenerated — no changes. All variables preserved.
        </p>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss"
            className="shrink-0 rounded p-0.5 text-emerald-700 hover:bg-emerald-100"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface ring-1 ring-inset ring-slate-100">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <svg
          className="h-4 w-4 text-emerald-600"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
        <p className="flex-1 text-sm font-semibold text-text-secondary">
          Template regenerated. Changes vs previous spec:
        </p>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss"
            className="shrink-0 rounded p-1 text-subtle hover:bg-surface-muted hover:text-text-secondary"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="flex flex-col gap-4 px-4 py-3">
        {/* ADDED */}
        {diff.added.length > 0 && (
          <section>
            <div className="mb-1.5 flex items-center gap-2">
              <h4 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-amber-700">
                Added ({diff.added.length})
              </h4>
              <span className="rounded-full bg-app-warning-soft px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-800">
                unrequested
              </span>
            </div>
            <p className="mb-2 text-[11px] text-amber-800">
              Agent spotted these in the document. You didn't ask for them —
              ignore on next pass if unwanted.
            </p>
            <ul className="space-y-1">
              {diff.added.map((name) => (
                <li
                  key={name}
                  className="flex items-center gap-2 rounded-md bg-app-warning-soft/60 px-2.5 py-1 text-xs"
                >
                  <span className="font-mono text-amber-700">+</span>
                  <code className="font-mono text-amber-900">{name}</code>
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* REMOVED */}
        {diff.removed.length > 0 && (
          <section>
            <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              Removed ({diff.removed.length})
            </h4>
            <ul className="space-y-1">
              {diff.removed.map((entry) => {
                const isDrift = entry.reason === 'unexpected';
                return (
                  <li
                    key={entry.name}
                    className={`flex flex-wrap items-center gap-2 rounded-md px-2.5 py-1 text-xs ${
                      isDrift
                        ? 'bg-app-warning-soft/60 text-amber-900'
                        : 'bg-surface-muted text-text-secondary'
                    }`}
                  >
                    <span
                      className={`font-mono ${
                        isDrift ? 'text-amber-700' : 'text-muted'
                      }`}
                    >
                      −
                    </span>
                    <code
                      className={`font-mono ${
                        isDrift ? 'text-amber-900' : 'text-text-secondary'
                      }`}
                    >
                      {entry.name}
                    </code>
                    <span className="text-[10px] text-subtle">
                      {entry.reason === 'merged' && entry.merged_into && (
                        <>
                          merged into{' '}
                          <code className="font-mono text-muted">
                            {entry.merged_into}
                          </code>
                        </>
                      )}
                      {entry.reason === 'ignored' && 'ignored'}
                      {entry.reason === 'unexpected' && (
                        <span className="font-semibold text-amber-700">
                          unexpected drop
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {/* PRESERVED */}
        {diff.preserved.length > 0 && (
          <section>
            <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              Preserved ({diff.preserved.length})
            </h4>
            <div className="flex flex-wrap items-center gap-1.5">
              {visiblePreserved.map((name) => (
                <code
                  key={name}
                  className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] text-muted"
                >
                  {name}
                </code>
              ))}
              {overflow > 0 && !preservedExpanded && (
                <button
                  type="button"
                  onClick={() => setPreservedExpanded(true)}
                  className="rounded px-1.5 py-0.5 text-[10px] font-semibold text-app-accent-text hover:bg-app-accent-soft"
                >
                  +{overflow} more
                </button>
              )}
              {preservedExpanded && (
                <button
                  type="button"
                  onClick={() => setPreservedExpanded(false)}
                  className="rounded px-1.5 py-0.5 text-[10px] font-semibold text-app-accent-text hover:bg-app-accent-soft"
                >
                  collapse
                </button>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default RegenerateDiffSummary;
