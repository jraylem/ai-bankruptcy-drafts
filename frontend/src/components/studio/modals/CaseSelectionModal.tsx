import { useEffect, useMemo, useState, type ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';
import type { CaseResponse } from '@/types/studio';
import { formatCaseName } from '@/utils/studio/caseName';

interface CaseSelectionModalProps {
  isOpen: boolean;
  title: string;
  confirmLabel: string;
  isRunning: boolean;
  onClose: () => void;
  onConfirm: (caseId: string) => void;
}

export const CaseSelectionModal = ({
  isOpen,
  title,
  confirmLabel,
  isRunning,
  onClose,
  onConfirm,
}: CaseSelectionModalProps): ReactElement | null => {
  const cases = useStudioStore((state) => state.cases);
  const selectedCaseId = useStudioStore((state) => state.selectedCaseId);
  const selectCase = useStudioStore((state) => state.selectCase);

  const [picked, setPicked] = useState<string | null>(selectedCaseId);
  const [query, setQuery] = useState<string>('');

  useEffect((): void => {
    if (isOpen) setPicked(selectedCaseId);
  }, [isOpen, selectedCaseId]);

  const filtered = useMemo((): CaseResponse[] => {
    const q = query.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter((c) => {
      if (c.case_number.toLowerCase().includes(q)) return true;
      if (!c.case_name) return false;
      // Match against the raw value (catches single-debtor names + each
      // debtor of a joint filing) AND the formatted "<a> and <b>" form
      // (so typing "leonardo and beatriz" finds joint cases).
      const lower = c.case_name.toLowerCase();
      if (lower.includes(q)) return true;
      return formatCaseName(c.case_name).toLowerCase().includes(q);
    });
  }, [cases, query]);

  if (!isOpen) return null;

  const handleConfirm = (): void => {
    if (!picked) return;
    selectCase(picked);
    onConfirm(picked);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-xl bg-surface shadow-2xl">
        <header className="flex items-start justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-text-secondary">{title}</h2>
            <p className="mt-0.5 text-xs text-muted">
              Pick which case the template should resolve against.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-subtle hover:bg-surface-muted hover:text-text-secondary"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        <div className="border-b border-border px-6 py-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by case number or debtor name…"
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
        </div>

        <div className="h-72 overflow-y-auto px-3 py-2">
          {filtered.length === 0 ? (
            <p className="px-3 py-6 text-center text-xs text-subtle">
              {cases.length === 0
                ? 'No cases yet — ingest a petition first.'
                : 'No cases match that search.'}
            </p>
          ) : (
            <ul className="space-y-1">
              {filtered.map((c) => {
                const isPicked = picked === c.id;
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => setPicked(c.id)}
                      className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors ${
                        isPicked
                          ? 'border-indigo-300 bg-app-accent-soft'
                          : 'border-transparent hover:bg-surface-muted'
                      }`}
                    >
                      <div className="min-w-0">
                        <p className={`truncate text-sm font-semibold ${isPicked ? 'text-indigo-900' : 'text-text-secondary'}`}>
                          {c.case_name ? formatCaseName(c.case_name) : 'Unnamed case'}
                        </p>
                        <p className="text-xs text-muted">{c.case_number}</p>
                      </div>
                      {isPicked && (
                        <svg className="h-4 w-4 shrink-0 text-app-accent-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border px-6 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs text-muted hover:bg-surface-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!picked || isRunning}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRunning ? 'Running…' : confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  );
};

export default CaseSelectionModal;
