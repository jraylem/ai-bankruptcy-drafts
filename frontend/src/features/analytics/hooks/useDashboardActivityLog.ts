import { useQuery } from '@tanstack/react-query';
import { fetchDashboardActivityLog } from '../api/dashboard.api';
import type { DashboardActivityLogQuery } from '../types/dashboard.types';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardActivityLog = (query: DashboardActivityLogQuery = {}) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-activity-log', filters, query],
    queryFn: () => fetchDashboardActivityLog(filters, query),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
