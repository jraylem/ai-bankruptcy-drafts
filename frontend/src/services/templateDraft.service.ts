/**
 * Thin REST client for the v2 template-draft pipeline.
 *
 * Backed by `/api/v2/core/pleading/*`. Auth flows through `apiService` which
 * auto-attaches the `Authorization: Bearer <jwt>` header app-wide — this
 * service never reads the token directly.
 */

import { API_BASE_URL, API_ENDPOINTS } from '@/constants';
import { withCookieCredentials } from '@/features/auth/auth.requests';
import apiService from '@/services/api';
import type { ApiResponse } from '@/types';
import type {
  PendingUserInput,
  ResolvedTemplateValue,
  UserSelection,
} from '@/types/studio/resolution';

// ─── BE-facing types ────────────────────────────────────────────────

export type V2TaskStatus =
  | 'QUEUED'
  | 'PENDING'
  | 'CHECKING_EXISTING'
  | 'EXISTING_FOUND'
  | 'DRAFTING'
  | 'AWAITING_INPUT'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export const ACTIVE_TASK_STATES: ReadonlySet<V2TaskStatus> = new Set<V2TaskStatus>([
  'QUEUED',
  'PENDING',
  'CHECKING_EXISTING',
  'EXISTING_FOUND',
  'DRAFTING',
  'AWAITING_INPUT',
]);

export interface DraftChildResultPayload {
  template_id: string;
  template_name: string;
  companion_label: string;
  generated_doc_url: string;
  r2_object_key: string;
  resolved_values: ResolvedTemplateValue[];
  warnings: string[];
}

export interface DraftResponsePayload {
  status: 'completed';
  template_id: string;
  case_id: string;
  resolved_values: ResolvedTemplateValue[];
  generated_doc_url: string;
  r2_object_key: string;
  validation: { valid: boolean; errors: string[]; warnings: string[] };
  children: DraftChildResultPayload[];
}

export interface V2TemplateDraftTask {
  task_id: string;
  user_id: string;
  case_id: string;
  template_id: string;
  template_name: string;
  status: V2TaskStatus;
  bundle_picks: Record<string, string> | null;
  resolved_values: ResolvedTemplateValue[] | null;
  pending_inputs: Record<string, PendingUserInput> | null;
  log_id: string | null;
  existing_log_id: string | null;
  result: DraftResponsePayload | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartTemplateDraftRequest {
  template_id: string;
  case_id: string;
  bundle_picks?: Record<string, string> | null;
  skip_existing_check?: boolean;
}

export interface StartTemplateDraftResponse {
  task: V2TemplateDraftTask;
}

export interface CaseGenerationLogEntry {
  id: string;
  user_id: string;
  case_id: string;
  draft_template_id: string;
  template_name: string | null;
  status: string;
  task_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ChildPresignedEntry {
  template_id: string;
  template_name: string;
  companion_label: string;
  url: string;
}

export interface CompletedDocumentEnvelope {
  log_id: string;
  parent_template_id: string;
  parent_url: string;
  children: ChildPresignedEntry[];
}

// ─── REST calls ─────────────────────────────────────────────────────

export const startTemplateDraft = (
  req: StartTemplateDraftRequest,
): Promise<ApiResponse<StartTemplateDraftResponse>> =>
  apiService.post<StartTemplateDraftResponse>(API_ENDPOINTS.PLEADING_V2.START, req);

export const submitTemplateDraftInput = (
  taskId: string,
  userPicks: Record<string, UserSelection>,
): Promise<ApiResponse<V2TemplateDraftTask>> =>
  apiService.post<V2TemplateDraftTask>(API_ENDPOINTS.PLEADING_V2.SUBMIT_INPUT(taskId), {
    user_picks: userPicks,
  });

export const useExistingTemplateDraft = (
  taskId: string,
): Promise<ApiResponse<V2TemplateDraftTask>> =>
  apiService.post<V2TemplateDraftTask>(
    API_ENDPOINTS.PLEADING_V2.USE_EXISTING(taskId),
    {},
  );

export const regenerateTemplateDraft = (
  taskId: string,
): Promise<ApiResponse<V2TemplateDraftTask>> =>
  apiService.post<V2TemplateDraftTask>(
    API_ENDPOINTS.PLEADING_V2.REGENERATE(taskId),
    {},
  );

export const cancelTemplateDraft = (
  taskId: string,
): Promise<ApiResponse<V2TemplateDraftTask>> =>
  apiService.post<V2TemplateDraftTask>(API_ENDPOINTS.PLEADING_V2.CANCEL(taskId), {});

export const dismissTemplateDraft = (
  taskId: string,
): Promise<ApiResponse<{ dismissed: boolean }>> =>
  apiService.delete<{ dismissed: boolean }>(API_ENDPOINTS.PLEADING_V2.DISMISS(taskId));

export const listActiveTemplateDrafts = (
  { caseId }: { caseId?: string } = {},
): Promise<ApiResponse<V2TemplateDraftTask[]>> => {
  const url = caseId
    ? `${API_ENDPOINTS.PLEADING_V2.TASKS}?case_id=${encodeURIComponent(caseId)}`
    : API_ENDPOINTS.PLEADING_V2.TASKS;
  return apiService.get<V2TemplateDraftTask[]>(url);
};

export const getTemplateDraftTask = (
  taskId: string,
): Promise<ApiResponse<V2TemplateDraftTask>> =>
  apiService.get<V2TemplateDraftTask>(API_ENDPOINTS.PLEADING_V2.TASK_BY_ID(taskId));

export const getCompletedDocumentEnvelope = (
  logId: string,
): Promise<ApiResponse<CompletedDocumentEnvelope>> =>
  apiService.get<CompletedDocumentEnvelope>(
    API_ENDPOINTS.PLEADING_V2.CASE_GENERATION_LOG_DOWNLOAD(logId),
  );

export interface AutosaveDocxResponse {
  ok: boolean;
  log_id: string;
  r2_object_key: string;
  child_index: number | null;
  updated_at: string | null;
}

export const autosaveDocx = (
  logId: string,
  buffer: ArrayBuffer,
  { childIndex, filename }: { childIndex?: number; filename?: string } = {},
): Promise<ApiResponse<AutosaveDocxResponse>> => {
  const formData = new FormData();
  formData.append(
    'file',
    new Blob([buffer], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }),
    filename ?? 'document.docx',
  );
  const base = API_ENDPOINTS.PLEADING_V2.CASE_GENERATION_LOG_AUTOSAVE(logId);
  const url = childIndex !== undefined ? `${base}?child_index=${childIndex}` : base;
  return apiService.put<AutosaveDocxResponse>(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const listCaseGenerationLogs = (
  caseId: string,
  limit = 50,
): Promise<ApiResponse<CaseGenerationLogEntry[]>> =>
  apiService.get<CaseGenerationLogEntry[]>(
    `${API_ENDPOINTS.PLEADING_V2.CASE_GENERATION_LOGS}?case_id=${encodeURIComponent(caseId)}&limit=${limit}`,
  );

/**
 * Fetch a completed log's docx as PDF (lazy-converted server-side via LibreOffice).
 *
 * Returns the raw blob — caller is responsible for triggering the browser
 * download (see `triggerBlobDownload`). Uses `fetch` rather than apiService
 * because the response is binary, not JSON. Cookies carry the JWT, same as
 * the other binary-download flows in this codebase.
 */
export const downloadCompletedDocumentAsPdf = async (
  logId: string,
  options: { childIndex?: number } = {},
): Promise<Blob> => {
  const baseUrl: string = API_ENDPOINTS.PLEADING_V2.CASE_GENERATION_LOG_DOWNLOAD_PDF(logId);
  const path: string =
    options.childIndex == null
      ? baseUrl
      : `${baseUrl}?child_index=${encodeURIComponent(String(options.childIndex))}`;
  const response: Response = await fetch(
    `${API_BASE_URL}${path}`,
    withCookieCredentials({ method: 'GET' }),
  );
  if (!response.ok) {
    let errorMessage: string = 'Failed to download PDF';
    try {
      const errorBody = await response.json();
      const detail = errorBody?.detail;
      if (typeof detail === 'string') {
        errorMessage = detail;
      } else if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
        errorMessage = detail.message;
      }
    } catch {
      // Body wasn't JSON — keep the default message.
    }
    throw new Error(errorMessage);
  }
  return response.blob();
};

export const templateDraftApi = {
  startTemplateDraft,
  submitTemplateDraftInput,
  useExistingTemplateDraft,
  regenerateTemplateDraft,
  cancelTemplateDraft,
  dismissTemplateDraft,
  listActiveTemplateDrafts,
  getTemplateDraftTask,
  getCompletedDocumentEnvelope,
  downloadCompletedDocumentAsPdf,
  listCaseGenerationLogs,
};
