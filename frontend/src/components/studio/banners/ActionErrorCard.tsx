import type { ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';

interface ActionErrorCardProps {
  onJumpToVariable?: (propertyName: string) => void;
}

const extractVariableName = (entry: string): string | null => {
  const match = entry.match(/'([^']+)'/);
  return match ? match[1] : null;
};

export const ActionErrorCard = ({ onJumpToVariable }: ActionErrorCardProps): ReactElement | null => {
  const actionError = useStudioStore((state) => state.actionError);
  const isDryRunning = useStudioStore((state) => state.isDryRunning);
  const isSaving = useStudioStore((state) => state.isSaving);
  const retryLastAction = useStudioStore((state) => state.retryLastAction);
  const clearActionError = useStudioStore((state) => state.clearActionError);

  if (!actionError) return null;

  const isRetrying = isDryRunning || isSaving;
  const actionLabel = actionError.kind === 'dry-run' ? 'Dry run' : 'Save';

  return (
    <div className="overflow-hidden rounded-xl border border-app-danger-soft bg-app-danger-soft">
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="mt-0.5 shrink-0 text-app-danger-text">
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
            />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-red-900">{actionLabel} failed</p>
          <p className="mt-0.5 text-xs text-app-danger-text">{actionError.message}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => retryLastAction()}
            disabled={isRetrying}
            className="flex items-center gap-1 rounded-lg border border-red-300 bg-surface px-3 py-1.5 text-xs font-semibold text-app-danger-text hover:bg-app-danger-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRetrying && (
              <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            )}
            Retry
          </button>
          <button
            type="button"
            onClick={clearActionError}
            className="text-app-danger-text hover:text-red-900"
            aria-label="Dismiss"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {actionError.validationErrors && actionError.validationErrors.length > 0 && (
        <div className="border-t border-app-danger-soft bg-surface px-4 py-3">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-app-danger-text">
            Per-variable issues
          </p>
          <ul className="space-y-1 text-xs text-text-secondary">
            {actionError.validationErrors.map((entry, idx) => {
              const variableName = extractVariableName(entry);
              const isClickable = !!variableName && !!onJumpToVariable;
              return (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-red-500">×</span>
                  {isClickable ? (
                    <button
                      type="button"
                      onClick={() => onJumpToVariable!(variableName!)}
                      className="text-left text-text-secondary underline-offset-2 hover:text-app-accent-text hover:underline"
                    >
                      {entry}
                    </button>
                  ) : (
                    <span>{entry}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
};

export default ActionErrorCard;
