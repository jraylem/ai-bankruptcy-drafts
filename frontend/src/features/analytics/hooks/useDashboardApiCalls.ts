import { useQuery } from '@tanstack/react-query';
import { fetchDashboardApiCalls } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardApiCalls = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-api-calls', filters],
    queryFn: () => fetchDashboardApiCalls(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
