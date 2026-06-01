import type {
  DashboardCaseSource,
  DashboardDateRange,
  DashboardPagination,
} from './common.types';

export type DashboardMotionsAnalyticsSortBy =
  | 'created_at'
  | 'status'
  | 'motion_type'
  | 'processing_seconds';

export type DashboardMotionsAnalyticsSortDir = 'asc' | 'desc';

export type DashboardMotionCategory = 'motion' | 'order';

export type DashboardMotionStatus = 'pending' | 'completed' | 'failed' | 'cancelled';

export type DashboardMotionCosType = 'WithNoticeOfHearing' | 'WithoutNoticeOfHearing' | 'No';

export interface DashboardMotionsAnalyticsByTypeItem {
  motion_type: string;
  display_name: string;
  completed: number;
  total_attempted: number;
}

export interface DashboardMotionsAnalyticsByDistrictItem {
  completed: number;
  total_attempted: number;
}

export interface DashboardMotionsAnalyticsTypeRankingItem {
  motion_type: string;
  display_name: string;
  category: string;
  completed: number;
  total_attempted: number;
}

export interface DashboardMotionsAnalyticsCosRankingItem {
  motion_type: string;
  display_name: string;
  count: number;
}

export interface DashboardMotionsAnalyticsAvgProcessingByTypeItem {
  motion_type: string;
  display_name: string;
  avg_seconds: number;
}

export interface DashboardMotionsAnalyticsKpis {
  total: number;
  by_status: {
    pending: number;
    completed: number;
    failed: number;
    cancelled: number;
  };
  success_rate_pct: number;
  avg_processing_seconds: number | null;
  by_type: {
    motions: DashboardMotionsAnalyticsByTypeItem[];
    orders: DashboardMotionsAnalyticsByTypeItem[];
  };
  by_district: {
    flnb: DashboardMotionsAnalyticsByDistrictItem;
    flmb: DashboardMotionsAnalyticsByDistrictItem;
    flsb: DashboardMotionsAnalyticsByDistrictItem;
    pawb: DashboardMotionsAnalyticsByDistrictItem;
    other: DashboardMotionsAnalyticsByDistrictItem;
  };
  by_cos_type: {
    with_notice_of_hearing: number;
    without_notice_of_hearing: number;
    no: number;
  };
  cos_type_ranking: {
    with_notice_of_hearing: DashboardMotionsAnalyticsCosRankingItem[];
    without_notice_of_hearing: DashboardMotionsAnalyticsCosRankingItem[];
  };
  motion_type_ranking: DashboardMotionsAnalyticsTypeRankingItem[];
  avg_processing_by_type: DashboardMotionsAnalyticsAvgProcessingByTypeItem[];
}

export interface DashboardMotionAnalyticsItem {
  task_id: string;
  session_id: string | null;
  case_number: string | null;
  case_name: string | null;
  debtor_name: string | null;
  district: string | null;
  motion_type: string;
  display_name: string;
  category: string;
  status: string;
  cos_type: string | null;
  source: DashboardCaseSource | null;
  created_at: string;
  completed_at: string | null;
  processing_seconds: number | null;
  actor_user_id: string | null;
  actor_name: string | null;
}

export interface DashboardMotionsAnalyticsResponse {
  kpis: DashboardMotionsAnalyticsKpis;
  pagination: DashboardPagination;
  motions: DashboardMotionAnalyticsItem[];
  date_range: DashboardDateRange;
}

export interface DashboardMotionsAnalyticsQuery {
  page?: number;
  page_size?: number;
  sort_by?: DashboardMotionsAnalyticsSortBy;
  sort_dir?: DashboardMotionsAnalyticsSortDir;
  search?: string;
  motion_type?: string;
  category?: DashboardMotionCategory;
  status?: DashboardMotionStatus;
  district?: string;
  source?: DashboardCaseSource;
  cos_type?: DashboardMotionCosType;
}

export interface DashboardMotionSessionSummaryKpis {
  total_motions_and_orders: number;
  total_motions: number;
  total_orders: number;
  completed: number;
  pending: number;
  failed: number;
  cancelled: number;
  avg_processing_seconds: number | null;
  total_cos_generated: number;
  cos_with_notice_of_hearing: number;
  cos_without_notice_of_hearing: number;
}

export interface DashboardMotionSessionByTypeItem {
  motion_type: string;
  display_name: string;
  category: string;
  completed: number;
  total_attempted: number;
}

export interface DashboardMotionSessionByType {
  motions: DashboardMotionSessionByTypeItem[];
  orders: DashboardMotionSessionByTypeItem[];
}

export interface DashboardMotionSessionItem {
  task_id: string;
  motion_type: string;
  display_name: string;
  category: string;
  status: string;
  cos_type: string | null;
  created_at: string;
  completed_at: string | null;
  processing_seconds: number | null;
  actor_user_id: string | null;
  actor_name: string | null;
}

export interface DashboardMotionSessionDetailResponse {
  session_id: string;
  case_number: string | null;
  debtor_name: string | null;
  district: string | null;
  kpis: DashboardMotionSessionSummaryKpis;
  by_type: DashboardMotionSessionByType;
  pagination: DashboardPagination;
  motions: DashboardMotionSessionItem[];
}

export interface DashboardMotionSessionDetailQuery {
  page?: number;
  page_size?: number;
  sort_by?: DashboardMotionsAnalyticsSortBy;
  sort_dir?: DashboardMotionsAnalyticsSortDir;
  status?: DashboardMotionStatus;
  category?: DashboardMotionCategory;
  motion_type?: string;
  search?: string;
}
