import React from 'react';
import { FiDownload, FiEye, FiFolder } from 'react-icons/fi';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import {
  formatCaseDetailDateTime,
  formatCaseDetailLabel,
} from '@/features/analytics/utils/caseDetail.helpers';
import type { CaseDetailDocumentsCardProps } from './types';

export const CaseDetailDocumentsCard: React.FC<CaseDetailDocumentsCardProps> = ({
  documents,
  rows,
}) => {
  return (
    <SectionCard
      className="self-start"
      title={
        <div className="flex items-center gap-2">
          <FiFolder className="h-4 w-4 text-app-accent" />
          <span>Documents</span>
        </div>
      }
    >
      {documents.actionError ? (
        <div className="mb-3 rounded-xl border border-app-danger-text/25 bg-app-danger-soft px-3 py-2 text-xs text-app-danger-text">
          {documents.actionError}
        </div>
      ) : null}

      {documents.pdfListErrorMessage ? (
        <div className="mb-3 rounded-xl border border-app-warning-text/25 bg-app-warning-soft px-3 py-2 text-xs text-app-warning-text">
          File list issue: {documents.pdfListErrorMessage}
        </div>
      ) : null}

      {documents.isPDFListLoading ? (
        <AnalyticsBodySkeleton className="h-[220px]" />
      ) : rows.length ? (
        <div className="space-y-2">
          {rows.map((document, index) => {
            const canAccess = documents.canAccessDocument(document);
            const isViewing = documents.isDocumentBusy(document, 'view');
            const isDownloading = documents.isDocumentBusy(document, 'download');
            const displayName = documents.getDocumentDisplayName(document);

            return (
              <div
                key={`${document.filename}-${document.uploaded_at}-${index}`}
                className="rounded-xl border border-border/70 bg-surface-muted/50 px-3 py-2.5"
              >
                <p className="truncate text-xs font-medium text-text-secondary">{displayName}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-subtle">
                  <span>{document.source ? formatCaseDetailLabel(document.source) : 'Unknown source'}</span>
                  <span aria-hidden="true">•</span>
                  <span>{formatCaseDetailDateTime(document.uploaded_at)}</span>
                </div>

                <div className="mt-2 flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => void documents.handleDocumentAction(document, 'view')}
                    disabled={!canAccess || documents.hasBusyAction}
                    aria-label={`View ${displayName}`}
                    title={isViewing ? 'Opening...' : 'View'}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-app-accent-soft text-app-accent-text transition hover:bg-option-icon-hover disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <FiEye className={`h-3.5 w-3.5 ${isViewing ? 'animate-pulse' : ''}`} />
                  </button>
                  <button
                    type="button"
                    onClick={() => void documents.handleDocumentAction(document, 'download')}
                    disabled={!canAccess || documents.hasBusyAction}
                    aria-label={`Download ${displayName}`}
                    title={isDownloading ? 'Downloading...' : 'Download'}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-app-success-soft text-app-success-text transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <FiDownload className={`h-3.5 w-3.5 ${isDownloading ? 'animate-pulse' : ''}`} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-subtle">No documents found.</p>
      )}
    </SectionCard>
  );
};
