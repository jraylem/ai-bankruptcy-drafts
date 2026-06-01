import type { ReactElement, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { useStudioStore } from '@/stores/useStudioStore';
import {
  useTemplateDraftStore,
  type V2TaskStatus,
  type V2TemplateDraftTask,
} from '@/stores/useTemplateDraftStore';

/**
 * V2 status strip — live pills driven by `useTemplateDraftStore.tasks`.
 *
 * Global across cases: parallel drafts started while viewing different cases
 * all show in one strip. Each pill carries a small case chip so the user can
 * see at a glance which case the draft belongs to. Clicking `Open` on a READY
 * pill navigates to that case (if needed) before opening the document viewer.
 *
 * Statuses `CANCELLED` are filtered out; everything else maps to a pill.
 */

interface StatusStyle {
  color: string;
  label: string;
  active: boolean;
  pulse?: boolean;
}

const STATUS_STYLES: Record<Exclude<V2TaskStatus, 'CANCELLED'>, StatusStyle> = {
  QUEUED: { color: 'text-subtle', label: 'QUEUED', active: false },
  PENDING: { color: 'text-subtle', label: 'Pending', active: false },
  CHECKING_EXISTING: { color: 'text-blue-500', label: 'READING CASE', active: true },
  EXISTING_FOUND: { color: 'text-app-accent-text', label: 'EXISTS', active: false },
  DRAFTING: { color: 'text-violet-500', label: 'DRAFTING', active: true },
  AWAITING_INPUT: { color: 'text-amber-500', label: 'NEEDS INPUT', active: false, pulse: true },
  COMPLETED: { color: 'text-emerald-500', label: 'READY', active: false },
  FAILED: { color: 'text-red-500', label: 'FAILED', active: false },
};

const StatusIndicator = ({ style }: { style: StatusStyle }): ReactElement => {
  if (style.active) {
    return (
      <span
        aria-hidden="true"
        className={`relative inline-flex h-3 w-3 shrink-0 items-center justify-center ${style.color}`}
      >
        <svg
          className="h-3 w-3 motion-safe:animate-spin motion-reduce:hidden"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
        >
          <circle cx="8" cy="8" r="6" strokeWidth="2" className="opacity-25" />
          <path d="M14 8a6 6 0 0 1-6 6" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span className="hidden h-2 w-2 rounded-full bg-current motion-reduce:inline-block" />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-2 w-2 shrink-0 rounded-full bg-current ${style.color} ${
        style.pulse ? 'motion-safe:animate-pulse' : ''
      }`}
    />
  );
};

const CloseIcon = (): ReactElement => (
  <svg
    className="h-3.5 w-3.5"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const OpenIcon = (): ReactElement => (
  <svg
    className="h-3.5 w-3.5"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M14 3h7v7M21 3l-9 9M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5" />
  </svg>
);

const TrailingActions = ({ task }: { task: V2TemplateDraftTask }): ReactNode => {
  const dismissTask = useTemplateDraftStore((s) => s.dismissTask);
  const openInputModal = useTemplateDraftStore((s) => s.openInputModal);
  const openExistingModal = useTemplateDraftStore((s) => s.openExistingModal);
  const openDocumentViewer = useTemplateDraftStore((s) => s.openDocumentViewer);
  const openCancelConfirm = useTemplateDraftStore((s) => s.openCancelConfirm);
  const selectedCaseId = useStudioStore((s) => s.selectedCaseId);
  const selectCase = useStudioStore((s) => s.selectCase);
  const navigate = useNavigate();

  const openTaskCaseThenViewer = (): void => {
    // If the user is on a different case (or no case at all), hop over to the
    // task's case first so the viewer + autosave have the right workspace
    // context. Otherwise just open the viewer in place.
    if (task.case_id && task.case_id !== selectedCaseId) {
      selectCase(task.case_id);
      navigate(`/case/${encodeURIComponent(task.case_id)}`);
    }
    openDocumentViewer(task.task_id);
  };

  const ghostClass =
    'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-subtle transition-colors hover:bg-surface-muted hover:text-text-secondary';

  switch (task.status) {
    case 'QUEUED':
    case 'PENDING':
    case 'CHECKING_EXISTING':
    case 'DRAFTING':
      return (
        <button
          type="button"
          aria-label="Cancel draft"
          title="Cancel draft"
          onClick={(e) => {
            e.stopPropagation();
            openCancelConfirm(task.task_id);
          }}
          className={ghostClass}
        >
          <CloseIcon />
        </button>
      );
    case 'AWAITING_INPUT':
      return (
        <>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              openInputModal(task.task_id);
            }}
            className="inline-flex h-6 shrink-0 items-center rounded-full bg-amber-500 px-2.5 text-[11px] font-semibold text-white shadow-sm transition hover:bg-amber-600"
          >
            Input
          </button>
          <button
            type="button"
            aria-label="Cancel draft"
            title="Cancel draft"
            onClick={(e) => {
              e.stopPropagation();
              openCancelConfirm(task.task_id);
            }}
            className={ghostClass}
          >
            <CloseIcon />
          </button>
        </>
      );
    case 'EXISTING_FOUND':
      return (
        <>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              openExistingModal(task.task_id);
            }}
            className="inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-app-accent-soft px-2.5 text-[11px] font-semibold text-app-accent-text transition hover:bg-app-accent-soft/80"
          >
            Choose
          </button>
          <button
            type="button"
            aria-label="Cancel draft"
            title="Cancel draft"
            onClick={(e) => {
              e.stopPropagation();
              openCancelConfirm(task.task_id);
            }}
            className={ghostClass}
          >
            <CloseIcon />
          </button>
        </>
      );
    case 'COMPLETED':
      return (
        <>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              openTaskCaseThenViewer();
            }}
            className="inline-flex h-6 shrink-0 items-center gap-1 rounded-full bg-emerald-600 px-2.5 text-[11px] font-semibold text-white shadow-sm transition hover:bg-emerald-700"
          >
            <OpenIcon />
            Open
          </button>
          <button
            type="button"
            aria-label="Dismiss completed draft"
            title="Dismiss"
            onClick={(e) => {
              e.stopPropagation();
              void dismissTask(task.task_id);
            }}
            className={ghostClass}
          >
            <CloseIcon />
          </button>
        </>
      );
    case 'FAILED':
      return (
        <button
          type="button"
          aria-label="Dismiss failed draft"
          title="Dismiss"
          onClick={(e) => {
            e.stopPropagation();
            void dismissTask(task.task_id);
          }}
          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600 transition-colors hover:bg-red-100"
        >
          <CloseIcon />
        </button>
      );
  }
  return null;
};

const DisplayTitle = ({ task }: { task: V2TemplateDraftTask }): string => {
  // Prefer the live template name from useStudioStore; fall back to the snapshot.
  const templates = useStudioStore((s) => s.templates);
  const live = templates.find((t) => t.id === task.template_id);
  return live?.name || task.template_name || task.template_id;
};

interface CaseChipInfo {
  /** What we render inline on the pill — short, friendly, mixed-case. */
  label: string;
  /** What we show on the tooltip — full context. */
  tooltip: string;
}

const useCaseChipInfo = (caseId: string): CaseChipInfo => {
  const cases = useStudioStore((s) => s.cases);
  const c = cases.find((x) => x.id === caseId);
  if (!c) return { label: caseId, tooltip: `Case ${caseId}` };
  const number = c.case_number || c.case_number_original || c.id;
  const name = c.case_name || '';
  // Prefer the human name when present; fall back to the number alone.
  if (name) {
    return { label: name, tooltip: `${name} · ${number}` };
  }
  return { label: number, tooltip: `Case ${number}` };
};

const DismissingSpinner = (): ReactElement => (
  <span
    aria-hidden="true"
    className="inline-flex h-6 w-6 shrink-0 items-center justify-center text-subtle"
  >
    <svg
      className="h-3.5 w-3.5 motion-safe:animate-spin"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
    >
      <circle cx="8" cy="8" r="6" strokeWidth="2" className="opacity-25" />
      <path d="M14 8a6 6 0 0 1-6 6" strokeWidth="2" strokeLinecap="round" />
    </svg>
  </span>
);

const DraftStatusPill = ({ task }: { task: V2TemplateDraftTask }): ReactElement => {
  const style = STATUS_STYLES[task.status as Exclude<V2TaskStatus, 'CANCELLED'>];
  const focusedTaskId = useTemplateDraftStore((s) => s.focusedTaskId);
  const isDismissing = useTemplateDraftStore((s) => s.dismissingTaskIds.has(task.task_id));
  const title = DisplayTitle({ task });
  const caseChip = useCaseChipInfo(task.case_id);
  const message = task.error ?? '';
  const isFocused = focusedTaskId === task.task_id;
  const focusClass = isFocused ? 'ring-2 ring-app-accent-soft motion-safe:animate-pulse' : '';
  const baseClass =
    'group inline-flex h-11 shrink-0 items-center gap-2.5 rounded-full border border-border/60 bg-surface px-3.5 transition-colors min-w-[260px] max-w-[360px]';
  const hoverClass = task.status === 'FAILED' ? '' : 'hover:bg-surface-muted';
  // Dismissing pills go grayscale + lose hover affordance and trailing actions
  // so the user gets immediate feedback while the DELETE round-trip is pending.
  const dismissingClass = isDismissing
    ? 'grayscale opacity-60 pointer-events-none'
    : '';
  const tooltip = isDismissing
    ? 'Removing…'
    : `${title} · ${caseChip.tooltip}${message ? ` · ${message}` : ''}`;

  return (
    <div
      title={tooltip}
      className={`${baseClass} ${isDismissing ? '' : hoverClass} ${focusClass} ${dismissingClass}`}
      aria-busy={isDismissing || undefined}
    >
      <StatusIndicator style={style} />
      <div className="flex min-w-0 flex-1 flex-col leading-tight">
        <span className="truncate text-sm font-medium text-text-secondary">
          {title}
        </span>
        <span className="truncate text-[11px] text-subtle">
          {caseChip.label}
        </span>
      </div>
      <span
        className={`hidden shrink-0 text-[11px] font-semibold uppercase tracking-wider sm:inline ${
          isDismissing ? 'text-subtle' : style.color
        }`}
      >
        {isDismissing ? 'Removing…' : style.label}
      </span>
      {isDismissing ? <DismissingSpinner /> : <TrailingActions task={task} />}
    </div>
  );
};

export const TemplateDraftStatusStrip = (): ReactElement => {
  const tasks = useTemplateDraftStore((s) => s.tasks);

  // Global — every non-cancelled task the user has, across all cases. Parallel
  // drafting is the whole point: the user can switch cases freely and watch
  // every pill progress in one place. The pill itself carries case context.
  const visible = Object.values(tasks)
    .filter((t) => t.status !== 'CANCELLED')
    .sort((a, b) => (b.created_at > a.created_at ? 1 : -1));

  const hasDrafts = visible.length > 0;

  return (
    <div
      className="relative z-10 border-b border-border bg-surface/95 px-4 py-2 backdrop-blur-[1px]"
      role="region"
      aria-label="Drafts in flight"
    >
      {hasDrafts ? (
        <div
          className="min-w-0 overflow-x-auto overflow-y-hidden pb-1"
          style={{ scrollbarWidth: 'thin' }}
        >
          <div
            className="flex w-max min-w-full items-center gap-2 pr-2"
            aria-live="polite"
          >
            {visible.map((t) => (
              <DraftStatusPill key={t.task_id} task={t} />
            ))}
          </div>
        </div>
      ) : (
        <div className="flex min-h-[44px] items-center justify-center">
          <h1 className="text-lg font-semibold bg-linear-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
             Jurisgentic
          </h1>
        </div>
      )}
    </div>
  );
};

export default TemplateDraftStatusStrip;
