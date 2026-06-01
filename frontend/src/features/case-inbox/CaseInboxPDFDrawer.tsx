import React, { useEffect, useRef, useState } from 'react';

import { Drawer } from '@/components/common/Drawer';
import { PDFViewer } from '@/components/pdf/PDFViewer';
import { usePDFStore } from '@/stores/usePDFStore';
import type { CaseInboxEntry } from '@/types/case-inbox';

import { districtChipClasses, formatRelative, normalizeCaseNumber } from './formatting';
import { SsnBadge } from './SsnBadge';

interface CaseInboxPDFDrawerProps {
  entry: CaseInboxEntry | null;
  isOpen: boolean;
  onClose: () => void;
  onAccept: (entry: CaseInboxEntry) => void;
  onDismiss: (entry: CaseInboxEntry) => void;
  /** True while an Accept/Dismiss mutation is in flight for this entry. */
  isMutating?: boolean;
  /** Refetch the inbox list so the presigned URL is re-signed. */
  onRefetchInbox: () => void;
}

type LoadState = 'idle' | 'loading' | 'ready' | 'error';

export const CaseInboxPDFDrawer: React.FC<CaseInboxPDFDrawerProps> = ({
  entry,
  isOpen,
  onClose,
  onAccept,
  onDismiss,
  isMutating = false,
  onRefetchInbox,
}) => {
  const loadPDFFromUrl = usePDFStore((s) => s.loadPDFFromUrl);
  const clearPDF = usePDFStore((s) => s.clearPDF);
  const [loadState, setLoadState] = useState<LoadState>('idle');
  const headingId = entry ? `case-inbox-drawer-${entry.id}` : undefined;
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const pdfKey = entry ? `inbox-${entry.id}` : '';

  useEffect(() => {
    if (!isOpen || !entry || !entry.petition_pdf_url) {
      return;
    }
    let cancelled = false;
    setLoadState('loading');
    const cacheKey = `inbox-${entry.id}`;
    const displayName = entry.case_name ?? normalizeCaseNumber(entry.case_number) ?? 'Petition';
    loadPDFFromUrl(cacheKey, entry.petition_pdf_url, displayName).then((ok) => {
      if (cancelled) return;
      setLoadState(ok ? 'ready' : 'error');
    });
    return () => {
      cancelled = true;
    };
  }, [isOpen, entry, loadPDFFromUrl]);

  useEffect(() => {
    if (isOpen || !entry) return;
    clearPDF(`inbox-${entry.id}`);
    setLoadState('idle');
  }, [isOpen, entry, clearPDF]);

  if (!entry) return null;

  const isArchived = entry.status === 'archived';
  const acceptLabel = isArchived ? 'Reinstate' : 'Accept';
  const isScanned = entry.ssn_extraction_status === 'scanned_image';

  const handleRetry = () => {
    onRefetchInbox();
    if (entry.petition_pdf_url) {
      setLoadState('loading');
      loadPDFFromUrl(
        `inbox-${entry.id}`,
        entry.petition_pdf_url,
        entry.case_name ?? normalizeCaseNumber(entry.case_number) ?? 'Petition',
      ).then((ok) => setLoadState(ok ? 'ready' : 'error'));
    }
  };

  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      ariaLabelledBy={headingId}
    >
      <header className="flex items-start gap-3 border-b border-border bg-surface-muted/40 px-5 py-3">
        <div className="min-w-0 flex-1">
          <div id={headingId} className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-0.5">
            <span className="truncate text-sm font-semibold text-text" title={entry.case_name ?? undefined}>
              {entry.case_name ?? 'Unknown debtor'}
            </span>
            <span className="font-mono text-xs text-text-secondary">
              {normalizeCaseNumber(entry.case_number) ?? '—'}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
            {entry.court_district && (
              <span className={districtChipClasses(entry.court_district)}>
                {entry.court_district}
              </span>
            )}
            <span className="inline-flex items-center gap-1">
              SSN: <SsnBadge entry={entry} />
            </span>
            <span>
              Received {formatRelative(entry.received_at ?? entry.created_at) ?? '—'}
            </span>
          </div>
        </div>
        <button
          ref={closeBtnRef}
          type="button"
          onClick={onClose}
          aria-label="Close PDF viewer"
          className="rounded p-1 text-subtle hover:bg-surface hover:text-text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </header>

      {isScanned && (
        <div
          role="note"
          className="border-b border-amber-200 bg-amber-50 px-5 py-2 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-200"
        >
          Scanned PDF — text search will not work. Review the document visually before accepting.
        </div>
      )}

      <div className="flex-1 overflow-hidden" aria-busy={loadState === 'loading'}>
        {loadState === 'error' ? (
          <div
            role="alert"
            className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center"
          >
            <p className="text-sm text-text-secondary">
              This petition link couldn't be loaded. It may have expired.
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRetry}
                className="rounded bg-app-accent px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-app-accent-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
              >
                Try again
              </button>
              {entry.petition_pdf_url && (
                <a
                  href={entry.petition_pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary hover:bg-surface-muted"
                >
                  Open in new tab
                </a>
              )}
            </div>
          </div>
        ) : (
          <PDFViewer pdfKey={pdfKey} showPageJumpInput />
        )}
      </div>

      <footer className="flex items-center justify-between gap-3 border-t border-border bg-surface-muted/40 px-5 py-3">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-border bg-surface px-3 py-1 text-xs font-semibold text-text-secondary transition hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
        >
          Close
        </button>
        <div className="flex items-center gap-3">
          {!isArchived && (
            <button
              type="button"
              onClick={() => onDismiss(entry)}
              disabled={isMutating}
              className="rounded border border-app-danger-border bg-app-danger-soft px-3 py-1 text-xs font-semibold text-app-danger-text transition hover:bg-app-danger-soft/70 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-danger"
            >
              Reject…
            </button>
          )}
          <button
            type="button"
            onClick={() => onAccept(entry)}
            disabled={isMutating}
            className="rounded bg-app-accent px-3 py-1 text-xs font-semibold text-white shadow-sm transition hover:bg-app-accent-strong disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
          >
            {acceptLabel}
          </button>
        </div>
      </footer>
    </Drawer>
  );
};
