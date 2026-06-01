import {
  FiAlertCircle,
  FiArrowRight,
  FiCheckCircle,
  FiClock,
  FiPlay,
  FiX,
} from 'react-icons/fi';

import type {
  V2DryRunStatus,
  V2DryRunTask,
} from '@/services/studioV2DryRunAsync.service';

interface DryRunTaskCardProps {
  task: V2DryRunTask;
  isDismissing?: boolean;
  onDismiss?: (taskId: string) => void;
  onCancel?: (taskId: string) => void;
  /** Fired on click for AWAITING_INPUT (open modal) + COMPLETED (open result). */
  onClick?: (task: V2DryRunTask) => void;
}

/**
 * Per-status copy. Kept short — the card is narrow and the rail
 * crowds quickly with multiple parallel dry-runs.
 */
const STATUS_LABEL: Record<V2DryRunStatus, string> = {
  QUEUED: 'Queued',
  PENDING: 'Starting…',
  RUNNING: 'Resolving fields…',
  AWAITING_INPUT: 'Your input needed',
  RESUMING: 'Finishing…',
  COMPLETED: 'Draft ready',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
};

/**
 * Per-state visual treatment.
 *
 * Distinct from `ComposerTaskCard` so paralegals read the two card
 * families as "different features" at a glance:
 *   - Composer card uses LEFT-BORDER ACCENT + violet/emerald hues
 *     and a SQUARE icon-disc (rounded-md).
 *   - Dry-run card uses a FULL ROUNDED-PILL outer shell + indigo/sky
 *     hues and a CIRCULAR icon-disc (rounded-full).
 *
 * Inspired by v1's `TemplateDraftStatusStrip` chip (rounded-full pill
 * + circular SVG spinner) — we deliberately echo the "active live
 * task" silhouette so users recognize the pattern, but the v2 dry-run
 * palette + sizing reads as a related-but-different surface.
 *
 * AWAITING_INPUT gets a stronger amber treatment because it's an
 * action-required state — paralegal needs to come back and pick.
 */
const STATE_THEME: Record<
  V2DryRunStatus,
  { ring: string; bg: string; iconBg: string; icon: string; text: string }
> = {
  QUEUED: {
    ring: 'ring-slate-200',
    bg: 'bg-slate-50',
    iconBg: 'bg-slate-200',
    icon: 'text-slate-500',
    text: 'text-slate-700',
  },
  PENDING: {
    ring: 'ring-indigo-200',
    bg: 'bg-indigo-50/60',
    iconBg: 'bg-indigo-100',
    icon: 'text-indigo-600',
    text: 'text-indigo-900',
  },
  RUNNING: {
    ring: 'ring-indigo-300',
    bg: 'bg-indigo-50',
    iconBg: 'bg-indigo-100',
    icon: 'text-indigo-600',
    text: 'text-indigo-900',
  },
  AWAITING_INPUT: {
    ring: 'ring-amber-300',
    bg: 'bg-amber-50',
    iconBg: 'bg-amber-200',
    icon: 'text-amber-700',
    text: 'text-amber-900',
  },
  RESUMING: {
    ring: 'ring-indigo-300',
    bg: 'bg-indigo-50',
    iconBg: 'bg-indigo-100',
    icon: 'text-indigo-600',
    text: 'text-indigo-900',
  },
  COMPLETED: {
    ring: 'ring-emerald-300',
    bg: 'bg-emerald-50',
    iconBg: 'bg-emerald-100',
    icon: 'text-emerald-700',
    text: 'text-emerald-900',
  },
  FAILED: {
    ring: 'ring-rose-300',
    bg: 'bg-rose-50',
    iconBg: 'bg-rose-100',
    icon: 'text-rose-700',
    text: 'text-rose-900',
  },
  CANCELLED: {
    ring: 'ring-slate-200',
    bg: 'bg-slate-50',
    iconBg: 'bg-slate-200',
    icon: 'text-slate-500',
    text: 'text-slate-600',
  },
};

/**
 * Circular spinner — the visual signature that ties dry-run cards to
 * v1's pleading chip. SVG-based so it scales cleanly inside the
 * round icon-disc.
 */
function CircularSpinner({ className }: { className?: string }) {
  return (
    <svg
      className={`h-4 w-4 animate-spin ${className ?? ''}`}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
    >
      <circle
        cx="8"
        cy="8"
        r="6"
        stroke="currentColor"
        strokeWidth="2"
        className="opacity-25"
      />
      <path
        d="M14 8a6 6 0 0 0-6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function StatusIcon({ status, themed }: { status: V2DryRunStatus; themed: string }) {
  if (
    status === 'QUEUED' ||
    status === 'PENDING' ||
    status === 'RUNNING' ||
    status === 'RESUMING'
  ) {
    return <CircularSpinner className={themed} />;
  }
  if (status === 'AWAITING_INPUT') {
    return <FiArrowRight className={`h-4 w-4 ${themed}`} aria-hidden />;
  }
  if (status === 'COMPLETED') {
    return <FiCheckCircle className={`h-4 w-4 ${themed}`} aria-hidden />;
  }
  if (status === 'FAILED') {
    return <FiAlertCircle className={`h-4 w-4 ${themed}`} aria-hidden />;
  }
  if (status === 'CANCELLED') {
    return <FiX className={`h-4 w-4 ${themed}`} aria-hidden />;
  }
  return <FiClock className={`h-4 w-4 ${themed}`} aria-hidden />;
}

export default function DryRunTaskCard({
  task,
  isDismissing,
  onDismiss,
  onCancel,
  onClick,
}: DryRunTaskCardProps) {
  const isActive =
    task.status === 'QUEUED' ||
    task.status === 'PENDING' ||
    task.status === 'RUNNING' ||
    task.status === 'RESUMING';
  const isAwaiting = task.status === 'AWAITING_INPUT';
  const isCompleted = task.status === 'COMPLETED';
  const isFailed = task.status === 'FAILED';
  const isCancelled = task.status === 'CANCELLED';
  const isClickable = isAwaiting || isCompleted;

  const theme = STATE_THEME[task.status];
  // Primary line: template name. Sublabel: case label + status copy.
  const primary = task.template_name || 'Dry-run';
  const caseTag = task.case_label || task.case_id.slice(0, 8);
  const sublabel = task.error || STATUS_LABEL[task.status];

  const handleClick = () => {
    if (isClickable && onClick) onClick(task);
  };
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isClickable || !onClick) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick(task);
    }
  };

  // Single full-card render for every state. COMPLETED chips
  // deliberately do NOT auto-collapse to a compact pill or
  // auto-dismiss — they persist until the paralegal hits × so
  // refreshing the page (or coming back later) still shows them.
  // Mirrors v1 pleading chip behavior in the chat page.
  return (
    <article
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={[
        // Outer pill — rounded-full + ring-based accent + soft bg.
        // Deliberately distinct from `ComposerTaskCard`'s left-border
        // accent + square iconBg silhouette so the two card families
        // never get visually confused.
        'group relative flex items-center gap-2.5 rounded-full px-2.5 py-1.5 ring-1 transition-colors',
        theme.ring,
        theme.bg,
        isClickable ? 'cursor-pointer hover:opacity-95' : 'cursor-default',
        isAwaiting ? 'ring-2 shadow-sm' : '',
        isDismissing ? 'pointer-events-none opacity-50' : '',
      ].join(' ')}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      aria-label={`Dry-run of ${primary} for ${caseTag} — ${sublabel}`}
    >
      {/* Leading round disc — the "circular" visual cue. */}
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${theme.iconBg}`}
      >
        {isActive || isAwaiting ? (
          <StatusIcon status={task.status} themed={theme.icon} />
        ) : isCompleted ? (
          <FiCheckCircle className={`h-4 w-4 ${theme.icon}`} aria-hidden />
        ) : (
          <FiPlay className={`h-3.5 w-3.5 ${theme.icon}`} aria-hidden />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className={`truncate text-[11.5px] font-semibold ${theme.text}`}>
          {primary}
        </p>
        <p
          className={[
            'truncate text-[10px]',
            isFailed ? 'text-rose-800' : 'text-app-muted',
          ].join(' ')}
          title={`${sublabel} · case ${caseTag}`}
        >
          <span className="font-medium">{caseTag}</span>
          <span className="mx-1 opacity-50">·</span>
          {sublabel}
        </p>
      </div>
      {/* COMPLETED chips show an always-visible "Open" affordance so
          the paralegal knows to click to view the rendered docx. */}
      {isCompleted && (
        <span
          className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700"
          aria-hidden
        >
          Open
        </span>
      )}
      {/* Trailing action button — Cancel for in-flight, Dismiss for
          terminal. Visible on hover so the chip stays clean by default
          but the paralegal can always clear it. */}
      {(isActive || isAwaiting || isCompleted || isFailed || isCancelled) && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if ((isActive || isAwaiting) && onCancel) onCancel(task.task_id);
            else if (onDismiss) onDismiss(task.task_id);
          }}
          className="shrink-0 rounded-full p-1 text-app-muted opacity-0 transition-opacity hover:bg-white/60 hover:text-app-text group-hover:opacity-100"
          aria-label={
            isActive || isAwaiting
              ? `Cancel ${primary} dry-run`
              : `Dismiss ${primary} dry-run`
          }
        >
          {isDismissing ? (
            <CircularSpinner className="text-app-muted" />
          ) : (
            <FiX className="h-3 w-3" aria-hidden />
          )}
        </button>
      )}
    </article>
  );
}
