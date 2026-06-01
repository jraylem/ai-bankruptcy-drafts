import { useQuery } from '@tanstack/react-query';
import { fetchDashboardUsersDaily } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardUsersDaily = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-users-daily', filters],
    queryFn: () => fetchDashboardUsersDaily(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
