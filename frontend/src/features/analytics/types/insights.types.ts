import type { DashboardDateRange } from './common.types';

export type DashboardInsightType = 'trend' | 'chart' | 'pie' | 'users' | 'target' | string;

export interface DashboardInsightItem {
  type: DashboardInsightType;
  text: string;
}

export type DashboardInsightDirection = 'up' | 'down' | 'flat' | string;

export interface DashboardInsightPeriodMetric {
  pct: number | null;
  direction: DashboardInsightDirection;
}

export interface DashboardInsightPeriodOverPeriod {
  current_label: string;
  prior_label: string;
  total_cases: DashboardInsightPeriodMetric;
  motions_drafted: DashboardInsightPeriodMetric;
  orders_drafted?: DashboardInsightPeriodMetric;
  active_cases: DashboardInsightPeriodMetric;
  new_users: DashboardInsightPeriodMetric;
}

export interface DashboardInsightsResponse {
  summary_title: string;
  insights: DashboardInsightItem[];
  period_over_period: DashboardInsightPeriodOverPeriod;
  suggested_actions: string[];
  date_range: DashboardDateRange;
}

export interface DashboardInsightExplainResponse {
  explanation: string;
}

export interface DashboardInsightsChatResponse {
  reply: string;
}

export interface DashboardInsightsChatHistoryMessage {
  role: string;
  content: string;
}

export interface DashboardInsightsChatHistoryResponse {
  messages: DashboardInsightsChatHistoryMessage[];
}

export type DashboardInsightsChatStreamEvent =
  | { type: 'tool_status'; name: string; status: 'running' | 'done' }
  | { type: 'text_chunk'; chunk: string }
  | { type: 'done' }
  | { type: 'error'; message: string };
