import type {
  DashboardCaseDetailResponse,
  DashboardCaseDocument,
  DashboardCaseMotion,
  DashboardCaseTimelineEvent,
} from '@/features/analytics/types/dashboard.types';
import type { CaseDetailDocumentActionMode } from '@/features/analytics/utils/caseDetail.helpers';

export interface CaseDetailHeaderCardProps {
  canOpenDashboard: boolean;
  detail: DashboardCaseDetailResponse;
  onOpenDashboard: () => void;
}

export interface CaseDetailTimelineViewModel {
  currentPage: number;
  currentPageSize: number;
  items: DashboardCaseTimelineEvent[];
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  showingFrom: number;
  showingTo: number;
  totalItems: number;
  totalPages: number;
}

export interface CaseDetailTimelineCardProps {
  timeline: CaseDetailTimelineViewModel;
}

export interface CaseDetailMotionsViewModel {
  clearFilters: () => void;
  clearSearch: () => void;
  currentPage: number;
  currentPageSize: number;
  hasFilters: boolean;
  rows: DashboardCaseMotion[];
  searchInput: string;
  setPage: (page: number) => void;
  setPageSize: (pageSize: number) => void;
  setSearchInput: (value: string) => void;
  setStatusFilter: (value: string) => void;
  showingFrom: number;
  showingTo: number;
  statusFilter: string;
  totalItems: number;
  totalPages: number;
}

export interface CaseDetailMotionsCardProps {
  motions: CaseDetailMotionsViewModel;
}

export interface CaseDetailDocumentsViewModel {
  actionError: string | null;
  canAccessDocument: (document: DashboardCaseDocument) => boolean;
  getDocumentDisplayName: (document: DashboardCaseDocument) => string;
  handleDocumentAction: (
    document: DashboardCaseDocument,
    mode: CaseDetailDocumentActionMode
  ) => Promise<void>;
  hasBusyAction: boolean;
  isDocumentBusy: (document: DashboardCaseDocument, mode: CaseDetailDocumentActionMode) => boolean;
  isPDFListLoading: boolean;
  pdfListErrorMessage: string | null;
}

export interface CaseDetailDocumentsCardProps {
  documents: CaseDetailDocumentsViewModel;
  rows: DashboardCaseDocument[];
}
