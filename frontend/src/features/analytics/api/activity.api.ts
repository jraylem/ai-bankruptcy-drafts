import { apiService } from '@/services/api';
import { API_ENDPOINTS } from '@/constants';
import type {
  DashboardActivityFeedQuery,
  DashboardActivityFeedResponse,
  DashboardActivityLogActionsResponse,
  DashboardActivityLogQuery,
  DashboardActivityLogResponse,
  DashboardAnalyticsFilters,
} from '../types';
import { buildQueryParams, getOrThrowData } from './shared.api';

export const fetchDashboardActivityFeed = async (
  filters: DashboardAnalyticsFilters,
  query: DashboardActivityFeedQuery = {}
): Promise<DashboardActivityFeedResponse> => {
  const response = await apiService.get<DashboardActivityFeedResponse>(
    API_ENDPOINTS.DASHBOARD.ACTIVITY.FEED,
    {
      params: {
        ...buildQueryParams(filters),
        limit: query.limit ?? 5,
        offset: query.offset ?? 0,
        ...(query.action ? { action: query.action } : {}),
        ...(typeof query.include_system === 'boolean'
          ? { include_system: query.include_system }
          : {}),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard activity feed response was empty');
};

export const fetchDashboardActivityLog = async (
  filters: DashboardAnalyticsFilters,
  query: DashboardActivityLogQuery = {}
): Promise<DashboardActivityLogResponse> => {
  const response = await apiService.get<DashboardActivityLogResponse>(
    API_ENDPOINTS.DASHBOARD.ACTIVITY.LOG,
    {
      params: {
        ...buildQueryParams(filters),
        limit: query.limit ?? 20,
        offset: query.offset ?? 0,
        ...(query.action ? { action: query.action } : {}),
        ...(query.actor_id ? { actor_id: query.actor_id } : {}),
        ...(query.entity_type ? { entity_type: query.entity_type } : {}),
        ...(query.entity_id ? { entity_id: query.entity_id } : {}),
        ...(query.status ? { status: query.status } : {}),
        ...(query.search ? { search: query.search } : {}),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard activity log response was empty');
};

export const fetchDashboardActivityLogActions = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardActivityLogActionsResponse> => {
  const response = await apiService.get<DashboardActivityLogActionsResponse>(
    API_ENDPOINTS.DASHBOARD.ACTIVITY.ACTIONS,
    {
      params: buildQueryParams(filters),
    }
  );

  return getOrThrowData(response, 'Dashboard activity log actions response was empty');
};
