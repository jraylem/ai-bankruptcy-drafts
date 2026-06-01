import { apiService } from '@/services/api';
import { API_ENDPOINTS } from '@/constants';
import type {
  DashboardCaseDetailQuery,
  DashboardAnalyticsFilters,
  DashboardCaseDetailResponse,
  DashboardCasesAnalyticsQuery,
  DashboardCasesAnalyticsResponse,
} from '../types';
import { buildQueryParams, getOrThrowData } from './shared.api';

export const fetchDashboardAnalyticsCases = async (
  filters: DashboardAnalyticsFilters,
  query: DashboardCasesAnalyticsQuery = {}
): Promise<DashboardCasesAnalyticsResponse> => {
  const response = await apiService.get<DashboardCasesAnalyticsResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.CASES,
    {
      params: {
        ...buildQueryParams(filters),
        ...(query.page ? { page: query.page } : {}),
        ...(query.page_size ? { page_size: query.page_size } : {}),
        ...(query.sort_by ? { sort_by: query.sort_by } : {}),
        ...(query.sort_dir ? { sort_dir: query.sort_dir } : {}),
        ...(query.search ? { search: query.search } : {}),
        ...(query.status ? { status: query.status } : {}),
        ...(query.district ? { district: query.district } : {}),
        ...(query.source ? { source: query.source } : {}),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard analytics cases response was empty');
};

export const fetchDashboardAnalyticsCaseDetail = async (
  sessionId: string,
  query: DashboardCaseDetailQuery = {}
): Promise<DashboardCaseDetailResponse> => {
  const response = await apiService.get<DashboardCaseDetailResponse>(
    API_ENDPOINTS.DASHBOARD.ANALYTICS.CASE_DETAIL(sessionId),
    {
      params: {
        ...(query.motions_page ? { motions_page: query.motions_page } : {}),
        ...(query.motions_page_size ? { motions_page_size: query.motions_page_size } : {}),
        ...(query.motions_search ? { motions_search: query.motions_search } : {}),
        ...(query.motions_status ? { motions_status: query.motions_status } : {}),
        ...(query.motions_motion_type ? { motions_motion_type: query.motions_motion_type } : {}),
        ...(query.motions_sort_by ? { motions_sort_by: query.motions_sort_by } : {}),
        ...(query.motions_sort_dir ? { motions_sort_dir: query.motions_sort_dir } : {}),
        ...(query.timeline_page ? { timeline_page: query.timeline_page } : {}),
        ...(query.timeline_page_size ? { timeline_page_size: query.timeline_page_size } : {}),
        ...(query.timeline_event ? { timeline_event: query.timeline_event } : {}),
        ...(query.timeline_actor_id ? { timeline_actor_id: query.timeline_actor_id } : {}),
        ...(query.timeline_search ? { timeline_search: query.timeline_search } : {}),
        ...(query.timeline_sort_dir ? { timeline_sort_dir: query.timeline_sort_dir } : {}),
      },
    }
  );

  return getOrThrowData(response, 'Dashboard analytics case detail response was empty');
};
