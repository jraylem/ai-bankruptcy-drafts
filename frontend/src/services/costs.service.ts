/** Thin REST client for the studio Costs panel.
 *
 * Backed by `GET /api/v2/core/costs/summary?range=week|month`. Auth
 * piggybacks on `apiService` which handles cookies + Bearer fallback.
 */

import { API_ENDPOINTS } from '@/constants';
import { apiService } from '@/services/api';
import type { ApiResponse } from '@/types';
import type { CostRange, CostsSummaryResponse } from '@/types/costs';

export const fetchCostsSummary = (
  range: CostRange,
): Promise<ApiResponse<CostsSummaryResponse>> =>
  apiService.get<CostsSummaryResponse>(
    `${API_ENDPOINTS.CORE.COSTS_SUMMARY}?range=${range}`,
  );
