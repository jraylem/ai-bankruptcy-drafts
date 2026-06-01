import {
  FiAlertCircle,
  FiCheckCircle,
  FiRefreshCw,
  FiUploadCloud,
  FiX,
} from 'react-icons/fi';

import type {
  V2ComposerTask,
  V2ComposerTaskStatus,
} from '@/services/studioV2ComposerAsync.service';

interface ComposerTaskCardProps {
  task: V2ComposerTask;
  isDismissing?: boolean;
  onDismiss?: (taskId: string) => void;
  onCancel?: (taskId: string) => void;
  onClick?: (task: V2ComposerTask) => void;
}

const STATUS_LABEL: Record<V2ComposerTaskStatus, string> = {
  QUEUED: 'Queued…',
  PENDING: 'Starting…',
  RUNNING: 'Reading the document…',
  COMPLETED: 'Ready',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
};

/**
 * Per-state visual treatment — left-border accent + soft tinted bg
 * so the user can scan a stack and instantly clock which need their
 * attention vs which are quietly humming along.
 */
const STATE_THEME: Record<
  V2ComposerTaskStatus,
  { border: string; bg: string; icon: string; iconBg: string }
> = {
  QUEUED: {
    border: 'border-l-slate-300',
    bg: 'bg-slate-50',
    icon: 'text-slate-500',
    iconBg: 'bg-slate-200',
  },
  PENDING: {
    border: 'border-l-violet-300',
    bg: 'bg-violet-50/60',
    icon: 'text-violet-600',
    iconBg: 'bg-violet-100',
  },
  RUNNING: {
    border: 'border-l-violet-500',
    bg: 'bg-violet-50',
    icon: 'text-violet-600',
    iconBg: 'bg-violet-100',
  },
  COMPLETED: {
    border: 'border-l-emerald-500',
    bg: 'bg-emerald-50',
    icon: 'text-emerald-700',
    iconBg: 'bg-emerald-100',
  },
  FAILED: {
    border: 'border-l-rose-500',
    bg: 'bg-rose-50',
    icon: 'text-rose-700',
    iconBg: 'bg-rose-100',
  },
  CANCELLED: {
    border: 'border-l-slate-400',
    bg: 'bg-slate-50',
    icon: 'text-slate-500',
    iconBg: 'bg-slate-200',
  },
};

function StatusIcon({ status, themed }: { status: V2ComposerTaskStatus; themed: string }) {
  if (status === 'QUEUED' || status === 'PENDING' || status === 'RUNNING') {
    return (
      <span
        className={`block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current/30 border-t-current ${themed}`}
        aria-hidden
      />
    );
  }
  if (status === 'COMPLETED') {
    return <FiCheckCircle className={`h-3.5 w-3.5 ${themed}`} aria-hidden />;
  }
  if (status === 'FAILED') {
    return <FiAlertCircle className={`h-3.5 w-3.5 ${themed}`} aria-hidden />;
  }
  return <FiX className={`h-3.5 w-3.5 ${themed}`} aria-hidden />;
}

export default function ComposerTaskCard({
  task,
  isDismissing,
  onDismiss,
  onCancel,
  onClick,
}: ComposerTaskCardProps) {
  const isActive =
    task.status === 'QUEUED' || task.status === 'PENDING' || task.status === 'RUNNING';
  const isCompleted = task.status === 'COMPLETED';
  const isFailed = task.status === 'FAILED';
  const isCancelled = task.status === 'CANCELLED';

  const KindIcon = task.kind === 'regenerate' ? FiRefreshCw : FiUploadCloud;
  const theme = STATE_THEME[task.status];
  const label =
    task.template_name ||
    task.original_filename ||
    (task.kind === 'regenerate' ? 'Re-reading template' : 'Template');
  const subline = task.error || STATUS_LABEL[task.status];

  const handleClick = () => {
    if (isCompleted && onClick) onClick(task);
  };
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isCompleted || !onClick) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick(task);
    }
  };

  // Single full-card render for every state. COMPLETED chips do NOT
  // auto-collapse or auto-dismiss — they persist until the paralegal
  // hits × (mirrors v1 pleading chip + the dry-run chip pattern).
  return (
    <article
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={[
        'group relative rounded-md border-l-4 px-2.5 py-2 transition-colors',
        theme.border,
        theme.bg,
        isCompleted
          ? 'cursor-pointer hover:bg-emerald-100/60'
          : 'cursor-default',
        isDismissing ? 'pointer-events-none opacity-50' : '',
      ].join(' ')}
      role={isCompleted ? 'button' : undefined}
      tabIndex={isCompleted ? 0 : undefined}
      aria-label={`${label} — ${subline}`}
    >
      <div className="flex items-start gap-2">
        <div
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${theme.iconBg} ${theme.icon}`}
        >
          <KindIcon className="h-3.5 w-3.5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-app-text">{label}</p>
              <div className="mt-0.5 flex items-center gap-1.5">
                <StatusIcon status={task.status} themed={theme.icon} />
                <p
                  className={[
                    'truncate text-[10.5px]',
                    isFailed ? 'text-rose-800' : 'text-app-muted',
                  ].join(' ')}
                  title={subline}
                >
                  {subline}
                </p>
              </div>
            </div>
            {isCompleted && (
              <span
                className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700"
                aria-hidden
              >
                Open
              </span>
            )}
            {(isActive || isFailed || isCompleted || isCancelled) && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  if (isActive && onCancel) onCancel(task.task_id);
                  else if (onDismiss) onDismiss(task.task_id);
                }}
                className="rounded p-0.5 text-app-muted opacity-0 transition-opacity hover:bg-app-bg hover:text-app-text group-hover:opacity-100"
                aria-label={isActive ? `Cancel ${label}` : `Dismiss ${label}`}
              >
                {isDismissing ? (
                  <span
                    className="block h-3 w-3 animate-spin rounded-full border-2 border-app-muted/30 border-t-app-muted"
                    aria-hidden
                  />
                ) : (
                  <FiX className="h-3 w-3" aria-hidden />
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
