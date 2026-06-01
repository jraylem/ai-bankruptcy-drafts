import { useQuery } from '@tanstack/react-query';
import { fetchDashboardMotionsDaily } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardMotionsDaily = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-motions-daily', filters],
    queryFn: () => fetchDashboardMotionsDaily(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
