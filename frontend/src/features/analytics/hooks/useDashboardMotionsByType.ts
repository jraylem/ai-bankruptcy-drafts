import { useQuery } from '@tanstack/react-query';
import { fetchDashboardMotionsByType } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardMotionsByType = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-motions-by-type', filters],
    queryFn: () => fetchDashboardMotionsByType(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
