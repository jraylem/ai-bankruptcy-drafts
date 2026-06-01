import type { DashboardDateRange } from './common.types';

export interface DashboardCasesResponse {
  total: number;
  active_cases: {
    sum: number;
    manual: number;
    summoned: number;
    from_pending: number;
  };
  pending_cases: number;
  inactive_cases: {
    sum: number;
    denied: number;
    archived: number;
    deleted: number;
  };
  by_district_active: {
    sum: number;
    flnb: number;
    flmb: number;
    flsb: number;
    pawb: number;
    other: number;
  };
  date_range: DashboardDateRange;
}

export interface DashboardUsersResponse {
  total: number;
  new_in_range: number;
  active_in_range: number;
  date_range: DashboardDateRange;
}

export interface DashboardMotionsResponse {
  total: number;
  by_status: {
    pending: number;
    completed: number;
    failed: number;
    cancelled: number;
  };
  by_type: Array<{
    motion_type: string;
    display_name: string;
    count: number;
  }>;
  date_range: DashboardDateRange;
}

export interface DashboardMotionsDailyPoint {
  date: string;
  total: number;
  completed: number;
  pending: number;
  failed: number;
  cancelled: number;
}

export interface DashboardMotionsDailyResponse {
  data: DashboardMotionsDailyPoint[];
  date_range: DashboardDateRange;
}

export interface DashboardCasesDailyPoint {
  date: string;
  total: number;
  active: number;
  pending: number;
  inactive: number;
}

export interface DashboardCasesDailyResponse {
  data: DashboardCasesDailyPoint[];
  date_range: DashboardDateRange;
}

export interface DashboardUsersDailyPoint {
  date: string;
  active_users: number;
  motions_drafted: number;
  new_users: number;
}

export interface DashboardUsersDailyResponse {
  data: DashboardUsersDailyPoint[];
  date_range: DashboardDateRange;
}

export interface DashboardApiActionCount {
  action: string;
  count: number;
  error_count: number;
}

export interface DashboardApiUserCount {
  user_id: string;
  count: number;
}

export interface DashboardApiDailyPoint {
  date: string;
  count: number;
  error_count: number;
  by_action: Record<string, number>;
}

export interface DashboardApiCallsResponse {
  total: number;
  error_total: number;
  by_action: DashboardApiActionCount[];
  by_user: DashboardApiUserCount[];
  daily: DashboardApiDailyPoint[];
  filters: Record<string, string>;
  date_range: DashboardDateRange;
}

export interface DashboardMotionsByTypePoint {
  motion_type: string;
  display_name: string;
  total: number;
  completed: number;
  pending: number;
  failed: number;
  cancelled: number;
}

export interface DashboardMotionsByTypeResponse {
  data: DashboardMotionsByTypePoint[];
  date_range: DashboardDateRange;
}

export interface DashboardAnalyticsResponse {
  cases: DashboardCasesResponse;
  users: DashboardUsersResponse;
  motions: DashboardMotionsResponse;
}
