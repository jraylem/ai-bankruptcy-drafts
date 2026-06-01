export type UserDetailSessionSource = 'manual' | 'ecf' | 'gdrive' | 'courtdrive';

export type UserDetailSessionStatus = 'working' | 'accepted' | 'pending_acceptance' | 'archived';

export type UserDetailActivityStatusFilter = 'completed' | 'pending' | 'failed';

export type UserDetailActivityStatus =
  | UserDetailActivityStatusFilter
  | 'accepted'
  | 'denied'
  | 'archived'
  | 'success';

export type UserDetailSortDirection = 'asc' | 'desc';

export type UserDetailSessionsSortKey =
  | 'case'
  | 'district'
  | 'source'
  | 'status'
  | 'motions'
  | 'last_activity';

export type UserDetailActivitySortKey = 'action' | 'status' | 'duration' | 'occurred' | 'entity';

export type UserDetailActivityAction =
  | 'draft_motion'
  | 'generate_document'
  | 'download_motion'
  | 'upload_pdf'
  | 'accept_case';

export interface UserDetailPagination {
  page: number;
  page_size: number;
  total: number;
}

export interface UserDetailDateRangeInfo {
  preset: string;
  start: string;
  end: string;
}

export interface UserDetailTrendPoint {
  day: string;
  motions: number;
  activeMinutes: number;
}

export interface UserDetailMotionTypeRow {
  motion_type: string;
  drafted: number;
  completed: number;
}

export interface UserDetailSessionRow {
  session_id: string;
  case_number: string | null;
  debtor_name: string | null;
  district: string | null;
  source: UserDetailSessionSource | null;
  petition_status: UserDetailSessionStatus | null;
  motions_count: number;
  last_activity_at: string | null;
}

export interface UserDetailActivityRow {
  id: string;
  occurred_at: string;
  action: string;
  detail: string | null;
  entity_id: string | null;
  status: UserDetailActivityStatus | null;
  duration_ms: number | null;
}

export interface UserDetailViewModel {
  user_id: string;
  name: string;
  email: string;
  joined_at: string | null;
  last_active_at: string | null;
  login_count_30d: number;
  active_days_30d: number;
  sessions_created_30d: number;
  motions_started_30d: number;
  motions_completed_30d: number;
  draft_success_rate: number;
  avg_draft_time_seconds: number | null;
  documents_exported_30d: number;
  trend_30d: UserDetailTrendPoint[];
  top_motion_types: UserDetailMotionTypeRow[];
  recent_sessions: UserDetailSessionRow[];
  recent_sessions_pagination: UserDetailPagination;
  recent_activity: UserDetailActivityRow[];
  recent_activity_pagination: UserDetailPagination;
  date_range: UserDetailDateRangeInfo;
}

export interface DashboardUserDetailQuery {
  sessions_page?: number;
  sessions_page_size?: number;
  sessions_search?: string;
  sessions_source?: UserDetailSessionSource;
  sessions_status?: UserDetailSessionStatus;
  sessions_sort_by?: UserDetailSessionsSortKey;
  sessions_sort_dir?: UserDetailSortDirection;
  activity_page?: number;
  activity_page_size?: number;
  activity_search?: string;
  activity_action?: UserDetailActivityAction;
  activity_status?: UserDetailActivityStatusFilter;
  activity_sort_by?: UserDetailActivitySortKey;
  activity_sort_dir?: UserDetailSortDirection;
}

export interface UserDetailSessionsQueryState {
  page: number;
  pageSize: number;
  search: string;
  source: UserDetailSessionSource | '';
  status: UserDetailSessionStatus | '';
  sortBy: UserDetailSessionsSortKey;
  sortDir: UserDetailSortDirection;
}

export interface UserDetailActivityQueryState {
  page: number;
  pageSize: number;
  search: string;
  action: UserDetailActivityAction | '';
  status: UserDetailActivityStatusFilter | '';
  sortBy: UserDetailActivitySortKey;
  sortDir: UserDetailSortDirection;
}
