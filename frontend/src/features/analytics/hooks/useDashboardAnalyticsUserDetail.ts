import { useQuery } from '@tanstack/react-query';
import { fetchDashboardAnalyticsUserDetail } from '../api/users.api';
import type { DashboardUserDetailQuery } from '../types';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardAnalyticsUserDetail = (
  userId: string | null,
  query: DashboardUserDetailQuery = {},
  enabled = true
) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-analytics-user-detail', userId, filters, query],
    queryFn: () => fetchDashboardAnalyticsUserDetail(userId as string, filters, query),
    enabled: Boolean(userId) && enabled,
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
