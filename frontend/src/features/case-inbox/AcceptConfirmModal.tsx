import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';

import { Spinner } from '@/components/common/Spinner';
import type { CaseInboxEntry } from '@/types/case-inbox';

import { normalizeCaseNumber } from './formatting';

interface AcceptConfirmModalProps {
  entry: CaseInboxEntry | null;
  isMutating?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirm modal for the Accept (and Summon) action. Parity with
 * DismissConfirmModal — paralegals can't fat-finger a case creation
 * from the inbox. Copy makes clear that Accept creates a real Case row
 * and opens the drafting workspace; Summon (archived) recovers and
 * promotes the petition.
 */
export const AcceptConfirmModal: React.FC<AcceptConfirmModalProps> = ({
  entry,
  isMutating = false,
  onConfirm,
  onCancel,
}) => {
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
  const isArchived = entry.status === 'archived';
  const hasMatch = entry.matched_unfiled_case != null;
  const title = isArchived
    ? `Reinstate ${debtor}${caseRef}?`
    : `Accept ${debtor}${caseRef}?`;
  // When the matcher found an unfiled counterpart, the Accept action
  // merges this court notice INTO that existing case rather than
  // creating a new one. Body + button label flip to reflect that.
  const body = hasMatch
    ? 'This court notice will merge into the existing unfiled case (filing it) and open the drafting workspace.'
    : (isArchived
      ? 'This creates a new case from the archived petition and opens the drafting workspace.'
      : 'This creates a new case in the drafting workspace and removes the petition from the Inbox.');
  const confirmLabel = hasMatch
    ? (isMutating ? 'Merging…' : 'Accept merge and open')
    : (isArchived
      ? (isMutating ? 'Reinstating…' : 'Reinstate and open')
      : (isMutating ? 'Accepting…' : 'Accept and open'));

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
        aria-labelledby="accept-confirm-title"
        className="fixed left-1/2 top-1/2 z-[1000] w-[min(440px,90vw)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-2xl"
      >
        <h2
          id="accept-confirm-title"
          className="mb-2 text-base font-semibold text-text"
        >
          {title}
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
              already in the system. Accepting will merge this court notice into
              that unfiled case (filing it) and open the drafting workspace.
            </p>
          </div>
        )}
        <p className="mb-2 text-sm text-text-secondary">{body}</p>
        {isMutating && (
          <p
            role="status"
            aria-live="polite"
            className="mb-3 inline-flex items-center gap-2 text-xs text-muted"
          >
            <span aria-hidden="true">
              <Spinner size="sm" className="text-app-accent" />
            </span>
            Reading the petition and setting up your case workspace. We'll open it as soon as it's ready.
          </p>
        )}
        <div className="mt-3 flex items-center justify-end gap-2">
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
            className="inline-flex items-center gap-2 rounded bg-app-accent px-4 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-app-accent-strong disabled:cursor-not-allowed disabled:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
          >
            {isMutating && (
              <span aria-hidden="true">
                <Spinner size="sm" className="text-white" />
              </span>
            )}
            {confirmLabel}
          </button>
        </div>
      </div>
    </>
  );

  return createPortal(modal, document.body);
};
