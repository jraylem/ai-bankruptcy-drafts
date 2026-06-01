/**
 * Thin REST client for the Studio V2 dry-run-async pipeline.
 *
 * Backed by `/api/v3/studio/dry-run-async/*`. Mirrors
 * `studioV2ComposerAsync.service.ts` shape but for a richer state
 * machine that includes AWAITING_INPUT + RESUMING (pause/resume
 * protocol the composer doesn't need).
 *
 * The state machine: QUEUED → PENDING → RUNNING → {COMPLETED, FAILED,
 * CANCELLED} OR QUEUED → PENDING → RUNNING → AWAITING_INPUT →
 * RESUMING → COMPLETED.
 *
 * Distinct from composer-async because:
 * 1. Dry-run carries the EXPERIMENTAL spec (from the wizard's working
 *    draft) — never reads `published_spec`.
 * 2. Pause/resume — initial may hit AWAITING_INPUT, FE submits picks
 *    via /submit-input, worker resumes.
 * 3. Lower concurrency caps (5 vs 10) — diagnostic tools, not
 *    committed work.
 */

import { API_BASE_URL, API_ENDPOINTS } from '@/constants';
import apiService from '@/services/api';
import type { ApiResponse } from '@/types';
import type {
  DryRunResponseV2,
  PendingUserInputV2,
  ResolvedTemplateValueV2,
  TemplateSpecV2Wire,
  UserSelectionV2,
} from '@/types/studio-v2';

// ─── BE-facing types ────────────────────────────────────────────────

export type V2DryRunStatus =
  | 'QUEUED'
  | 'PENDING'
  | 'RUNNING'
  | 'AWAITING_INPUT'
  | 'RESUMING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export const ACTIVE_DRY_RUN_STATES: ReadonlySet<V2DryRunStatus> =
  new Set<V2DryRunStatus>([
    'QUEUED',
    'PENDING',
    'RUNNING',
    'AWAITING_INPUT',
    'RESUMING',
  ]);

export const TERMINAL_DRY_RUN_STATES: ReadonlySet<V2DryRunStatus> =
  new Set<V2DryRunStatus>(['COMPLETED', 'FAILED', 'CANCELLED']);

/**
 * One dry-run task record — pulled from `GET /tasks`, the SSE
 * snapshot event, OR an individual status_changed / awaiting_input /
 * completed / failed event.
 *
 * Carries the full pipeline context (template_spec, bundle config,
 * pending_inputs, resolved_values) so the FE can re-open the
 * pending-input modal from any state and the worker can resume
 * without the FE re-sending everything.
 */
export interface V2DryRunTask {
  task_id: string;
  user_id: string;
  template_id: string;
  case_id: string;
  template_name: string;
  case_label: string;
  status: V2DryRunStatus;
  template_spec: TemplateSpecV2Wire;
  bundle_picks: Record<string, string> | null;
  bundle_role: string | null;
  bundle_companions: Array<Record<string, unknown>> | null;
  resolved_values: ResolvedTemplateValueV2[] | null;
  pending_inputs: Record<string, PendingUserInputV2> | null;
  user_picks: Record<string, UserSelectionV2> | null;
  result: DryRunResponseV2 | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface StartDryRunResponse {
  task_id: string;
  status: V2DryRunStatus;
}

export interface StartDryRunBody {
  template_id: string;
  case_id: string;
  template_spec: TemplateSpecV2Wire;
  bundle_picks?: Record<string, string> | null;
  bundle_role?: string | null;
  bundle_companions?: Array<Record<string, unknown>> | null;
}

export interface SubmitInputBody {
  user_picks: Record<string, UserSelectionV2>;
  bundle_picks?: Record<string, string> | null;
}

// ─── Endpoints ──────────────────────────────────────────────────────

/**
 * Kick off a fresh async dry-run task.
 *
 * Returns immediately with `{ task_id, status }` (PENDING or QUEUED).
 * The actual pipeline work runs in the Taskiq worker; the FE watches
 * the SSE stream for status transitions.
 */
export async function startDryRunAsync(
  body: StartDryRunBody,
): Promise<ApiResponse<StartDryRunResponse>> {
  return apiService.post<StartDryRunResponse>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN_ASYNC_START,
    body,
  );
}

/**
 * Submit the paralegal's picks for a paused dry-run. Only valid when
 * the task is AWAITING_INPUT — server flips to RESUMING + enqueues
 * the resume worker.
 */
export async function submitDryRunAsyncInput(
  taskId: string,
  body: SubmitInputBody,
): Promise<ApiResponse<StartDryRunResponse>> {
  return apiService.post<StartDryRunResponse>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN_ASYNC_SUBMIT_INPUT(taskId),
    body,
  );
}

/** Mark a task CANCELLED. */
export async function cancelDryRunAsyncTask(
  taskId: string,
): Promise<ApiResponse<V2DryRunTask>> {
  return apiService.post<V2DryRunTask>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN_ASYNC_CANCEL(taskId),
    {},
  );
}

/** Hard-dismiss a task record from the rail. */
export async function dismissDryRunAsyncTask(
  taskId: string,
): Promise<ApiResponse<{ removed: boolean; task_id: string }>> {
  return apiService.delete<{ removed: boolean; task_id: string }>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN_ASYNC_DISMISS(taskId),
  );
}

/** Cold-load all tasks for the current user (polling fallback). */
export async function listDryRunAsyncTasks(): Promise<ApiResponse<V2DryRunTask[]>> {
  return apiService.get<V2DryRunTask[]>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN_ASYNC_TASKS,
  );
}

/** Fetch a single task (polling fallback when SSE unavailable). */
export async function getDryRunAsyncTask(
  taskId: string,
): Promise<ApiResponse<V2DryRunTask>> {
  return apiService.get<V2DryRunTask>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN_ASYNC_TASK_BY_ID(taskId),
  );
}

/** Absolute URL for the EventSource subscription. */
export function buildDryRunAsyncEventsUrl(): string {
  return `${API_BASE_URL}${API_ENDPOINTS.STUDIO_V2.DRY_RUN_ASYNC_EVENTS}`;
}
