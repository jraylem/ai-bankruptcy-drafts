import { useQuery } from '@tanstack/react-query';
import { fetchDashboardCasesDaily } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardCasesDaily = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-cases-daily', filters],
    queryFn: () => fetchDashboardCasesDaily(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
