import type { DashboardAnalyticsFilters } from '../types';

interface ApiServiceResponse<T> {
  data?: T | null;
  error?: string | null;
}

export const buildQueryParams = (filters: DashboardAnalyticsFilters) =>
  filters.range === 'custom'
    ? { range: filters.range, start: filters.start, end: filters.end }
    : { range: filters.range };

export const getOrThrowData = <T>(response: ApiServiceResponse<T>, emptyMessage: string): T => {
  if (response.error) {
    throw new Error(response.error);
  }

  if (!response.data) {
    throw new Error(emptyMessage);
  }

  return response.data;
};
