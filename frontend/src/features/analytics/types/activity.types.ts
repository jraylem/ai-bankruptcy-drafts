import type { DashboardActivityMetadataValue, DashboardDateRange } from './common.types';

export interface DashboardActivityFeedItem {
  id: string;
  action: string;
  label: string;
  detail?: string | null;
  actor_name?: string | null;
  user_id: string | null;
  session_id: string | null;
  metadata: Record<string, DashboardActivityMetadataValue> | null;
  occurred_at: string;
}

export interface DashboardActivityFeedResponse {
  items: DashboardActivityFeedItem[];
  total: number;
  limit: number;
  offset: number;
  date_range: DashboardDateRange;
}

export interface DashboardActivityFeedQuery {
  action?: string;
  include_system?: boolean;
  limit?: number;
  offset?: number;
}

export type DashboardActivityLogEntityType = 'motion' | 'case' | 'pdf' | 'user' | 'system';

export interface DashboardActivityLogActor {
  user_id: string;
  name: string | null;
  email: string | null;
}

export interface DashboardActivityLogEntry {
  id: string;
  occurred_at: string;
  actor: DashboardActivityLogActor | null;
  action: string;
  label: string;
  detail: string | null;
  entity_type: DashboardActivityLogEntityType | null;
  entity_id: string | null;
  entity_label: string | null;
  status: string | null;
  metadata: Record<string, DashboardActivityMetadataValue> | null;
  session_id: string | null;
  duration_ms?: number | null;
  error_code?: number | null;
  error_message?: string | null;
}

export interface DashboardActivityLogFilters {
  date_range: DashboardDateRange;
  actor_id: string | null;
  actions: string[] | null;
  entity_type: DashboardActivityLogEntityType | null;
  entity_id: string | null;
  status: string | null;
  search?: string | null;
}

export interface DashboardActivityLogKpi {
  total_events: number;
  unique_actors: number;
  error_rate: number;
  avg_duration_ms: number | null;
}

export interface DashboardActivityLogResponse {
  items: DashboardActivityLogEntry[];
  total: number;
  limit: number;
  offset: number;
  filters: DashboardActivityLogFilters;
  kpi: DashboardActivityLogKpi;
}

export interface DashboardActivityLogActionOption {
  action: string;
  label: string;
  count: number;
}

export interface DashboardActivityLogActionsResponse {
  actions: DashboardActivityLogActionOption[];
  date_range: DashboardDateRange;
}

export interface DashboardActivityLogQuery {
  limit?: number;
  offset?: number;
  action?: string;
  actor_id?: string;
  entity_type?: DashboardActivityLogEntityType;
  entity_id?: string;
  status?: string;
  search?: string;
}
