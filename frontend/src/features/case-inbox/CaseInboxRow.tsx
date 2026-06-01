import React from 'react';
import { LuEye } from 'react-icons/lu';

import type { CaseInboxEntry } from '@/types/case-inbox';

import {
  districtChipClasses,
  formatAbsolute,
  formatRelative,
  normalizeCaseNumber,
} from './formatting';
import { SsnBadge } from './SsnBadge';

interface CaseInboxRowProps {
  entry: CaseInboxEntry;
  /** True while an accept/dismiss mutation is in flight for this row. */
  isMutating?: boolean;
  /** Called when the user clicks Accept (or Summon, if the row is archived). */
  onAccept: (entry: CaseInboxEntry) => void;
  /** Only invoked when status='ready'. The button is hidden on archived rows. */
  onDismiss: (entry: CaseInboxEntry) => void;
  /** Opens the in-page PDF drawer for this entry. */
  onViewPDF: (entry: CaseInboxEntry) => void;
}

/**
 * Single inbox row, used in both `/inbox` and `/inbox/archived`. Dense
 * table layout per the architect's UX call. Button label flips between
 * Accept and Summon based on `entry.status` — same /accept endpoint.
 */
export const CaseInboxRow: React.FC<CaseInboxRowProps> = ({
  entry,
  isMutating = false,
  onAccept,
  onDismiss,
  onViewPDF,
}) => {
  const isArchived = entry.status === 'archived';
  const actionLabel = isArchived ? 'Reinstate' : 'Accept';
  const annotation = isArchived ? archivedAnnotation(entry) : null;

  return (
    <tr className="border-b border-border last:border-b-0 text-sm">
      <td className="py-3 pl-4 pr-4 text-text-secondary tabular-nums whitespace-nowrap" title={formatAbsolute(entry.received_at ?? entry.created_at)}>
        {formatRelative(entry.received_at ?? entry.created_at)}
      </td>
      <td className="py-3 pr-4 font-mono text-text-secondary whitespace-nowrap">
        {normalizeCaseNumber(entry.case_number) ?? <span className="text-muted">—</span>}
      </td>
      <td className="py-3 pr-4 text-text-secondary truncate" title={entry.case_name ?? undefined}>
        {entry.case_name ?? <span className="text-muted">Unknown debtor</span>}
      </td>
      <td className="py-3 pr-4">
        {entry.court_district ? (
          <span className={districtChipClasses(entry.court_district)}>
            {entry.court_district}
          </span>
        ) : (
          <span className="text-xs text-muted">—</span>
        )}
      </td>
      <td className="py-3 pr-4">
        <SsnBadge entry={entry} />
      </td>
      <td className="py-3 pr-2">
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center justify-end gap-2">
            {entry.petition_pdf_url && (
              <button
                type="button"
                onClick={() => onViewPDF(entry)}
                aria-label="Open petition PDF in drawer"
                className="inline-flex items-center gap-1 rounded border border-border bg-surface px-3 py-1 text-xs font-semibold text-text-secondary transition hover:bg-surface-muted hover:text-app-accent-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent disabled:cursor-not-allowed disabled:opacity-50"
              >
                <LuEye className="h-3.5 w-3.5" aria-hidden="true" />
                View PDF
              </button>
            )}
            {!isArchived && (
              <button
                type="button"
                onClick={() => onDismiss(entry)}
                disabled={isMutating}
                className="rounded border border-app-danger-border bg-app-danger-soft px-3 py-1 text-xs font-semibold text-app-danger-text transition hover:bg-app-danger-soft/70 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-danger"
              >
                Reject
              </button>
            )}
            <button
              type="button"
              onClick={() => onAccept(entry)}
              disabled={isMutating}
              className="rounded bg-app-accent px-3 py-1 text-xs font-semibold text-white shadow-sm transition hover:bg-app-accent-strong disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
            >
              {actionLabel}
            </button>
          </div>
          {annotation && (
            <span className="text-[10px] text-muted">{annotation}</span>
          )}
        </div>
      </td>
    </tr>
  );
};

function archivedAnnotation(entry: CaseInboxEntry): string {
  const when = formatRelative(entry.archived_at);
  if (entry.dismissed_by_user_id) {
    return when ? `Rejected ${when} by another paralegal` : 'Rejected';
  }
  return when ? `Archived ${when}` : 'Archived';
}
