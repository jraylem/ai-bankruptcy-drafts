/**
 * Thin REST client for the Studio V2 composer-async pipeline.
 *
 * Backed by `/api/v3/studio/composer-async/*`. Mirrors
 * `templateDraft.service.ts` shape. Returns task records that the
 * Zustand store + SSE consumer keep in sync.
 *
 * The composer state machine is SIMPLER than the v2 pleading state
 * machine — no CHECKING_EXISTING / EXISTING_FOUND / AWAITING_INPUT
 * / resume. Just: QUEUED → PENDING → RUNNING → COMPLETED / FAILED /
 * CANCELLED.
 */

import { API_BASE_URL, API_ENDPOINTS } from '@/constants';
import apiService from '@/services/api';
import type { ApiResponse } from '@/types';

/**
 * Axios's default header is `application/json` (set on the shared
 * client in `services/api.ts`). For multipart uploads we MUST force
 * `multipart/form-data` so axios serializes the FormData with a
 * `boundary` rather than JSON-stringifying it into an empty body.
 * Mirrors `studioV2.service.ts`'s MULTIPART_HEADERS pattern.
 */
const MULTIPART_HEADERS = { 'Content-Type': 'multipart/form-data' };

// ─── BE-facing types ────────────────────────────────────────────────

export type V2ComposerTaskKind = 'generate' | 'regenerate';

export type V2ComposerTaskStatus =
  | 'QUEUED'
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export const ACTIVE_COMPOSER_TASK_STATES: ReadonlySet<V2ComposerTaskStatus> =
  new Set<V2ComposerTaskStatus>(['QUEUED', 'PENDING', 'RUNNING']);

export const TERMINAL_COMPOSER_TASK_STATES: ReadonlySet<V2ComposerTaskStatus> =
  new Set<V2ComposerTaskStatus>(['COMPLETED', 'FAILED', 'CANCELLED']);

/** Result payload returned by the BE after a successful generate. */
export interface GenerateResultPayload {
  template_id: string;
  name: string;
  template_spec: unknown[];
  original_doc_url: string;
  template_doc_url: string;
}

/** Result payload returned by the BE after a successful regenerate. */
export interface RegenerateResultPayload {
  template_id: string;
  inserted: string[];
  updated: string[];
  deleted: string[];
  preserved_params: string[];
  template_doc_url: string;
}

/**
 * One composer task record — pulled from `GET /tasks`, the SSE
 * snapshot event, OR an individual status_changed / completed /
 * failed event.
 */
export interface V2ComposerTask {
  task_id: string;
  user_id: string;
  kind: V2ComposerTaskKind;
  template_name: string;
  template_id: string | null;
  status: V2ComposerTaskStatus;
  template_role: string;
  original_filename: string;
  generate_result: GenerateResultPayload | null;
  regenerate_result: RegenerateResultPayload | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartComposerTaskResponse {
  task_id: string;
  status: V2ComposerTaskStatus;
}

export interface StartRegenerateBody {
  template_id: string;
  ignored_texts?: string[] | null;
  merges?: Array<{
    new_variable_name?: string | null;
    source_variables: string[];
    description?: string | null;
  }> | null;
  regeneration_instruction?: string | null;
}

// ─── Endpoints ──────────────────────────────────────────────────────

/**
 * Kick off a fresh async template-generation task.
 *
 * Returns immediately with `{ task_id, status }` (PENDING or QUEUED).
 * The actual TemplateAgentV2 work runs in the Taskiq worker; the FE
 * watches the SSE stream for status_changed → completed/failed.
 */
export async function startComposerGenerate(
  file: File,
  templateName: string,
  templateRole: 'single' | 'master' | 'part_of_packet' = 'single',
): Promise<ApiResponse<StartComposerTaskResponse>> {
  const form = new FormData();
  form.append('file', file);
  form.append('template_name', templateName);
  form.append('template_role', templateRole);
  return apiService.post<StartComposerTaskResponse>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_ASYNC_GENERATE,
    form,
    { headers: MULTIPART_HEADERS },
  );
}

/**
 * Kick off a fresh async template-regenerate (re-extract) task for
 * an existing template.
 */
export async function startComposerRegenerate(
  body: StartRegenerateBody,
): Promise<ApiResponse<StartComposerTaskResponse>> {
  return apiService.post<StartComposerTaskResponse>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_ASYNC_REGENERATE,
    body,
  );
}

/** Mark a task CANCELLED. */
export async function cancelComposerTask(
  taskId: string,
): Promise<ApiResponse<V2ComposerTask>> {
  return apiService.post<V2ComposerTask>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_ASYNC_CANCEL(taskId),
    {},
  );
}

/** Hard-dismiss a task record from the strip. */
export async function dismissComposerTask(
  taskId: string,
): Promise<ApiResponse<{ removed: boolean; task_id: string }>> {
  return apiService.delete<{ removed: boolean; task_id: string }>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_ASYNC_DISMISS(taskId),
  );
}

/** Cold-load all tasks for the current user (polling fallback). */
export async function listComposerTasks(): Promise<ApiResponse<V2ComposerTask[]>> {
  return apiService.get<V2ComposerTask[]>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_ASYNC_TASKS,
  );
}

/** Fetch a single task (polling fallback when SSE unavailable). */
export async function getComposerTask(
  taskId: string,
): Promise<ApiResponse<V2ComposerTask>> {
  return apiService.get<V2ComposerTask>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_ASYNC_TASK_BY_ID(taskId),
  );
}

/** Absolute URL for the EventSource subscription. */
export function buildComposerEventsUrl(): string {
  return `${API_BASE_URL}${API_ENDPOINTS.STUDIO_V2.COMPOSER_ASYNC_EVENTS}`;
}
