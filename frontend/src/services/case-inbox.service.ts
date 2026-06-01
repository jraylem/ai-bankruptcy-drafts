/** Thin REST client for the v2 Case Inbox.
 *
 * Backed by `/api/v2/core/case-inbox/*`. Auth piggybacks on `apiService`
 * which handles cookies + Bearer fallback. Accept and Summon both hit
 * the same /accept endpoint — the BE tolerates both ready and archived
 * source statuses. The FE just relabels the button.
 */

import { API_ENDPOINTS } from '@/constants';
import { apiService } from '@/services/api';
import type { ApiResponse } from '@/types';
import type {
  CaseInboxDismissResponse,
  CaseInboxListResponse,
} from '@/types/case-inbox';
import type { CreateCaseResult } from '@/types/studio/resolution';

export const fetchCaseInbox = (): Promise<ApiResponse<CaseInboxListResponse>> =>
  apiService.get<CaseInboxListResponse>(API_ENDPOINTS.CORE.CASE_INBOX_LIST);

export const fetchCaseInboxArchived = (
  params: { q?: string; limit?: number; offset?: number } = {},
): Promise<ApiResponse<CaseInboxListResponse>> => {
  const searchParams = new URLSearchParams();
  if (params.q) searchParams.set('q', params.q);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params.offset !== undefined) searchParams.set('offset', String(params.offset));
  const qs = searchParams.toString();
  const url = qs
    ? `${API_ENDPOINTS.CORE.CASE_INBOX_ARCHIVED}?${qs}`
    : API_ENDPOINTS.CORE.CASE_INBOX_ARCHIVED;
  return apiService.get<CaseInboxListResponse>(url);
};

/** Accept (when row is ready) OR Summon (when row is archived).
 *  Same endpoint either way — BE tolerates both source statuses. */
export const acceptCaseInbox = (
  id: string,
): Promise<ApiResponse<CreateCaseResult>> =>
  apiService.post<CreateCaseResult>(API_ENDPOINTS.CORE.CASE_INBOX_ACCEPT(id), {});

export const dismissCaseInbox = (
  id: string,
): Promise<ApiResponse<CaseInboxDismissResponse>> =>
  apiService.post<CaseInboxDismissResponse>(
    API_ENDPOINTS.CORE.CASE_INBOX_DISMISS(id),
    {},
  );
