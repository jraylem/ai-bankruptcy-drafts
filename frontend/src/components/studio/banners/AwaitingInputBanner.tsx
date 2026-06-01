import type { ReactElement } from 'react';
interface AwaitingInputBannerProps {
  kind: 'dry-run' | 'draft';
  caseName: string | null;
  pendingCount: number;
  onContinue: () => void;
  onDiscard: () => void;
}

export const AwaitingInputBanner = ({
  kind,
  caseName,
  pendingCount,
  onContinue,
  onDiscard,
}: AwaitingInputBannerProps): ReactElement => {
  const label = kind === 'draft' ? 'Draft' : 'Dry run';
  return (
    <div className="mb-4 overflow-hidden rounded-xl border border-app-accent-soft bg-app-accent-soft">
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="mt-0.5 shrink-0 rounded-md bg-indigo-100 p-1 text-app-accent-text">
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-indigo-900">
            {label} paused — we need your help
          </p>
          <p className="mt-0.5 text-xs text-app-accent-text">
            {pendingCount} input{pendingCount === 1 ? '' : 's'} required
            {caseName ? ` for ${caseName}` : ''}. Review suggestions, pick values,
            and upload any supporting documents to continue.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onContinue}
              className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-3 py-1 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700"
            >
              <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
              Continue
            </button>
            <button
              type="button"
              onClick={onDiscard}
              className="text-xs font-semibold text-app-accent-text hover:text-indigo-900"
            >
              Discard
            </button>
          </div>
        </div>
        <span className="shrink-0 rounded-md bg-indigo-600 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white">
          Input
        </span>
      </div>
    </div>
  );
};

export default AwaitingInputBanner;
