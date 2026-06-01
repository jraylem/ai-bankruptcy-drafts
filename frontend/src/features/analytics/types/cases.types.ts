import type {
  DashboardCaseSource,
  DashboardDateRange,
  DashboardPagination,
} from './common.types';

export type DashboardCasesAnalyticsSortBy =
  | 'created_at'
  | 'status'
  | 'district'
  | 'debtor_name'
  | 'bucket'
  | 'source'
  | 'last_activity_at'
  | 'motions_count';

export type DashboardCasesAnalyticsSortDir = 'asc' | 'desc';

export interface DashboardCasesAnalyticsActiveKpis {
  sum: number;
  manual: number;
  summoned: number;
  from_pending: number;
}

export interface DashboardCasesAnalyticsInactiveKpis {
  sum: number;
  denied: number;
  archived: number;
  deleted: number;
}

export interface DashboardCasesAnalyticsByDistrict {
  flnb: number;
  flmb: number;
  flsb: number;
  pawb: number;
  other: number;
}

export interface DashboardCasesAnalyticsKpis {
  total: number;
  active: DashboardCasesAnalyticsActiveKpis;
  pending: number;
  inactive: DashboardCasesAnalyticsInactiveKpis;
  by_district: DashboardCasesAnalyticsByDistrict;
}

export interface DashboardCaseAnalyticsItem {
  session_id: string;
  case_number: string | null;
  debtor_name: string | null;
  district: string | null;
  petition_status: string | null;
  bucket: string;
  source: DashboardCaseSource | null;
  created_at: string;
  last_activity_at: string | null;
  motions_count: number;
  thread_id: string | null;
}

export interface DashboardCasesAnalyticsResponse {
  kpis: DashboardCasesAnalyticsKpis;
  pagination: DashboardPagination;
  cases: DashboardCaseAnalyticsItem[];
  date_range: DashboardDateRange;
}

export interface DashboardCasesAnalyticsQuery {
  page?: number;
  page_size?: number;
  sort_by?: DashboardCasesAnalyticsSortBy;
  sort_dir?: DashboardCasesAnalyticsSortDir;
  search?: string;
  status?: string;
  district?: string;
  source?: DashboardCaseSource;
}

export interface DashboardCaseTimelineActor {
  user_id: string;
  name: string | null;
}

export interface DashboardCaseTimelineEvent {
  event: string;
  at: string;
  detail: string | null;
  actor: DashboardCaseTimelineActor | null;
}

export interface DashboardCaseDocument {
  filename: string;
  source: string | null;
  uploaded_at: string;
}

export interface DashboardCaseMotion {
  task_id: string;
  motion_type: string;
  status: string;
  case_name: string | null;
  case_number: string | null;
  created_at: string;
  completed_at: string | null;
  processing_seconds: number | null;
}

export interface DashboardCaseDetailResponse {
  session_id: string;
  case_number: string | null;
  debtor_name: string | null;
  district: string | null;
  petition_status: string | null;
  bucket: string;
  source: string | null;
  created_at: string;
  last_activity_at: string | null;
  thread_id: string | null;
  motions_count: number;
  timeline: DashboardCaseTimelineEvent[];
  timeline_pagination: DashboardPagination;
  documents: DashboardCaseDocument[];
  motions: DashboardCaseMotion[];
  motions_pagination: DashboardPagination;
}

export type DashboardCaseDetailSortDir = 'asc' | 'desc';

export type DashboardCaseDetailMotionsSortBy =
  | 'created_at'
  | 'motion_type'
  | 'status'
  | 'processing_seconds';

export interface DashboardCaseDetailQuery {
  motions_page?: number;
  motions_page_size?: number;
  motions_search?: string;
  motions_status?: string;
  motions_motion_type?: string;
  motions_sort_by?: DashboardCaseDetailMotionsSortBy;
  motions_sort_dir?: DashboardCaseDetailSortDir;
  timeline_page?: number;
  timeline_page_size?: number;
  timeline_event?: string;
  timeline_actor_id?: string;
  timeline_search?: string;
  timeline_sort_dir?: DashboardCaseDetailSortDir;
}
