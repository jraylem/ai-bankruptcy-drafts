import type { DashboardUsersAnalyticsUser } from './users.types';

export type UsersTableSortKey = 'joined' | 'last_active' | 'cases' | 'motions';

export type SortDirection = 'asc' | 'desc';

export interface UsersSummaryMetrics {
  totalUsers: number;
  newInRange: number;
  activeInRange: number;
  avgMotionsPerUser: number;
}

export interface UsersTrendPoint {
  day: string;
  motions: number;
  activeUsers: number;
  newUsers: number;
}

export interface UsersPageSizeOption {
  label: string;
  value: string;
}

export type UsersRow = DashboardUsersAnalyticsUser;
