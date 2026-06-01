import { useQuery } from '@tanstack/react-query';
import { fetchDashboardAnalyticsCases } from '../api/dashboard.api';
import type { DashboardCasesAnalyticsQuery } from '../types/dashboard.types';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardAnalyticsCases = (query: DashboardCasesAnalyticsQuery = {}) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-analytics-cases', filters, query],
    queryFn: () => fetchDashboardAnalyticsCases(filters, query),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
