import { useEffect, useState, type ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';

const AUTO_DISMISS_MS = 10_000;

interface DryRunResultBannerProps {
  onJumpToVariable?: (propertyName: string) => void;
}

const extractVariableName = (warning: string): string | null => {
  const placeholderMatch = warning.match(/\[\[(.+?)\]\]/);
  if (placeholderMatch) return placeholderMatch[1];
  const quotedMatch = warning.match(/'([^']+)'/);
  if (quotedMatch) return quotedMatch[1];
  return null;
};

export const DryRunResultBanner = ({ onJumpToVariable }: DryRunResultBannerProps): ReactElement | null => {
  const dryRunResult = useStudioStore((state) => state.dryRunResult);
  const [warningsExpanded, setWarningsExpanded] = useState(false);
  // Local-only banner visibility — separate from the store's dryRunResult so
  
  const [isBannerHidden, setIsBannerHidden] = useState(false);

  const warningCount = dryRunResult?.validation.warnings.length ?? 0;
  const hasWarnings = warningCount > 0;

  useEffect(() => {
    setIsBannerHidden(false);
  }, [dryRunResult]);

  useEffect(() => {
    if (!dryRunResult || hasWarnings || isBannerHidden) return;
    const id = window.setTimeout(() => setIsBannerHidden(true), AUTO_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [dryRunResult, hasWarnings, isBannerHidden]);

  if (!dryRunResult || isBannerHidden) return null;

  const resolvedCount = dryRunResult.resolved_values.filter((rv) => rv.value).length;
  const totalCount = dryRunResult.resolved_values.length;

  const containerClass = hasWarnings
    ? 'mb-4 overflow-hidden rounded-xl border border-app-warning-soft bg-app-warning-soft'
    : 'mb-4 overflow-hidden rounded-xl border border-app-success-soft bg-app-success-soft';
  const iconClass = hasWarnings ? 'mt-0.5 shrink-0 text-app-warning-text' : 'mt-0.5 shrink-0 text-app-success-text';
  const titleClass = hasWarnings ? 'text-sm font-semibold text-amber-900' : 'text-sm font-semibold text-emerald-900';
  const dismissClass = hasWarnings
    ? 'shrink-0 text-app-warning-text hover:text-amber-900'
    : 'shrink-0 text-app-success-text hover:text-emerald-900';
  const expandedBorderClass = hasWarnings
    ? 'border-t border-app-warning-soft bg-surface px-4 py-3'
    : 'border-t border-app-success-soft bg-surface px-4 py-3';

  return (
    <div className={containerClass}>
      <div className="flex items-start gap-3 px-4 py-3">
        <div className={iconClass}>
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {hasWarnings ? (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
              />
            ) : (
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
              />
            )}
          </svg>
        </div>

        <div className="min-w-0 flex-1">
          <p className={titleClass}>
            Dry run complete — {resolvedCount} of {totalCount} values resolved
            {hasWarnings && ` · ${warningCount} warning${warningCount === 1 ? '' : 's'}`}
          </p>
          {hasWarnings && (
            <div className="mt-1 flex items-center gap-3 text-xs">
              <button
                type="button"
                onClick={() => setWarningsExpanded(!warningsExpanded)}
                className="font-semibold text-app-warning-text hover:text-amber-900"
              >
                {warningsExpanded ? 'Hide' : 'Show'} warnings
              </button>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsBannerHidden(true)}
          className={dismissClass}
          aria-label="Dismiss banner"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {warningsExpanded && hasWarnings && (
        <div className={expandedBorderClass}>
          <ul className="space-y-1 text-xs text-text-secondary">
            {dryRunResult.validation.warnings.map((warning, idx) => {
              const variableName = extractVariableName(warning);
              const isClickable = !!variableName && !!onJumpToVariable;
              return (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-amber-500">⚠</span>
                  {isClickable ? (
                    <button
                      type="button"
                      onClick={() => onJumpToVariable!(variableName!)}
                      className="text-left text-text-secondary underline-offset-2 hover:text-app-accent-text hover:underline"
                    >
                      {warning}
                    </button>
                  ) : (
                    <span>{warning}</span>
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

export default DryRunResultBanner;
