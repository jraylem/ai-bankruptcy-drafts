import { useQuery } from '@tanstack/react-query';
import { fetchDashboardAnalyticsMotions } from '../api/dashboard.api';
import type { DashboardMotionsAnalyticsQuery } from '../types/dashboard.types';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardAnalyticsMotions = (query: DashboardMotionsAnalyticsQuery = {}) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-analytics-motions', filters, query],
    queryFn: () => fetchDashboardAnalyticsMotions(filters, query),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
