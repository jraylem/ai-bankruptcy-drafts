import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

import { Spinner } from '@/components/common/Spinner';
import type { CaseInboxEntry } from '@/types/case-inbox';

import { normalizeCaseNumber } from './formatting';

interface DismissConfirmModalProps {
  entry: CaseInboxEntry | null;
  isMutating?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirm modal for the Dismiss action. Architect-required so paralegals
 * don't mis-click destructive-feeling buttons on billable client work.
 *
 * Critical copy: dismiss is **recoverable** for ~48h via the Archived
 * tab → Summon. The copy makes this explicit so users know it's soft.
 */
export const DismissConfirmModal: React.FC<DismissConfirmModalProps> = ({
  entry,
  isMutating = false,
  onConfirm,
  onCancel,
}) => {
  // Close on Escape so keyboard-only users don't get trapped.
  useEffect(() => {
    if (!entry) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isMutating) onCancel();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [entry, isMutating, onCancel]);

  if (!entry) return null;

  const debtor = entry.case_name || 'this petition';
  const canonicalCaseNumber: string | null = normalizeCaseNumber(entry.case_number);
  const caseRef: string = canonicalCaseNumber ? ` (${canonicalCaseNumber})` : '';
  const hasMatch = entry.matched_unfiled_case != null;
  const matchedCreatedAt = entry.matched_unfiled_case
    ? new Date(entry.matched_unfiled_case.created_at).toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
      })
    : null;

  const modal = (
    <>
      <div
        className="fixed inset-0 z-[999] bg-black/40"
        onClick={isMutating ? undefined : onCancel}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="dismiss-confirm-title"
        className="fixed left-1/2 top-1/2 z-[1000] w-[min(420px,90vw)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-2xl"
      >
        <h2
          id="dismiss-confirm-title"
          className="mb-2 text-base font-semibold text-text"
        >
          Reject {debtor}{caseRef}?
        </h2>
        {entry.matched_unfiled_case && (
          <div className="mb-3 rounded border border-app-warning bg-app-warning-soft px-3 py-2 text-xs text-app-warning-text">
            <p className="mb-0.5 font-semibold">⚠ Existing unfiled case found</p>
            <p>
              An unfiled petition for{' '}
              <span className="font-semibold">
                {entry.matched_unfiled_case.case_name}
              </span>
              {matchedCreatedAt ? <> uploaded on {matchedCreatedAt}</> : null} is
              already in the system. Rejecting will still merge this court notice
              into that unfiled case (filing it) and archive the inbox entry.
              The case stays in your cases list.
            </p>
          </div>
        )}
        <p className="mb-5 text-sm text-text-secondary">
          {hasMatch
            ? <>Only the inbox notification is archived — you can reinstate it from the Archived tab anytime.</>
            : <>The petition moves to <strong>Archived</strong>. You can reinstate it from the Archived tab anytime — no data is permanently lost.</>}
        </p>
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isMutating}
            className="rounded border border-border bg-surface px-4 py-1.5 text-sm font-semibold text-text-secondary transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isMutating}
            className="inline-flex items-center gap-2 rounded bg-app-danger px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-app-danger-strong disabled:cursor-not-allowed disabled:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-danger"
          >
            {isMutating && (
              <span aria-hidden="true">
                <Spinner size="sm" className="text-white" />
              </span>
            )}
            {hasMatch
              ? (isMutating ? 'Merging…' : 'Reject merge and archive')
              : (isMutating ? 'Rejecting…' : 'Reject and archive')}
          </button>
        </div>
      </div>
    </>
  );

  return createPortal(modal, document.body);
};
