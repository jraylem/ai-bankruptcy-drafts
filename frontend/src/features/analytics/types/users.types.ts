import type { DashboardActivityMetadataValue, DashboardDateRange, DashboardPagination } from './common.types';

export type DashboardUsersAnalyticsSortBy =
  | 'last_active'
  | 'cases_count'
  | 'motions_drafted'
  | 'created_at';

export type DashboardUsersAnalyticsSortDir = 'asc' | 'desc';

export interface DashboardUsersAnalyticsKpis {
  total_users: number;
  new_in_range: number;
  active_in_range: number;
  avg_motions_per_user: number;
}

export interface DashboardUsersAnalyticsAction {
  action: string;
  label: string;
  detail: string | null;
  entity_id: string | null;
  timestamp: string;
  metadata: Record<string, DashboardActivityMetadataValue> | null;
}

export interface DashboardUsersAnalyticsUser {
  user_id: string;
  name: string;
  email: string;
  created_at: string;
  last_active_at: string | null;
  cases_count: number;
  motions_drafted: number;
  avg_draft_time_seconds: number | null;
  top_motion_types: string[];
  recent_actions: DashboardUsersAnalyticsAction[];
}

export interface DashboardUsersAnalyticsResponse {
  kpis: DashboardUsersAnalyticsKpis;
  pagination: DashboardPagination;
  users: DashboardUsersAnalyticsUser[];
  date_range: DashboardDateRange;
}

export interface DashboardUsersAnalyticsQuery {
  page?: number;
  page_size?: number;
  sort_by?: DashboardUsersAnalyticsSortBy;
  sort_dir?: DashboardUsersAnalyticsSortDir;
  search?: string;
}

export type DashboardUsersDetailSessionsSortBy =
  | 'case'
  | 'source'
  | 'status'
  | 'motions'
  | 'last_activity';

export type DashboardUsersDetailActivitySortBy = 'action' | 'duration' | 'occurred';

export interface DashboardUsersDetailExportQuery {
  sessions_page?: number;
  sessions_page_size?: number;
  sessions_search?: string;
  sessions_source?: 'manual' | 'ecf' | 'gdrive' | 'courtdrive';
  sessions_status?: 'working' | 'accepted' | 'pending_acceptance' | 'archived';
  sessions_sort_by?: DashboardUsersDetailSessionsSortBy;
  sessions_sort_dir?: DashboardUsersAnalyticsSortDir;
  activity_page?: number;
  activity_page_size?: number;
  activity_search?: string;
  activity_action?: string;
  activity_sort_by?: DashboardUsersDetailActivitySortBy;
  activity_sort_dir?: DashboardUsersAnalyticsSortDir;
}
