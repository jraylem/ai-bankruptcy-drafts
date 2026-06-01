import { useMemo, useState } from 'react';

import { FiChevronDown, FiChevronUp } from 'react-icons/fi';

import ComposerTaskCard from '@/components/studio-v2/ComposerTaskCard';
import type { V2ComposerTask } from '@/services/studioV2ComposerAsync.service';
import { ACTIVE_COMPOSER_TASK_STATES } from '@/services/studioV2ComposerAsync.service';
import { useStudioV2ComposerTasksStore } from '@/stores/useStudioV2ComposerTasksStore';

const VISIBLE_CAP = 3;

interface ComposerTasksRailSectionProps {
  onTaskClick?: (task: V2ComposerTask) => void;
}

/**
 * Sticky "In Progress" section inside `TemplatesRail`. Shows ONLY
 * actively-running composer tasks (QUEUED / PENDING / RUNNING).
 *
 * Terminal tasks (COMPLETED / FAILED / CANCELLED) live elsewhere:
 *   - COMPLETED → auto-dismissed by the store after the success
 *     toast + auto-select have done their job. The new template is
 *     already visible in the templates list below the section.
 *   - CANCELLED → auto-dismissed.
 *   - FAILED → stays visible briefly via an inline failure pill
 *     (rendered separately below the active list) so the user can
 *     read the error without "In Progress" being a lie.
 *
 * Stacking: vertical (rail is 280px — horizontal would crush each
 * card), newest-on-top, soft cap at 3 + "Show N more" expander.
 *
 * Sticky behavior: `position: sticky; top: 0` within the rail's
 * scroll container keeps the section pinned while the user scrolls
 * a long template list — Slack's "Unreads" / Linear's "Active
 * issues" pin pattern.
 *
 * IMPORTANT: select the raw `tasks` dict (stable ref unless tasks
 * change) and derive the sorted array via `useMemo` — selecting a
 * derived array straight out of Zustand returns a fresh reference
 * on every render and triggers an infinite re-render loop
 * (Object.is selector equality in Zustand 5).
 */
export default function ComposerTasksRailSection({
  onTaskClick,
}: ComposerTasksRailSectionProps) {
  const tasksMap = useStudioV2ComposerTasksStore((s) => s.tasks);
  const dismissingTaskIds = useStudioV2ComposerTasksStore(
    (s) => s.dismissingTaskIds,
  );
  const dismissTask = useStudioV2ComposerTasksStore((s) => s.dismissTask);
  const cancelTask = useStudioV2ComposerTasksStore((s) => s.cancelTask);
  const [expanded, setExpanded] = useState(false);

  const activeTasks = useMemo(() => {
    return Object.values(tasksMap)
      .filter((t) => ACTIVE_COMPOSER_TASK_STATES.has(t.status))
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [tasksMap]);

  const failedTasks = useMemo(() => {
    return Object.values(tasksMap)
      .filter((t) => t.status === 'FAILED')
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [tasksMap]);

  if (activeTasks.length === 0 && failedTasks.length === 0) return null;

  const visible = expanded ? activeTasks : activeTasks.slice(0, VISIBLE_CAP);
  const hiddenCount = Math.max(0, activeTasks.length - visible.length);

  return (
    <section
      className="sticky top-0 z-10 border-b border-border bg-surface px-3 py-2"
      aria-label="Templates in progress"
      aria-live="polite"
    >
      {activeTasks.length > 0 && (
        <>
          <header className="mb-1.5 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 rounded-full bg-violet-500"
                aria-hidden
              />
              <h3 className="text-[10px] font-bold uppercase tracking-wider text-app-muted">
                In progress
              </h3>
              <span className="rounded-full bg-app-accent-soft px-1.5 py-0.5 text-[10px] font-semibold leading-none text-app-accent-text">
                {activeTasks.length}
              </span>
            </div>
            {activeTasks.length > VISIBLE_CAP && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="flex items-center gap-0.5 rounded-md p-0.5 text-[10px] text-app-muted hover:text-app-text"
                aria-label={expanded ? 'Collapse list' : 'Expand list'}
              >
                {expanded ? (
                  <>
                    <FiChevronUp className="h-3 w-3" aria-hidden /> Collapse
                  </>
                ) : (
                  <>
                    <FiChevronDown className="h-3 w-3" aria-hidden /> Show all
                  </>
                )}
              </button>
            )}
          </header>
          <div className="flex flex-col gap-1.5">
            {visible.map((task) => (
              <ComposerTaskCard
                key={task.task_id}
                task={task}
                isDismissing={dismissingTaskIds.has(task.task_id)}
                onDismiss={(id) => void dismissTask(id)}
                onCancel={(id) => void cancelTask(id)}
                onClick={onTaskClick}
              />
            ))}
            {hiddenCount > 0 && !expanded && (
              <button
                type="button"
                onClick={() => setExpanded(true)}
                className="self-stretch rounded-md border border-dashed border-border bg-surface px-2 py-1 text-[10px] font-medium text-app-muted hover:bg-surface-muted hover:text-app-text"
              >
                Show {hiddenCount} more
              </button>
            )}
          </div>
        </>
      )}

      {failedTasks.length > 0 && (
        <div className={activeTasks.length > 0 ? 'mt-2' : ''}>
          <header className="mb-1.5 flex items-center gap-1.5">
            <span
              className="h-1.5 w-1.5 rounded-full bg-rose-500"
              aria-hidden
            />
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-rose-700">
              Failed
            </h3>
            <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-rose-700">
              {failedTasks.length}
            </span>
          </header>
          <div className="flex flex-col gap-1.5">
            {failedTasks.map((task) => (
              <ComposerTaskCard
                key={task.task_id}
                task={task}
                isDismissing={dismissingTaskIds.has(task.task_id)}
                onDismiss={(id) => void dismissTask(id)}
                onCancel={(id) => void cancelTask(id)}
                onClick={onTaskClick}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
