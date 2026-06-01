import { useQuery } from '@tanstack/react-query';
import { fetchDashboardAnalyticsUsers } from '../api/dashboard.api';
import type { DashboardUsersAnalyticsQuery } from '../types/dashboard.types';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardAnalyticsUsers = (query: DashboardUsersAnalyticsQuery = {}) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-analytics-users', filters, query],
    queryFn: () => fetchDashboardAnalyticsUsers(filters, query),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
