/**
 * Zustand store for v2 template-draft tasks.
 *
 * Greenfield — no shared code with the legacy `usePleadingTaskStore`. Receives
 * every task update via SSE (`templateDraftEvents.service.ts`) and forwards
 * REST actions to `templateDraft.service.ts`. The Draft v2 page mounts this
 * store; legacy `/dashboard` does not.
 */

import { create } from 'zustand';

import {
  cancelTemplateDraft,
  dismissTemplateDraft,
  listActiveTemplateDrafts,
  regenerateTemplateDraft,
  startTemplateDraft,
  submitTemplateDraftInput,
  useExistingTemplateDraft as adoptExistingTemplateDraft,
  type StartTemplateDraftRequest,
  type V2TaskStatus,
  type V2TemplateDraftTask,
} from '@/services/templateDraft.service';
import type { BundleCompanion } from '@/types/studio/bundling';
import type { UserSelection } from '@/types/studio/resolution';

export interface BranchPickerState {
  templateId: string;
  caseId: string;
  templateName: string;
  companions: BundleCompanion[];
}

const ACTIVE_STATES: ReadonlySet<V2TaskStatus> = new Set<V2TaskStatus>([
  'QUEUED',
  'PENDING',
  'CHECKING_EXISTING',
  'EXISTING_FOUND',
  'DRAFTING',
  'AWAITING_INPUT',
]);

export interface ActionResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
  code?: string; // BE detail.code on 429 (DUPLICATE_DRAFT_IN_FLIGHT, QUEUE_FULL)
  existingTaskId?: string;
}

export interface TemplateDraftState {
  tasks: Record<string, V2TemplateDraftTask>;
  /**
   * Tombstone set: task ids that have been locally dismissed or BE-removed
   * during this session. Used to drop stale SSE events that may have been
   * emitted just before the dismiss landed on the BE. Bounded at 200 entries
   * (LRU-ish: oldest evicted on overflow) so the set can't grow unbounded.
   */
  dismissedTaskIds: Set<string>;
  /**
   * Task ids whose DELETE is currently in flight — the strip renders these
   * pills in a muted/grayscale state with a spinner instead of the × button.
   */
  dismissingTaskIds: Set<string>;
  inputModalTaskId: string | null;
  existingModalTaskId: string | null;
  viewerTaskId: string | null;
  cancelConfirmTaskId: string | null;
  branchPickerState: BranchPickerState | null;
  focusedTaskId: string | null; // pulses the matching pill briefly after dedup 429
  error: string | null;

  // SSE / hydration
  applySnapshot: (tasks: V2TemplateDraftTask[]) => void;
  upsertTask: (task: V2TemplateDraftTask) => void;
  removeTask: (taskId: string) => void;
  loadActive: (caseId?: string) => Promise<void>;

  // User actions (REST)
  startDraft: (
    req: StartTemplateDraftRequest,
    opts?: { templateNameHint?: string },
  ) => Promise<ActionResult<string>>;
  submitInput: (taskId: string, picks: Record<string, UserSelection>) => Promise<ActionResult>;
  cancelTask: (taskId: string) => Promise<ActionResult>;
  dismissTask: (taskId: string) => Promise<ActionResult>;
  useExisting: (taskId: string) => Promise<ActionResult>;
  regenerate: (taskId: string) => Promise<ActionResult>;

  // Modal control
  openInputModal: (taskId: string) => void;
  closeInputModal: () => void;
  openExistingModal: (taskId: string) => void;
  closeExistingModal: () => void;
  openDocumentViewer: (taskId: string) => void;
  closeDocumentViewer: () => void;
  openCancelConfirm: (taskId: string) => void;
  closeCancelConfirm: () => void;
  openBranchPicker: (payload: BranchPickerState) => void;
  closeBranchPicker: () => void;
  confirmBranchPicks: (picks: Record<string, string>) => Promise<ActionResult<string>>;
  focusTask: (taskId: string) => void;
  clearFocus: () => void;

  // Selectors (not setters; reads stay through useTemplateDraftStore((s)=>...))
  findActiveDuplicate: (caseId: string, templateId: string) => V2TemplateDraftTask | null;
}

export const useTemplateDraftStore = create<TemplateDraftState>((set, get) => ({
  tasks: {},
  dismissedTaskIds: new Set<string>(),
  dismissingTaskIds: new Set<string>(),
  inputModalTaskId: null,
  existingModalTaskId: null,
  viewerTaskId: null,
  cancelConfirmTaskId: null,
  branchPickerState: null,
  focusedTaskId: null,
  error: null,

  applySnapshot: (tasks) => {
    const { tasks: local, dismissedTaskIds } = get();
    const next: Record<string, V2TemplateDraftTask> = {};
    // Preserve client-side optimistic placeholders — their POST is still in flight.
    for (const [tid, t] of Object.entries(local)) {
      if (tid.startsWith('pending-')) next[tid] = t;
    }
    // For each BE task: skip if it's been dismissed this session; otherwise
    // if our local copy is NEWER (optimistic update mid-flight), keep local —
    // a stale snapshot must not wipe instant-feedback state.
    for (const beTask of tasks) {
      if (dismissedTaskIds.has(beTask.task_id)) continue;
      const localTask = local[beTask.task_id];
      if (localTask && localTask.updated_at > beTask.updated_at) {
        next[beTask.task_id] = localTask;
      } else {
        next[beTask.task_id] = beTask;
      }
    }
    set({ tasks: next, error: null });
  },

  upsertTask: (task) => {
    const { tasks, inputModalTaskId, existingModalTaskId, dismissedTaskIds } = get();

    // Drop SSE events for tasks the user has already dismissed this session —
    // these can arrive after a DELETE if events were already in flight when the
    // dismiss landed (caused pill flicker: vanish → reappear → vanish again).
    if (dismissedTaskIds.has(task.task_id)) {
      return;
    }

    const prev = tasks[task.task_id];

    // Drop stale BE updates: if our local copy is strictly newer (optimistic
    // update awaiting the POST round-trip), ignore. The next legitimately-newer
    // SSE event from the BE will overwrite us.
    if (prev && prev.updated_at > task.updated_at) {
      return;
    }

    const updates: Partial<TemplateDraftState> = {
      tasks: { ...tasks, [task.task_id]: task },
    };

    // No auto-open for either AWAITING_INPUT or EXISTING_FOUND. With parallel
    // drafting across cases, a surprise modal interrupting the user's current
    // work is unwanted. The pill's "Input" / "Choose" chip is the only entry
    // into each modal — user-triggered, opt-in.

    // Close stale modals when the task moves on.
    if (inputModalTaskId === task.task_id && task.status !== 'AWAITING_INPUT') {
      updates.inputModalTaskId = null;
    }
    if (existingModalTaskId === task.task_id && task.status !== 'EXISTING_FOUND') {
      updates.existingModalTaskId = null;
    }

    set(updates as TemplateDraftState);
  },

  removeTask: (taskId) => {
    const {
      tasks,
      inputModalTaskId,
      existingModalTaskId,
      viewerTaskId,
      cancelConfirmTaskId,
      dismissedTaskIds,
    } = get();
    const next = { ...tasks };
    delete next[taskId];
    // Tombstone the id so any stale SSE events for it that are still in flight
    // (emitted by the BE before our DELETE landed) can't re-add the pill.
    // Bounded so a long session can't grow the set without limit.
    const nextDismissed = new Set(dismissedTaskIds);
    nextDismissed.add(taskId);
    if (nextDismissed.size > 200) {
      const oldest = nextDismissed.values().next().value;
      if (oldest !== undefined) nextDismissed.delete(oldest);
    }
    set({
      tasks: next,
      dismissedTaskIds: nextDismissed,
      inputModalTaskId: inputModalTaskId === taskId ? null : inputModalTaskId,
      existingModalTaskId: existingModalTaskId === taskId ? null : existingModalTaskId,
      viewerTaskId: viewerTaskId === taskId ? null : viewerTaskId,
      cancelConfirmTaskId: cancelConfirmTaskId === taskId ? null : cancelConfirmTaskId,
    });
  },

  loadActive: async (caseId) => {
    const result = await listActiveTemplateDrafts({ caseId });
    if (result.error) {
      set({ error: result.error });
      return;
    }
    set((state) => {
      const next = { ...state.tasks };
      for (const beTask of result.data ?? []) {
        const localTask = state.tasks[beTask.task_id];
        // Preserve local optimistic updates that are newer than BE.
        if (!localTask || localTask.updated_at <= beTask.updated_at) {
          next[beTask.task_id] = beTask;
        }
      }
      return { tasks: next, error: null };
    });
  },

  startDraft: async (req, opts = {}) => {
    // FE-side dedup pre-check — skip the round-trip if we already see one.
    const existing = get().findActiveDuplicate(req.case_id, req.template_id);
    if (existing) {
      get().focusTask(existing.task_id);
      return {
        success: false,
        error: 'A draft for this template and case is already in progress.',
        code: 'DUPLICATE_DRAFT_IN_FLIGHT',
        existingTaskId: existing.task_id,
      };
    }

    // Optimistic placeholder so the strip pill appears the moment the user
    // clicks Generate — replaced atomically when the POST returns.
    const placeholderId = `pending-${typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`}`;
    const now = new Date().toISOString();
    const placeholder: V2TemplateDraftTask = {
      task_id: placeholderId,
      user_id: '',
      case_id: req.case_id,
      template_id: req.template_id,
      template_name: opts.templateNameHint ?? '',
      status: 'PENDING',
      bundle_picks: req.bundle_picks ?? null,
      resolved_values: null,
      pending_inputs: null,
      log_id: null,
      existing_log_id: null,
      result: null,
      error: null,
      created_at: now,
      updated_at: now,
    };
    set((state) => ({ tasks: { ...state.tasks, [placeholderId]: placeholder } }));

    const result = await startTemplateDraft(req);

    // Drop the placeholder regardless of outcome.
    set((state) => {
      const next = { ...state.tasks };
      delete next[placeholderId];
      return { tasks: next };
    });

    if (result.data) {
      get().upsertTask(result.data.task);
      return { success: true, data: result.data.task.task_id };
    }

    // Try to surface BE 429 codes from FastAPI detail envelopes.
    const errMsg = result.error ?? 'Failed to start draft';
    const detail = (result as { detail?: unknown }).detail as
      | { code?: string; existing_task_id?: string; message?: string }
      | undefined;
    if (detail?.code === 'DUPLICATE_DRAFT_IN_FLIGHT' && detail.existing_task_id) {
      get().focusTask(detail.existing_task_id);
      return {
        success: false,
        error: detail.message ?? errMsg,
        code: detail.code,
        existingTaskId: detail.existing_task_id,
      };
    }
    return { success: false, error: errMsg };
  },

  submitInput: async (taskId, picks) => {
    // Optimistic: close the input modal + flip the pill to PENDING right away
    // so the user gets instant feedback. The worker will transition through
    // DRAFTING → COMPLETED / AWAITING_INPUT / FAILED via SSE.
    const existing = get().tasks[taskId];
    if (existing) {
      set((state) => ({
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...existing,
            status: 'PENDING',
            pending_inputs: null,
            error: null,
            updated_at: new Date().toISOString(),
          },
        },
        inputModalTaskId: state.inputModalTaskId === taskId ? null : state.inputModalTaskId,
      }));
    } else {
      set({ inputModalTaskId: null });
    }

    const result = await submitTemplateDraftInput(taskId, picks);
    if (result.data) {
      get().upsertTask(result.data);
      return { success: true };
    }
    return { success: false, error: result.error ?? 'Failed to submit input' };
  },

  cancelTask: async (taskId) => {
    const result = await cancelTemplateDraft(taskId);
    if (result.data) {
      get().upsertTask(result.data);
      set({ cancelConfirmTaskId: null });
      return { success: true };
    }
    return { success: false, error: result.error ?? 'Failed to cancel task' };
  },

  dismissTask: async (taskId) => {
    // Mark the pill as dismissing so the strip can render it grayscale + spinner
    // immediately, without waiting for the DELETE round-trip.
    set((state) => {
      const next = new Set(state.dismissingTaskIds);
      next.add(taskId);
      return { dismissingTaskIds: next };
    });
    const result = await dismissTemplateDraft(taskId);
    if (result.data) {
      get().removeTask(taskId);
      // removeTask doesn't touch dismissingTaskIds; drop the id here so it doesn't
      // leak across the same task_id reused later (unlikely with UUIDs, but cheap).
      set((state) => {
        if (!state.dismissingTaskIds.has(taskId)) return state;
        const next = new Set(state.dismissingTaskIds);
        next.delete(taskId);
        return { dismissingTaskIds: next };
      });
      return { success: true };
    }
    // Failure path — un-grayscale the pill so the user can retry.
    set((state) => {
      if (!state.dismissingTaskIds.has(taskId)) return state;
      const next = new Set(state.dismissingTaskIds);
      next.delete(taskId);
      return { dismissingTaskIds: next };
    });
    return { success: false, error: result.error ?? 'Failed to dismiss task' };
  },

  useExisting: async (taskId) => {
    // Optimistic: close the EXISTING modal + flip task to COMPLETED with the
    // existing log id pre-set, so the viewer can open instantly and fetch the
    // download envelope without waiting for the POST. updated_at is bumped so
    // a racing snapshot can't downgrade us back to EXISTING_FOUND.
    const existing = get().tasks[taskId];
    set((state) => ({
      tasks:
        existing && existing.existing_log_id
          ? {
              ...state.tasks,
              [taskId]: {
                ...existing,
                status: 'COMPLETED',
                log_id: existing.existing_log_id,
                updated_at: new Date().toISOString(),
              },
            }
          : state.tasks,
      existingModalTaskId: state.existingModalTaskId === taskId ? null : state.existingModalTaskId,
    }));
    const result = await adoptExistingTemplateDraft(taskId);
    if (result.data) {
      get().upsertTask(result.data);
      return { success: true };
    }
    return { success: false, error: result.error ?? 'Failed to adopt existing document' };
  },

  regenerate: async (taskId) => {
    // Optimistic: flip the task to PENDING locally + close the EXISTING modal
    // immediately so the user gets instant feedback while the POST is in flight.
    // updated_at is bumped so a racing snapshot can't downgrade us.
    const existing = get().tasks[taskId];
    if (existing) {
      set((state) => ({
        tasks: {
          ...state.tasks,
          [taskId]: {
            ...existing,
            status: 'PENDING',
            result: null,
            error: null,
            log_id: null,
            existing_log_id: null,
            resolved_values: null,
            pending_inputs: null,
            updated_at: new Date().toISOString(),
          },
        },
        existingModalTaskId: state.existingModalTaskId === taskId ? null : state.existingModalTaskId,
      }));
    }

    const result = await regenerateTemplateDraft(taskId);
    if (result.data) {
      get().upsertTask(result.data);
      return { success: true };
    }
    return { success: false, error: result.error ?? 'Failed to regenerate' };
  },

  openInputModal: (taskId) => set({ inputModalTaskId: taskId }),
  closeInputModal: () => set({ inputModalTaskId: null }),
  openExistingModal: (taskId) => set({ existingModalTaskId: taskId }),
  closeExistingModal: () => set({ existingModalTaskId: null }),
  openDocumentViewer: (taskId) => set({ viewerTaskId: taskId }),
  closeDocumentViewer: () => set({ viewerTaskId: null }),
  openCancelConfirm: (taskId) => set({ cancelConfirmTaskId: taskId }),
  closeCancelConfirm: () => set({ cancelConfirmTaskId: null }),

  openBranchPicker: (payload) => set({ branchPickerState: payload }),
  closeBranchPicker: () => set({ branchPickerState: null }),
  confirmBranchPicks: async (picks) => {
    const current = get().branchPickerState;
    if (!current) {
      return { success: false, error: 'No branch picker open' };
    }
    set({ branchPickerState: null });
    return get().startDraft(
      {
        template_id: current.templateId,
        case_id: current.caseId,
        bundle_picks: picks,
      },
      { templateNameHint: current.templateName },
    );
  },

  focusTask: (taskId) => {
    set({ focusedTaskId: taskId });
    setTimeout(() => {
      if (get().focusedTaskId === taskId) {
        set({ focusedTaskId: null });
      }
    }, 1800);
  },
  clearFocus: () => set({ focusedTaskId: null }),

  findActiveDuplicate: (caseId, templateId) => {
    for (const t of Object.values(get().tasks)) {
      if (
        t.case_id === caseId &&
        t.template_id === templateId &&
        ACTIVE_STATES.has(t.status)
      ) {
        return t;
      }
    }
    return null;
  },
}));

export type { V2TemplateDraftTask, V2TaskStatus };
