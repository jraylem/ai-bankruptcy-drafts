/** Wire types for /api/v2/core/costs/summary — keep in sync with
 *  bkdrafts-be/src/core/components/costs/schemas.py. */

export type CostRange = 'week' | 'month';

export interface CostsByKindEntry {
  kind: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface DailyCostEntry {
  day: string; // ISO timestamp
  cost_usd: number;
}

export interface CostsProjection {
  this_month_cost_usd: number;
  this_year_cost_usd: number;
  method: string;
}

export type WorkflowCountUnit = 'session' | 'message' | 'run' | 'case';

export interface WorkflowMetricEntry {
  unit: WorkflowCountUnit;
  count: number;
  avg_cost_usd: number;
}

export interface WorkflowMetric {
  total_cost_usd: number;
  metrics: WorkflowMetricEntry[];
}

export interface WorkflowMetrics {
  chat: WorkflowMetric;
  pleadings: WorkflowMetric;
  case_ingest: WorkflowMetric;
}

export interface CostsSummaryResponse {
  range: CostRange;
  since: string; // ISO
  until: string; // ISO
  total_cost_usd: number;
  by_kind: CostsByKindEntry[];
  daily_series: DailyCostEntry[];
  workflow_metrics: WorkflowMetrics;
  /** null on `range='week'` (weekly extrapolation is meaningless). */
  projection: CostsProjection | null;
}
