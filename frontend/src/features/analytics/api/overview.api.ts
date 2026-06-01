import { apiService } from '@/services/api';
import { API_ENDPOINTS } from '@/constants';
import type {
  DashboardApiCallsResponse,
  DashboardAnalyticsFilters,
  DashboardCasesDailyResponse,
  DashboardCasesResponse,
  DashboardMotionsByTypeResponse,
  DashboardMotionsDailyResponse,
  DashboardMotionsResponse,
  DashboardSystemStatusResponse,
  DashboardUsersDailyResponse,
  DashboardUsersResponse,
} from '../types';
import { buildQueryParams, getOrThrowData } from './shared.api';

export const fetchDashboardCases = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardCasesResponse> => {
  const response = await apiService.get<DashboardCasesResponse>(API_ENDPOINTS.DASHBOARD.CASES, {
    params: buildQueryParams(filters),
  });

  return getOrThrowData(response, 'Dashboard cases response was empty');
};

export const fetchDashboardUsers = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardUsersResponse> => {
  const response = await apiService.get<DashboardUsersResponse>(API_ENDPOINTS.DASHBOARD.USERS, {
    params: buildQueryParams(filters),
  });

  return getOrThrowData(response, 'Dashboard users response was empty');
};

export const fetchDashboardMotions = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardMotionsResponse> => {
  const response = await apiService.get<DashboardMotionsResponse>(API_ENDPOINTS.DASHBOARD.MOTIONS, {
    params: buildQueryParams(filters),
  });

  return getOrThrowData(response, 'Dashboard motions response was empty');
};

export const fetchDashboardMotionsDaily = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardMotionsDailyResponse> => {
  const response = await apiService.get<DashboardMotionsDailyResponse>(
    API_ENDPOINTS.DASHBOARD.CHARTS.MOTIONS_DAILY,
    {
      params: buildQueryParams(filters),
    }
  );

  return getOrThrowData(response, 'Dashboard motions daily response was empty');
};

export const fetchDashboardCasesDaily = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardCasesDailyResponse> => {
  const response = await apiService.get<DashboardCasesDailyResponse>(
    API_ENDPOINTS.DASHBOARD.CHARTS.CASES_DAILY,
    {
      params: buildQueryParams(filters),
    }
  );

  return getOrThrowData(response, 'Dashboard cases daily response was empty');
};

export const fetchDashboardUsersDaily = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardUsersDailyResponse> => {
  const response = await apiService.get<DashboardUsersDailyResponse>(
    API_ENDPOINTS.DASHBOARD.CHARTS.USERS_DAILY,
    {
      params: buildQueryParams(filters),
    }
  );

  return getOrThrowData(response, 'Dashboard users daily response was empty');
};

export const fetchDashboardApiCalls = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardApiCallsResponse> => {
  const response = await apiService.get<DashboardApiCallsResponse>(
    API_ENDPOINTS.DASHBOARD.KPIS.API_CALLS,
    {
      params: buildQueryParams(filters),
    }
  );

  return getOrThrowData(response, 'Dashboard API calls response was empty');
};

export const fetchDashboardMotionsByType = async (
  filters: DashboardAnalyticsFilters
): Promise<DashboardMotionsByTypeResponse> => {
  const response = await apiService.get<DashboardMotionsByTypeResponse>(
    API_ENDPOINTS.DASHBOARD.CHARTS.MOTIONS_BY_TYPE,
    {
      params: buildQueryParams(filters),
    }
  );

  return getOrThrowData(response, 'Dashboard motions by type response was empty');
};

export const fetchDashboardSystemStatus = async (): Promise<DashboardSystemStatusResponse> => {
  const response = await apiService.get<DashboardSystemStatusResponse>(
    API_ENDPOINTS.DASHBOARD.SYSTEM.STATUS
  );

  return getOrThrowData(response, 'Dashboard system status response was empty');
};
