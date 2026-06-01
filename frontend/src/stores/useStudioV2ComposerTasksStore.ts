/**
 * Zustand store for Studio V2 composer-async tasks.
 *
 * Mirrors `useTemplateDraftStore` shape with a simpler state machine
 * (no AWAITING_INPUT / EXISTING_FOUND / resume). Receives every task
 * update via SSE (`studioV2ComposerAsyncEvents.service.ts`) and
 * forwards REST actions to `studioV2ComposerAsync.service.ts`.
 *
 * The page mounts a single SSE subscription via
 * `startStudioV2ComposerEventStream` — the store rehydrates from the
 * `snapshot` event on connect (so cold reload always shows in-flight
 * tasks).
 */

import { create } from 'zustand';

import {
  ACTIVE_COMPOSER_TASK_STATES,
  cancelComposerTask,
  dismissComposerTask,
  listComposerTasks,
  startComposerGenerate,
  startComposerRegenerate,
  type StartRegenerateBody,
  type V2ComposerTask,
} from '@/services/studioV2ComposerAsync.service';

const DISMISSED_TOMBSTONE_MAX = 200;

/**
 * Auto-dismiss only fires for CANCELLED — user explicitly killed it,
 * no value to keep the chip around.
 *
 * COMPLETED chips persist until the paralegal explicitly hits ×.
 * Mirrors the dry-run chip behavior + the v1 pleading chat-page
 * pattern: a completed composer chip IS the entry point back to the
 * new template (click → navigate to its URL). Auto-dismissing would
 * silently delete the chip in the middle of the "fire 3 uploads in
 * parallel, come back later to open each one" workflow.
 *
 * FAILED tasks are also never auto-dismissed — the user must read
 * the error and × it themselves (Nielsen #9, error visibility).
 */
const AUTO_DISMISS_DELAY_MS: Record<'CANCELLED', number> = {
  CANCELLED: 3000,
};

export interface ComposerActionResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
  /** BE detail.code on 429 (QUEUE_FULL). */
  code?: string;
}

export interface StudioV2ComposerTasksState {
  tasks: Record<string, V2ComposerTask>;
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
  /** When set, the FE auto-selects this template once it lands COMPLETED. */
  autoSelectOnCompleteTaskId: string | null;
  error: string | null;

  // SSE / hydration
  applySnapshot: (tasks: V2ComposerTask[]) => void;
  upsertTask: (task: V2ComposerTask) => void;
  removeTask: (taskId: string) => void;
  loadTasks: () => Promise<void>;

  // User actions (REST)
  startGenerate: (
    file: File,
    templateName: string,
    templateRole?: 'single' | 'master' | 'part_of_packet',
  ) => Promise<ComposerActionResult<{ taskId: string }>>;
  startRegenerate: (body: StartRegenerateBody) => Promise<ComposerActionResult<{ taskId: string }>>;
  cancelTask: (taskId: string) => Promise<ComposerActionResult>;
  dismissTask: (taskId: string) => Promise<ComposerActionResult>;

  // Selection
  setAutoSelectOnCompleteTaskId: (taskId: string | null) => void;
  clearError: () => void;
}

/**
 * Module-level map of `task_id → timeout handle` so we only schedule
 * ONE auto-dismiss per task even if the same status arrives multiple
 * times via SSE (e.g. snapshot reconnect after a transition). Lives
 * outside the Zustand store because it's pure side-effect state, not
 * UI state — putting it in the store would force a re-render every
 * time we add/remove a timer.
 */
const autoDismissTimers = new Map<string, ReturnType<typeof setTimeout>>();

function scheduleAutoDismiss(
  taskId: string,
  status: V2ComposerTask['status'],
  dismiss: (taskId: string) => Promise<unknown>,
): void {
  // Only CANCELLED auto-dismisses. COMPLETED chips persist until the
  // paralegal explicitly hits ×.
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
    // Drop the oldest. Set iteration order is insertion order.
    const oldest = next.values().next().value;
    if (oldest === undefined) break;
    next.delete(oldest);
  }
  return next;
}

export const useStudioV2ComposerTasksStore = create<StudioV2ComposerTasksState>(
  (set, get) => ({
    tasks: {},
    dismissedTaskIds: new Set<string>(),
    dismissingTaskIds: new Set<string>(),
    autoSelectOnCompleteTaskId: null,
    error: null,

    applySnapshot: (tasks) => {
      const dismissed = get().dismissedTaskIds;
      const next: Record<string, V2ComposerTask> = {};
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
      // then the card vanishes automatically. FAILED stays put per
      // Nielsen #9.
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
      const response = await listComposerTasks();
      if (response.data) {
        get().applySnapshot(response.data);
      }
    },

    startGenerate: async (file, templateName, templateRole = 'single') => {
      set({ error: null });
      const response = await startComposerGenerate(file, templateName, templateRole);
      if (!response.data) {
        const err = response.error || 'Failed to start template upload';
        set({ error: err });
        return { success: false, error: err };
      }
      // The SSE stream delivers the new task record via the
      // status_changed event the BE emits right after enqueue; until
      // then, render an optimistic placeholder so the card appears
      // instantly without waiting for the SSE round-trip.
      const placeholder: V2ComposerTask = {
        task_id: response.data.task_id,
        user_id: '',
        kind: 'generate',
        template_name: templateName,
        template_id: null,
        status: response.data.status,
        template_role: templateRole,
        original_filename: file.name,
        generate_result: null,
        regenerate_result: null,
        error: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      get().upsertTask(placeholder);
      set({ autoSelectOnCompleteTaskId: response.data.task_id });
      return { success: true, data: { taskId: response.data.task_id } };
    },

    startRegenerate: async (body) => {
      set({ error: null });
      const response = await startComposerRegenerate(body);
      if (!response.data) {
        const err = response.error || 'Failed to start re-extract';
        set({ error: err });
        return { success: false, error: err };
      }
      const placeholder: V2ComposerTask = {
        task_id: response.data.task_id,
        user_id: '',
        kind: 'regenerate',
        template_name: '',
        template_id: body.template_id,
        status: response.data.status,
        template_role: 'single',
        original_filename: '',
        generate_result: null,
        regenerate_result: null,
        error: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      get().upsertTask(placeholder);
      return { success: true, data: { taskId: response.data.task_id } };
    },

    cancelTask: async (taskId) => {
      const response = await cancelComposerTask(taskId);
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

      const response = await dismissComposerTask(taskId);
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

    setAutoSelectOnCompleteTaskId: (taskId) => {
      set({ autoSelectOnCompleteTaskId: taskId });
    },

    clearError: () => set({ error: null }),
  }),
);

// ─── Selectors ────────────────────────────────────────────────────────

export function selectActiveComposerTasks(
  state: StudioV2ComposerTasksState,
): V2ComposerTask[] {
  return Object.values(state.tasks)
    .filter((t) => ACTIVE_COMPOSER_TASK_STATES.has(t.status))
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export function selectTerminalComposerTasks(
  state: StudioV2ComposerTasksState,
): V2ComposerTask[] {
  return Object.values(state.tasks)
    .filter((t) => !ACTIVE_COMPOSER_TASK_STATES.has(t.status))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export function selectAllVisibleComposerTasks(
  state: StudioV2ComposerTasksState,
): V2ComposerTask[] {
  return Object.values(state.tasks).sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  );
}

export function selectComposerTaskById(
  state: StudioV2ComposerTasksState,
  taskId: string | null | undefined,
): V2ComposerTask | undefined {
  if (!taskId) return undefined;
  return state.tasks[taskId];
}
