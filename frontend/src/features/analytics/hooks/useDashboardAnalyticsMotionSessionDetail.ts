import { useQuery } from '@tanstack/react-query';
import { fetchDashboardAnalyticsMotionSessionDetail } from '../api/dashboard.api';
import type { DashboardMotionSessionDetailQuery } from '../types/dashboard.types';

export const useDashboardAnalyticsMotionSessionDetail = (
  sessionId: string | null,
  query: DashboardMotionSessionDetailQuery = {},
  enabled = true
) =>
  useQuery({
    queryKey: ['dashboard-analytics-motions-session-detail', sessionId, query],
    queryFn: () => fetchDashboardAnalyticsMotionSessionDetail(sessionId as string, query),
    enabled: Boolean(sessionId) && enabled,
    placeholderData: (previousData) => previousData,
    staleTime: 30_000,
  });
