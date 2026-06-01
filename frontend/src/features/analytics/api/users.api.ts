import { apiService } from '@/services/api';
import { API_ENDPOINTS } from '@/constants';
import type {
  DashboardUserDetailQuery,
  DashboardAnalyticsFilters,
  DashboardUsersDetailExportQuery,
  DashboardUsersAnalyticsQuery,
  DashboardUsersAnalyticsResponse,
  UserDetailViewModel,
} from '../types';
import { buildQueryParams, getOrThrowData } from './shared.api';

export const fetchDashboardAnalyticsUsers = async (
  filters: DashboardAnalyticsFilters,
  query: DashboardUsersAnalyticsQuery = {}
): Promise<DashboardUsersAnalyticsResponse> => {
  const response = await apiService.get<DashboardUsersAnalyticsResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.USERS,
    {
      params: {
        ...buildQueryParams(filters),
        ...(query.page ? { page: query.page } : {}),
        ...(query.page_size ? { page_size: query.page_size } : {}),
        ...(query.sort_by ? { sort_by: query.sort_by } : {}),
        ...(query.sort_dir ? { sort_dir: query.sort_dir } : {}),
        ...(query.search ? { search: query.search } : {}),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard analytics users response was empty');
};

export const exportDashboardAnalyticsUsersXlsx = async (
  filters: DashboardAnalyticsFilters,
  query: Omit<DashboardUsersAnalyticsQuery, 'page' | 'page_size'> = {}
): Promise<Blob> => {
  const response = await apiService.get<Blob>(API_ENDPOINTS.DASHBOARD.EXPORT.USERS, {
    responseType: 'blob',
    params: {
      ...buildQueryParams(filters),
      ...(query.sort_by ? { sort_by: query.sort_by } : {}),
      ...(query.sort_dir ? { sort_dir: query.sort_dir } : {}),
      ...(query.search ? { search: query.search } : {}),
    },
  });

  if (response.error) {
    throw new Error(response.error);
  }

  if (!response.data) {
    throw new Error('Dashboard analytics users export response was empty');
  }

  return response.data;
};

export const exportDashboardAnalyticsUserXlsx = async (
  userId: string,
  filters: DashboardAnalyticsFilters,
  query: DashboardUsersDetailExportQuery = {}
): Promise<Blob> => {
  const response = await apiService.get<Blob>(API_ENDPOINTS.DASHBOARD.EXPORT.USER(userId), {
    responseType: 'blob',
    params: {
      ...buildQueryParams(filters),
      ...query,
    },
  });

  if (response.error) {
    throw new Error(response.error);
  }

  if (!response.data) {
    throw new Error('Dashboard analytics single-user export response was empty');
  }

  return response.data;
};

export const fetchDashboardAnalyticsUserDetail = async (
  userId: string,
  filters: DashboardAnalyticsFilters,
  query: DashboardUserDetailQuery = {}
): Promise<UserDetailViewModel> => {
  const response = await apiService.get<UserDetailViewModel>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.USER_DETAIL(userId),
    {
      params: {
        ...buildQueryParams(filters),
        ...query,
      },
    }
  );

  return getOrThrowData(response, 'Dashboard analytics user detail response was empty');
};
