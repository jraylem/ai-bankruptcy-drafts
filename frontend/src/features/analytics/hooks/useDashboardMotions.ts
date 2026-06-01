import { useQuery } from '@tanstack/react-query';
import { fetchDashboardMotions } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardMotions = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-motions', filters],
    queryFn: () => fetchDashboardMotions(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
