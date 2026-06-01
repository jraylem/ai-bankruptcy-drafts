import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { FiArrowLeft } from 'react-icons/fi';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { API_ENDPOINTS } from '@/constants';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import {
  CaseDetailDocumentsCard,
  CaseDetailHeaderCard,
  CaseDetailMotionsCard,
  CaseDetailTimelineCard,
} from '@/features/analytics/components/cases/detail';
import { useDashboardAnalyticsCaseDetail } from '@/features/analytics/hooks/useDashboardAnalyticsCaseDetail';
import type { DashboardCaseDocument } from '@/features/analytics/types/dashboard.types';
import {
  type CaseDetailDocumentActionMode,
  buildCaseDetailDocumentKey,
} from '@/features/analytics/utils/caseDetail.helpers';
import { apiService } from '@/services/api';
import { pdfService } from '@/services/pdf.service';

interface SessionPDFMetadata {
  id: string;
  filename: string;
  original_filename: string;
  uploaded_at: string;
}

interface SessionPDFListResponse {
  session_id: string;
  pdfs: SessionPDFMetadata[];
}

export const AnalyticsCaseDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();
  const [documentActionError, setDocumentActionError] = useState<string | null>(null);
  const [busyDocumentAction, setBusyDocumentAction] = useState<string | null>(null);
  const [timelinePage, setTimelinePage] = useState<number>(1);
  const [timelinePageSize, setTimelinePageSize] = useState<number>(10);
  const [motionsPage, setMotionsPage] = useState<number>(1);
  const [motionsPageSize, setMotionsPageSize] = useState<number>(10);
  const [motionStatusFilter, setMotionStatusFilter] = useState('');
  const [motionSearchInput, setMotionSearchInput] = useState('');
  const [motionSearchQuery, setMotionSearchQuery] = useState('');

  const detailQuery = useMemo(
    () => ({
      timeline_page: timelinePage,
      timeline_page_size: timelinePageSize,
      motions_page: motionsPage,
      motions_page_size: motionsPageSize,
      ...(motionSearchQuery ? { motions_search: motionSearchQuery } : {}),
      ...(motionStatusFilter ? { motions_status: motionStatusFilter } : {}),
    }),
    [
      motionSearchQuery,
      motionStatusFilter,
      motionsPage,
      motionsPageSize,
      timelinePage,
      timelinePageSize,
    ]
  );

  const {
    data: detail,
    isLoading,
    error,
  } = useDashboardAnalyticsCaseDetail(sessionId ?? null, detailQuery, Boolean(sessionId));

  const {
    data: pdfList,
    isLoading: isPDFListLoading,
    error: pdfListError,
  } = useQuery({
    queryKey: ['session-pdfs', sessionId],
    enabled: Boolean(sessionId),
    queryFn: async () => {
      const response = await apiService.get<SessionPDFListResponse>(
        API_ENDPOINTS.PDF.LIST_BY_SESSION(sessionId as string)
      );

      if (response.error) {
        throw new Error(response.error);
      }

      if (!response.data) {
        throw new Error('Failed to load files for this case');
      }

      return response.data.pdfs;
    },
    staleTime: 30_000,
  });

  const pdfByFilename = useMemo(() => {
    const map = new Map<string, SessionPDFMetadata[]>();

    (pdfList ?? []).forEach((pdf) => {
      const current = map.get(pdf.filename) ?? [];
      current.push(pdf);
      map.set(pdf.filename, current);
    });

    return map;
  }, [pdfList]);

  const resolvePDF = (document: DashboardCaseDocument) => {
    const candidates = pdfByFilename.get(document.filename) ?? [];
    return candidates[0] ?? null;
  };

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setMotionSearchQuery((current) =>
        current === motionSearchInput.trim() ? current : motionSearchInput.trim()
      );
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [motionSearchInput]);

  useEffect(() => {
    setTimelinePage(1);
    setTimelinePageSize(10);
    setMotionsPage(1);
    setMotionsPageSize(10);
    setMotionStatusFilter('');
    setMotionSearchInput('');
    setMotionSearchQuery('');
  }, [sessionId]);

  useEffect(() => {
    setMotionsPage(1);
  }, [motionStatusFilter, motionSearchQuery, motionsPageSize]);

  useEffect(() => {
    setTimelinePage(1);
  }, [timelinePageSize]);

  const timelineItems = detail?.timeline ?? [];
  const timelinePagination = detail?.timeline_pagination;
  const timelineTotalItems = timelinePagination?.total ?? 0;
  const timelineCurrentPage = timelinePagination?.page ?? timelinePage;
  const timelineCurrentPageSize = timelinePagination?.page_size ?? timelinePageSize;
  const timelineTotalPages = Math.max(1, Math.ceil(timelineTotalItems / timelineCurrentPageSize));
  const timelineShowingFrom =
    timelineTotalItems === 0 ? 0 : (timelineCurrentPage - 1) * timelineCurrentPageSize + 1;
  const timelineShowingTo = Math.min(
    (timelineCurrentPage - 1) * timelineCurrentPageSize + timelineItems.length,
    timelineTotalItems
  );

  const motionRows = detail?.motions ?? [];
  const motionsPagination = detail?.motions_pagination;
  const motionsTotalItems = motionsPagination?.total ?? 0;
  const motionsCurrentPage = motionsPagination?.page ?? motionsPage;
  const motionsCurrentPageSize = motionsPagination?.page_size ?? motionsPageSize;
  const motionsTotalPages = Math.max(1, Math.ceil(motionsTotalItems / motionsCurrentPageSize));
  const motionsShowingFrom =
    motionsTotalItems === 0 ? 0 : (motionsCurrentPage - 1) * motionsCurrentPageSize + 1;
  const motionsShowingTo = Math.min(
    (motionsCurrentPage - 1) * motionsCurrentPageSize + motionRows.length,
    motionsTotalItems
  );
  const hasMotionFilters = Boolean(motionSearchInput.trim() || motionStatusFilter);

  useEffect(() => {
    if (timelinePage > timelineTotalPages) {
      setTimelinePage(timelineTotalPages);
    }
  }, [timelinePage, timelineTotalPages]);

  useEffect(() => {
    if (motionsPage > motionsTotalPages) {
      setMotionsPage(motionsTotalPages);
    }
  }, [motionsPage, motionsTotalPages]);

  const handleDocumentAction = async (
    document: DashboardCaseDocument,
    mode: CaseDetailDocumentActionMode
  ) => {
    setDocumentActionError(null);

    const pdf = resolvePDF(document);

    if (!pdf?.id) {
      setDocumentActionError('This file is not available for direct preview/download yet.');
      return;
    }

    const actionKey = buildCaseDetailDocumentKey(document, mode);
    setBusyDocumentAction(actionKey);

    try {
      const blob = await pdfService.downloadPDF(pdf.id);
      const blobUrl = window.URL.createObjectURL(blob);

      if (mode === 'view') {
        window.open(blobUrl, '_blank', 'noopener,noreferrer');
      } else {
        const anchor = window.document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = pdf.original_filename || document.filename;
        window.document.body.appendChild(anchor);
        anchor.click();
        window.document.body.removeChild(anchor);
      }

      window.setTimeout(() => window.URL.revokeObjectURL(blobUrl), 60_000);
    } catch (downloadError) {
      setDocumentActionError(
        downloadError instanceof Error ? downloadError.message : 'Failed to access file'
      );
    } finally {
      setBusyDocumentAction(null);
    }
  };

  const clearMotionSearch = () => {
    setMotionSearchInput('');
    setMotionSearchQuery('');
    setMotionsPage(1);
  };

  const clearMotionFilters = () => {
    setMotionStatusFilter('');
    setMotionSearchInput('');
    setMotionSearchQuery('');
    setMotionsPage(1);
  };

  if (!sessionId) {
    return (
      <SidebarLayout sidebarVariant="analytics" className="bg-page" contentClassName="overflow-y-auto">
        <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Missing case session id.
          </div>
        </div>
      </SidebarLayout>
    );
  }

  return (
    <SidebarLayout sidebarVariant="analytics" className="bg-page" contentClassName="overflow-y-auto">
      <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
        <div className="mb-5 flex items-center gap-2 text-xs text-muted">
          <button
            type="button"
            onClick={() => navigate('/analytics/cases')}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-medium text-text-secondary transition hover:bg-surface-muted"
          >
            <FiArrowLeft className="h-3.5 w-3.5" />
            Back to Cases
          </button>
        </div>

        {error ? (
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Failed to load case detail: {error.message}
          </div>
        ) : isLoading || !detail ? (
          <AnalyticsBodySkeleton className="h-[420px]" />
        ) : (
          <>
            <CaseDetailHeaderCard
              canOpenDashboard={Boolean(detail.thread_id)}
              detail={detail}
              onOpenDashboard={() => {
                if (!detail.thread_id) return;
                window.open(`/dashboard/${detail.session_id}`, '_blank', 'noopener,noreferrer');
              }}
            />
            <div className="grid items-start gap-6 xl:grid-cols-[1.35fr_0.65fr]">
              <div className="space-y-6">
                <CaseDetailTimelineCard
                  timeline={{
                    currentPage: timelineCurrentPage,
                    currentPageSize: timelineCurrentPageSize,
                    items: timelineItems,
                    setPage: setTimelinePage,
                    setPageSize: setTimelinePageSize,
                    showingFrom: timelineShowingFrom,
                    showingTo: timelineShowingTo,
                    totalItems: timelineTotalItems,
                    totalPages: timelineTotalPages,
                  }}
                />
                <CaseDetailMotionsCard
                  motions={{
                    clearFilters: clearMotionFilters,
                    clearSearch: clearMotionSearch,
                    currentPage: motionsCurrentPage,
                    currentPageSize: motionsCurrentPageSize,
                    hasFilters: hasMotionFilters,
                    rows: motionRows,
                    searchInput: motionSearchInput,
                    setPage: setMotionsPage,
                    setPageSize: setMotionsPageSize,
                    setSearchInput: setMotionSearchInput,
                    setStatusFilter: setMotionStatusFilter,
                    showingFrom: motionsShowingFrom,
                    showingTo: motionsShowingTo,
                    statusFilter: motionStatusFilter,
                    totalItems: motionsTotalItems,
                    totalPages: motionsTotalPages,
                  }}
                />
              </div>
              <CaseDetailDocumentsCard
                documents={{
                  actionError: documentActionError,
                  canAccessDocument: (document) => Boolean(resolvePDF(document)),
                  getDocumentDisplayName: (document) => {
                    const matchedPDF = resolvePDF(document);
                    return matchedPDF?.original_filename || document.filename;
                  },
                  handleDocumentAction,
                  hasBusyAction: Boolean(busyDocumentAction),
                  isDocumentBusy: (document, mode) =>
                    busyDocumentAction === buildCaseDetailDocumentKey(document, mode),
                  isPDFListLoading: isPDFListLoading && !pdfList,
                  pdfListErrorMessage: pdfListError instanceof Error ? pdfListError.message : null,
                }}
                rows={detail.documents}
              />
            </div>
          </>
        )}
      </div>
    </SidebarLayout>
  );
};
