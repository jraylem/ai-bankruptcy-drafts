import { useQuery } from '@tanstack/react-query';
import { fetchDashboardCases } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardCases = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-cases', filters],
    queryFn: () => fetchDashboardCases(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
