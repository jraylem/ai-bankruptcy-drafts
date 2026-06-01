import { useEffect, useState } from 'react';
import { FiAlertCircle, FiCheck } from 'react-icons/fi';
import { cn } from '@/utils';
import { TEMPLATE_ROLES, type TemplateConfig, type TemplateRole } from './types';

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

interface TemplateRolePickerProps {
  config: TemplateConfig;
  onChange: (patch: Partial<TemplateConfig>) => void;
  status?: SaveStatus;
  lastSavedAt?: number | null;
}

const SHORT_LABEL: Record<string, string> = {
  single: 'Standalone',
  master: 'Lead',
  part_of_packet: 'Companion',
};

export const TemplateRolePicker = ({
  config,
  onChange,
  status = 'idle',
  lastSavedAt = null,
}: TemplateRolePickerProps) => {
  const activeRole = TEMPLATE_ROLES.find((r) => r.key === config.role);
  const isSaving = status === 'saving';
  const isError = status === 'error';

  // Track which role pill the user just clicked so the spinner / check
  // only morphs the relevant pill (not the previously-selected one).
  // Resets after the save fade so subsequent renders don't keep showing
  // a check on the active pill forever.
  const [clickedRole, setClickedRole] = useState<TemplateRole | null>(null);
  useEffect(() => {
    if (status === 'idle' && clickedRole !== null) {
      setClickedRole(null);
    }
  }, [status, clickedRole]);

  const handleClick = (role: TemplateRole): void => {
    if (config.role === role) return; // no-op clicks shouldn't trigger feedback
    setClickedRole(role);
    onChange({ role });
  };

  return (
    <section className="space-y-2">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-subtle">
          Filing role
        </h3>
        <p className="mt-0.5 text-[11px] text-subtle">
          What's this template's role in a filing?
        </p>
      </div>

      <div
        aria-busy={isSaving || undefined}
        className={cn(
          'grid grid-cols-3 gap-1 rounded-lg border bg-surface-muted p-1 motion-safe:transition-colors',
          isError
            ? 'border-app-danger-text/40 motion-safe:animate-[shake_0.4s_ease-in-out_1]'
            : 'border-border',
        )}
      >
        {TEMPLATE_ROLES.map((role) => {
          const isSelected = config.role === role.key;
          const isMorphing = clickedRole === role.key && (isSaving || status === 'saved');
          // Other pills get dimmed while a save is in flight so the
          // visual weight collapses onto the morphing pill.
          const dimDuringSave = isSaving && !isMorphing;
          return (
            <button
              key={role.key}
              type="button"
              onClick={() => handleClick(role.key)}
              disabled={isSaving}
              data-saving={isMorphing && isSaving || undefined}
              className={cn(
                'inline-flex cursor-pointer items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] font-semibold motion-safe:transition-all',
                isSelected
                  ? 'bg-surface text-app-accent-text shadow-sm ring-1 ring-app-accent/30'
                  : 'text-subtle hover:bg-surface/60 hover:text-text-secondary',
                dimDuringSave && 'opacity-40',
                isSaving && 'cursor-wait',
              )}
              aria-pressed={isSelected}
            >
              {isMorphing && isSaving && (
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-app-accent/30 border-t-app-accent" />
              )}
              {isMorphing && status === 'saved' && (
                <FiCheck className="h-3 w-3 text-app-accent-text" />
              )}
              <span>{SHORT_LABEL[role.key] ?? role.label}</span>
            </button>
          );
        })}
      </div>

      <StatusLine status={status} lastSavedAt={lastSavedAt} />

      {activeRole && (
        <p className="text-[11px] leading-relaxed text-text-secondary">
          {activeRole.description}
        </p>
      )}
    </section>
  );
};

const StatusLine = ({
  status,
  lastSavedAt,
}: {
  status: SaveStatus;
  lastSavedAt: number | null;
}) => {
  // Tick once per second so "Saved 4s ago" stays current. Cheap —
  // re-renders only the status line. Idle/no-save → no ticker.
  const [, setTick] = useState(0);
  useEffect(() => {
    if (status !== 'idle' || lastSavedAt === null) return;
    const id = window.setInterval(() => setTick((t) => t + 1), 1000);
    return () => window.clearInterval(id);
  }, [status, lastSavedAt]);

  if (status === 'saving') {
    return (
      <p className="flex min-h-[1.25rem] items-center gap-1.5 text-[11px] text-text-secondary motion-safe:animate-pulse">
        <span className="h-2.5 w-2.5 animate-spin rounded-full border border-app-accent/30 border-t-app-accent" />
        Saving filing role…
      </p>
    );
  }
  if (status === 'saved') {
    return (
      <p className="flex min-h-[1.25rem] items-center gap-1.5 text-[11px] font-medium text-app-accent-text">
        <FiCheck className="h-3 w-3" />
        Saved just now
      </p>
    );
  }
  if (status === 'error') {
    return (
      <p className="flex min-h-[1.25rem] items-center gap-1.5 text-[11px] font-medium text-app-danger-text">
        <FiAlertCircle className="h-3 w-3" />
        Save failed — pick again to retry
      </p>
    );
  }
  if (lastSavedAt !== null) {
    return (
      <p className="flex min-h-[1.25rem] items-center text-[11px] text-subtle">
        Saved {formatRelative(lastSavedAt)}
      </p>
    );
  }
  // Reserve the row so the layout doesn't shift when status appears.
  return <p className="min-h-[1.25rem]" aria-hidden="true" />;
};

const formatRelative = (then: number): string => {
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return 'earlier today';
};
