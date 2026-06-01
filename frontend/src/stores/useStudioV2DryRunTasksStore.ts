/**
 * Zustand store for Studio V2 dry-run-async tasks.
 *
 * Mirrors `useStudioV2ComposerTasksStore` shape with two deltas the
 * pause/resume protocol needs:
 *   - `submitInput(taskId, picks)` — resumes a paused (AWAITING_INPUT)
 *     task with the paralegal's picks. The composer store has no
 *     equivalent because composer never pauses.
 *   - `AWAITING_INPUT` cards stay until the user submits or cancels
 *     (no auto-dismiss timer — they're actively waiting for input).
 *
 * Receives every task update via SSE (`studioV2DryRunAsyncEvents.service.ts`)
 * and forwards REST actions to `studioV2DryRunAsync.service.ts`.
 *
 * Scope: this store + its SSE consumer mount ONLY on `/studio-v2`.
 * Dry-run cards never bleed into chat or cases pages.
 */

import { create } from 'zustand';

import {
  ACTIVE_DRY_RUN_STATES,
  cancelDryRunAsyncTask,
  dismissDryRunAsyncTask,
  listDryRunAsyncTasks,
  startDryRunAsync,
  submitDryRunAsyncInput,
  type StartDryRunBody,
  type SubmitInputBody,
  type V2DryRunTask,
} from '@/services/studioV2DryRunAsync.service';

const DISMISSED_TOMBSTONE_MAX = 200;

/**
 * Auto-dismiss only fires for CANCELLED — user explicitly killed the
 * task, no need to keep the chip around.
 *
 * COMPLETED chips persist until the paralegal explicitly dismisses
 * them (× button). Mirrors v1 pleading's chat-page chip behavior:
 * a completed dry-run IS the rendered docx record (no separate
 * "templates list" landing spot to take its place, unlike the
 * composer card which dismisses after the new template lands in the
 * rail). Auto-dismissing COMPLETED would silently delete the chip
 * the paralegal just got and ruin the "fire 3 dry-runs in parallel,
 * come back later to inspect each result" workflow.
 *
 * FAILED tasks are also never auto-dismissed — user reads the error
 * and ×'s it themselves (Nielsen #9, error visibility).
 *
 * AWAITING_INPUT NEVER auto-dismisses — the task is parked waiting
 * for user action; auto-dismissing would silently throw away a
 * paused pipeline.
 */
const AUTO_DISMISS_DELAY_MS: Record<'CANCELLED', number> = {
  CANCELLED: 3000,
};

export interface DryRunActionResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
  /** BE detail.code on 429 (QUEUE_FULL). */
  code?: string;
}

export interface StudioV2DryRunTasksState {
  tasks: Record<string, V2DryRunTask>;
  /**
   * Tombstone set: task ids that have been locally dismissed or
   * BE-removed during this session. Drops stale SSE events emitted
   * just before the dismiss landed. Bounded at 200 entries.
   */
  dismissedTaskIds: Set<string>;
  /**
   * Task ids whose DELETE is currently in flight — render the card
   * in a muted state with a spinner instead of the × button.
   */
  dismissingTaskIds: Set<string>;
  /**
   * When set, the FE focuses this task's pending-input modal once it
   * lands in AWAITING_INPUT (mirrors composer-async's
   * `autoSelectOnCompleteTaskId` pattern).
   */
  focusOnAwaitingInputTaskId: string | null;
  error: string | null;

  // SSE / hydration
  applySnapshot: (tasks: V2DryRunTask[]) => void;
  upsertTask: (task: V2DryRunTask) => void;
  removeTask: (taskId: string) => void;
  loadTasks: () => Promise<void>;

  // User actions (REST)
  startDryRun: (body: StartDryRunBody) => Promise<DryRunActionResult<{ taskId: string }>>;
  submitInput: (
    taskId: string,
    body: SubmitInputBody,
  ) => Promise<DryRunActionResult>;
  cancelTask: (taskId: string) => Promise<DryRunActionResult>;
  dismissTask: (taskId: string) => Promise<DryRunActionResult>;

  // Focus
  setFocusOnAwaitingInputTaskId: (taskId: string | null) => void;
  clearError: () => void;
}

/**
 * Module-level map of `task_id → timeout handle` so we only schedule
 * ONE auto-dismiss per task even if the same status arrives multiple
 * times via SSE (e.g. snapshot reconnect after a transition). Lives
 * outside the Zustand store because it's pure side-effect state, not
 * UI state.
 */
const autoDismissTimers = new Map<string, ReturnType<typeof setTimeout>>();

function scheduleAutoDismiss(
  taskId: string,
  status: V2DryRunTask['status'],
  dismiss: (taskId: string) => Promise<unknown>,
): void {
  // Only CANCELLED auto-dismisses. COMPLETED stays until explicit ×
  // (v1 pleading chip behavior) — see AUTO_DISMISS_DELAY_MS comment.
  if (status !== 'CANCELLED') return;
  if (autoDismissTimers.has(taskId)) return; // already scheduled
  const delay = AUTO_DISMISS_DELAY_MS.CANCELLED;
  const handle = setTimeout(() => {
    autoDismissTimers.delete(taskId);
    void dismiss(taskId);
  }, delay);
  autoDismissTimers.set(taskId, handle);
}

function cancelAutoDismiss(taskId: string): void {
  const handle = autoDismissTimers.get(taskId);
  if (handle) {
    clearTimeout(handle);
    autoDismissTimers.delete(taskId);
  }
}

function addTombstone(set: Set<string>, taskId: string): Set<string> {
  if (set.has(taskId)) return set;
  const next = new Set(set);
  next.add(taskId);
  while (next.size > DISMISSED_TOMBSTONE_MAX) {
    const oldest = next.values().next().value;
    if (oldest === undefined) break;
    next.delete(oldest);
  }
  return next;
}

export const useStudioV2DryRunTasksStore = create<StudioV2DryRunTasksState>(
  (set, get) => ({
    tasks: {},
    dismissedTaskIds: new Set<string>(),
    dismissingTaskIds: new Set<string>(),
    focusOnAwaitingInputTaskId: null,
    error: null,

    applySnapshot: (tasks) => {
      const dismissed = get().dismissedTaskIds;
      const next: Record<string, V2DryRunTask> = {};
      for (const t of tasks) {
        if (dismissed.has(t.task_id)) continue;
        next[t.task_id] = t;
        // Snapshot rehydration may carry tasks already in a terminal
        // success state (cold reload after the worker finished); make
        // sure they still auto-dismiss instead of sticking forever.
        scheduleAutoDismiss(t.task_id, t.status, (id) => get().dismissTask(id));
      }
      set({ tasks: next });
    },

    upsertTask: (task) => {
      const state = get();
      if (state.dismissedTaskIds.has(task.task_id)) return;
      set({
        tasks: { ...state.tasks, [task.task_id]: task },
      });
      // Schedule the rail-clearance side effect AFTER the state update
      // so the user sees the terminal pill for the configured delay,
      // then the card vanishes automatically. AWAITING_INPUT and
      // FAILED stay put.
      scheduleAutoDismiss(task.task_id, task.status, (id) => get().dismissTask(id));
    },

    removeTask: (taskId) => {
      cancelAutoDismiss(taskId);
      const state = get();
      const nextTasks = { ...state.tasks };
      delete nextTasks[taskId];
      const nextDismissing = new Set(state.dismissingTaskIds);
      nextDismissing.delete(taskId);
      set({
        tasks: nextTasks,
        dismissedTaskIds: addTombstone(state.dismissedTaskIds, taskId),
        dismissingTaskIds: nextDismissing,
      });
    },

    loadTasks: async () => {
      const response = await listDryRunAsyncTasks();
      if (response.data) {
        get().applySnapshot(response.data);
      }
    },

    startDryRun: async (body) => {
      set({ error: null });
      const response = await startDryRunAsync(body);
      if (!response.data) {
        const err = response.error || 'Failed to start dry-run';
        set({ error: err });
        return { success: false, error: err };
      }
      // Mark this task for auto-focus once it hits AWAITING_INPUT so
      // the paralegal sees the pick modal pop without hunting for the
      // card. Optimistic placeholder isn't worth it here — the BE
      // round-trip is sub-100ms and the SSE event arrives shortly.
      set({ focusOnAwaitingInputTaskId: response.data.task_id });
      return { success: true, data: { taskId: response.data.task_id } };
    },

    submitInput: async (taskId, body) => {
      set({ error: null });
      const response = await submitDryRunAsyncInput(taskId, body);
      if (!response.data) {
        const err = response.error || 'Failed to submit input';
        set({ error: err });
        return { success: false, error: err };
      }
      return { success: true };
    },

    cancelTask: async (taskId) => {
      const response = await cancelDryRunAsyncTask(taskId);
      if (!response.data) {
        return { success: false, error: response.error };
      }
      get().upsertTask(response.data);
      return { success: true };
    },

    dismissTask: async (taskId) => {
      const state = get();
      const nextDismissing = new Set(state.dismissingTaskIds);
      nextDismissing.add(taskId);
      set({ dismissingTaskIds: nextDismissing });

      const response = await dismissDryRunAsyncTask(taskId);
      if (!response.data) {
        // Restore the dismissing state so the user can retry.
        const restore = new Set(get().dismissingTaskIds);
        restore.delete(taskId);
        set({ dismissingTaskIds: restore });
        return { success: false, error: response.error };
      }
      // BE returned success — drop the task from the store + tombstone.
      get().removeTask(taskId);
      return { success: true };
    },

    setFocusOnAwaitingInputTaskId: (taskId) => {
      set({ focusOnAwaitingInputTaskId: taskId });
    },

    clearError: () => set({ error: null }),
  }),
);

// ─── Selectors ────────────────────────────────────────────────────────

export function selectActiveDryRunTasks(
  state: StudioV2DryRunTasksState,
): V2DryRunTask[] {
  return Object.values(state.tasks)
    .filter((t) => ACTIVE_DRY_RUN_STATES.has(t.status))
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export function selectTerminalDryRunTasks(
  state: StudioV2DryRunTasksState,
): V2DryRunTask[] {
  return Object.values(state.tasks)
    .filter((t) => !ACTIVE_DRY_RUN_STATES.has(t.status))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function selectDryRunTaskById(
  state: StudioV2DryRunTasksState,
  taskId: string | null | undefined,
): V2DryRunTask | undefined {
  if (!taskId) return undefined;
  return state.tasks[taskId];
}
