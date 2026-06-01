import { useEffect, useMemo, useState } from 'react';
import { FiSearch, FiX } from 'react-icons/fi';
import { Modal } from '@/components/common';
import { cn } from '@/utils';
import { listCases } from '@/services/studio.service';
import type { CaseResponse } from '@/types/studio/resolution';

interface CasePickerModalProps {
  isOpen: boolean;
  templateName: string;
  onPick: (caseRow: CaseResponse) => void;
  onClose: () => void;
}

/**
 * Modal that loads the firm's cases on mount, lets the paralegal
 * search by name / case_number / district, and returns the picked
 * case to the caller via `onPick`.
 *
 * Re-fetches every time the modal opens (no client-side cache) — the
 * case list changes when paralegals upload new petitions and the
 * dry-run flow needs fresh data every time.
 */
export const CasePickerModal = ({
  isOpen,
  templateName,
  onPick,
  onClose,
}: CasePickerModalProps) => {
  const [cases, setCases] = useState<CaseResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    setError(null);
    setQuery('');
    setLoading(true);
    let cancelled = false;
    void (async () => {
      const { data, error: apiError } = await listCases({ limit: 100 });
      if (cancelled) return;
      setLoading(false);
      if (apiError || !data) {
        setError(apiError ?? 'Failed to load cases');
        setCases([]);
        return;
      }
      setCases(data.cases);
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter((c) => {
      const haystack = [
        c.case_name,
        c.case_number,
        c.case_number_original ?? '',
        c.court_district ?? '',
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [cases, query]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="xl"
      closeOnBackdropClick={!loading}
    >
      <div className="flex max-h-[min(80vh,720px)] flex-col">
        <header className="shrink-0 border-b border-border px-6 py-5 pr-12">
          <p className="text-xs font-semibold uppercase tracking-wider text-app-accent-text">
            Test against a case
          </p>
          <h2
            className="mt-1 truncate text-lg font-semibold text-text-secondary"
            title={templateName}
          >
            {templateName}
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            Pick a case to run the template against. Nothing is saved — this
            is a dry-run that shows you exactly what the AI extracts and how
            the document will read at draft time.
          </p>
        </header>

        <div className="shrink-0 border-b border-border px-6 py-3">
          <div className="relative">
            <FiSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by debtor name, case number, or district…"
              className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-9 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 cursor-pointer rounded p-1 text-subtle hover:bg-surface-muted hover:text-text-secondary"
                aria-label="Clear search"
              >
                <FiX className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {loading && (
            <div className="flex h-32 items-center justify-center text-sm text-subtle">
              <span className="inline-flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-app-accent/30 border-t-app-accent" />
                Loading cases…
              </span>
            </div>
          )}

          {error && !loading && (
            <div className="mx-3 my-4 rounded-lg border border-app-danger-text/30 bg-app-danger-text/5 p-3 text-sm text-app-danger-text">
              {error}
            </div>
          )}

          {!loading && !error && filtered.length === 0 && (
            <div className="flex h-32 flex-col items-center justify-center gap-1 text-sm text-subtle">
              <p>{query ? 'No matches.' : 'No cases on file yet.'}</p>
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="cursor-pointer text-xs text-app-accent-text hover:underline"
                >
                  Clear search
                </button>
              )}
            </div>
          )}

          {!loading && !error && filtered.length > 0 && (
            <ul className="space-y-1">
              {filtered.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => onPick(c)}
                    className={cn(
                      'flex w-full cursor-pointer items-center justify-between gap-3 rounded-lg border border-transparent px-3 py-2.5 text-left transition-colors',
                      'hover:border-app-accent/40 hover:bg-app-accent-soft/30',
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-text-secondary">
                        {c.case_name}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-subtle">
                        <span className="font-mono">{c.case_number}</span>
                        {c.court_district && (
                          <span> · {c.court_district}</span>
                        )}
                        {c.chapter !== null && (
                          <span> · Ch. {c.chapter}</span>
                        )}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-md border border-app-accent/30 bg-app-accent-soft/40 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
                      Test
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-surface-muted/40 px-6 py-3">
          <p className="text-[11px] italic text-subtle">
            {filtered.length > 0 &&
              !loading &&
              `${filtered.length} case${filtered.length === 1 ? '' : 's'} shown.`}
          </p>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded-lg border border-border bg-surface px-3.5 py-1.5 text-sm font-medium text-text-secondary hover:bg-surface-muted"
          >
            Cancel
          </button>
        </footer>
      </div>
    </Modal>
  );
};
