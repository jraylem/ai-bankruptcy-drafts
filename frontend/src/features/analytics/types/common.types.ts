export type AnalyticsRangePreset = 'today' | '7d' | '30d' | 'custom';

export interface DashboardDateRange {
  preset: string;
  start: string;
  end: string;
}

export interface DashboardAnalyticsFilters {
  range: AnalyticsRangePreset;
  start?: string;
  end?: string;
}

export interface DashboardPagination {
  page: number;
  page_size: number;
  total: number;
}

export type DashboardActivityMetadataValue = string | number | boolean | null;

export type DashboardCaseSource = 'manual' | 'ecf' | 'gdrive' | 'courtdrive';

export interface AnalyticsKpiCard {
  label: string;
  value: string;
  valueClass?: string;
  iconKey?:
    | 'totalCases'
    | 'activeCases'
    | 'pendingCases'
    | 'inactiveCases'
    | 'totalUsers'
    | 'newUsers'
    | 'motionsDrafted'
    | 'systemStatus';
}
