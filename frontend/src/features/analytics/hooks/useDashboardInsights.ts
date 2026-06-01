import { useQuery } from '@tanstack/react-query';
import { fetchDashboardInsights } from '../api/insights.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardInsights = (enabled = true) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-insights', filters],
    queryFn: ({ signal }) => fetchDashboardInsights(filters, { signal }),
    enabled,
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
};
