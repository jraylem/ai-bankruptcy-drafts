import { apiService } from '@/services/api';
import { API_ENDPOINTS } from '@/constants';
import type {
  DashboardAnalyticsFilters,
  DashboardMotionSessionDetailQuery,
  DashboardMotionSessionDetailResponse,
  DashboardMotionsAnalyticsQuery,
  DashboardMotionsAnalyticsResponse,
} from '../types';
import { buildQueryParams, getOrThrowData } from './shared.api';

export const fetchDashboardAnalyticsMotions = async (
  filters: DashboardAnalyticsFilters,
  query: DashboardMotionsAnalyticsQuery = {}
): Promise<DashboardMotionsAnalyticsResponse> => {
  const response = await apiService.get<DashboardMotionsAnalyticsResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.MOTIONS,
    {
      params: {
        ...buildQueryParams(filters),
        ...(query.page ? { page: query.page } : {}),
        ...(query.page_size ? { page_size: query.page_size } : {}),
        ...(query.sort_by ? { sort_by: query.sort_by } : {}),
        ...(query.sort_dir ? { sort_dir: query.sort_dir } : {}),
        ...(query.search ? { search: query.search } : {}),
        ...(query.motion_type ? { motion_type: query.motion_type } : {}),
        ...(query.category ? { category: query.category } : {}),
        ...(query.status ? { status: query.status } : {}),
        ...(query.district ? { district: query.district } : {}),
        ...(query.source ? { source: query.source } : {}),
        ...(query.cos_type ? { cos_type: query.cos_type } : {}),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard analytics motions response was empty');
};

export const fetchDashboardAnalyticsMotionSessionDetail = async (
  sessionId: string,
  query: DashboardMotionSessionDetailQuery = {}
): Promise<DashboardMotionSessionDetailResponse> => {
  const response = await apiService.get<DashboardMotionSessionDetailResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.MOTION_SESSION_DETAIL(sessionId),
    {
      params: {
        ...(query.page ? { page: query.page } : {}),
        ...(query.page_size ? { page_size: query.page_size } : {}),
        ...(query.sort_by ? { sort_by: query.sort_by } : {}),
        ...(query.sort_dir ? { sort_dir: query.sort_dir } : {}),
        ...(query.status ? { status: query.status } : {}),
        ...(query.category ? { category: query.category } : {}),
        ...(query.motion_type ? { motion_type: query.motion_type } : {}),
        ...(query.search ? { search: query.search } : {}),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard analytics motion session detail response was empty');
};
