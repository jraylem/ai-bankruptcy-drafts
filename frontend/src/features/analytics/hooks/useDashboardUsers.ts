import { useQuery } from '@tanstack/react-query';
import { fetchDashboardUsers } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

export const useDashboardUsers = () => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-users', filters],
    queryFn: () => fetchDashboardUsers(filters),
    placeholderData: (previousData) => previousData,
    staleTime: 60_000,
  });
};
