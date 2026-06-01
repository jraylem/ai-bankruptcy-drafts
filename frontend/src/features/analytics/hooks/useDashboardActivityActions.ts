import { useQuery } from '@tanstack/react-query';
import { fetchDashboardActivityLogActions } from '../api/dashboard.api';
import { useAnalyticsQueryFilters } from './useAnalyticsQueryFilters';

type DashboardActivityActionOption = {
  label: string;
  value: string;
};

export const useDashboardActivityActions = (enabled = true) => {
  const filters = useAnalyticsQueryFilters();

  return useQuery({
    queryKey: ['dashboard-activity-actions', filters],
    enabled,
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<DashboardActivityActionOption[]> => {
      const response = await fetchDashboardActivityLogActions(filters);
      return response.actions
        .map((item) => ({ value: item.action, label: item.label }))
        .sort((a, b) => a.label.localeCompare(b.label));
    },
  });
};
