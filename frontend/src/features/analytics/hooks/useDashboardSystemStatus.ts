import { useQuery } from '@tanstack/react-query';
import { fetchDashboardSystemStatus } from '../api/dashboard.api';

export const useDashboardSystemStatus = () =>
  useQuery({
    queryKey: ['dashboard-system-status'],
    queryFn: fetchDashboardSystemStatus,
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
