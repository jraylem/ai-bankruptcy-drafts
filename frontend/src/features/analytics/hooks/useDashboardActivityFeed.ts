import { useQuery } from '@tanstack/react-query';
import { fetchDashboardActivityFeed } from '../api/dashboard.api';
import type { DashboardActivityFeedQuery } from '../types/dashboard.types';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardActivityFeed = (query: DashboardActivityFeedQuery = {}) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-activity-feed', filters, query],
    queryFn: () => fetchDashboardActivityFeed(filters, query),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
