import { useQuery } from '@tanstack/react-query';
import { fetchDashboardAnalyticsCaseDetail } from '../api/dashboard.api';
import type { DashboardCaseDetailQuery } from '../types/dashboard.types';

export const useDashboardAnalyticsCaseDetail = (
  sessionId: string | null,
  query: DashboardCaseDetailQuery = {},
  enabled = true
) =>
  useQuery({
    queryKey: ['dashboard-analytics-cases-detail', sessionId, query],
    queryFn: () => fetchDashboardAnalyticsCaseDetail(sessionId as string, query),
    enabled: Boolean(sessionId) && enabled,
    placeholderData: (previousData) => previousData,
    staleTime: 30_000,
  });
