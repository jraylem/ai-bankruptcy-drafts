import { useMemo, useState } from 'react';

import { FiChevronDown, FiChevronUp } from 'react-icons/fi';

import DryRunTaskCard from '@/components/studio-v2/DryRunTaskCard';
import type { V2DryRunTask } from '@/services/studioV2DryRunAsync.service';
import { ACTIVE_DRY_RUN_STATES } from '@/services/studioV2DryRunAsync.service';
import { useStudioV2DryRunTasksStore } from '@/stores/useStudioV2DryRunTasksStore';

const VISIBLE_CAP = 3;

interface DryRunTasksRailSectionProps {
  /** Fired when the paralegal clicks a card — used to open the
   * AwaitingInputModalV2 (AWAITING_INPUT) or focus the Draft tab
   * (COMPLETED). */
  onTaskClick?: (task: V2DryRunTask) => void;
}

/**
 * Sticky "Dry-runs" section inside `TemplatesRail`. Renders three
 * status families:
 *   - active in-flight (QUEUED / PENDING / RUNNING / AWAITING_INPUT
 *     / RESUMING) — chip shows live progress
 *   - terminal-success (COMPLETED) — chip persists with "Open" pill
 *     until paralegal hits × (mirrors v1 pleading chip behavior;
 *     auto-dismissing would silently lose the only handle to the
 *     rendered docx)
 *   - failed (FAILED) — separate sub-block with rose accent, error
 *     visibility per Nielsen #9
 *
 * Only CANCELLED is excluded — it auto-dismisses via the store 3s
 * after the user cancels and rendering it briefly during that window
 * adds noise.
 *
 * Sits BELOW `ComposerTasksRailSection` in the rail's sticky stack —
 * composer cards rank higher because they're the user's most recent
 * action (upload kicks off the iteration cycle).
 *
 * Scope: only mounted from `/studio-v2`'s TemplatesRail. Never rendered
 * in chat, cases page, or anywhere else. Dry-runs are diagnostic
 * tools for paralegals iterating on a template; they don't belong in
 * the global notification surface.
 *
 * IMPORTANT: select the raw `tasks` dict (stable ref unless tasks
 * change) and derive the sorted array via `useMemo` — selecting a
 * derived array straight out of Zustand returns a fresh reference
 * on every render and triggers an infinite re-render loop
 * (Object.is selector equality in Zustand 5).
 */
export default function DryRunTasksRailSection({
  onTaskClick,
}: DryRunTasksRailSectionProps) {
  const tasksMap = useStudioV2DryRunTasksStore((s) => s.tasks);
  const dismissingTaskIds = useStudioV2DryRunTasksStore(
    (s) => s.dismissingTaskIds,
  );
  const dismissTask = useStudioV2DryRunTasksStore((s) => s.dismissTask);
  const cancelTask = useStudioV2DryRunTasksStore((s) => s.cancelTask);
  const [expanded, setExpanded] = useState(false);

  // Active = anything actively progressing (running / resuming / awaiting
  // input / queued). Completed = terminal success that the paralegal
  // can click to open. Both stay in the same primary list so a fresh
  // batch of dry-runs and their finished results sit together — the
  // chip's per-state styling + the "Open" pill make the distinction
  // obvious without needing a separate sub-header. Failed gets its
  // own block so error visibility is preserved (Nielsen #9).
  //
  // CANCELLED is intentionally excluded from rendering — it
  // auto-dismisses 3s later via the store anyway and showing it
  // during that brief window adds noise.
  const visibleTasks = useMemo(() => {
    return Object.values(tasksMap)
      .filter(
        (t) => ACTIVE_DRY_RUN_STATES.has(t.status) || t.status === 'COMPLETED',
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [tasksMap]);

  const failedTasks = useMemo(() => {
    return Object.values(tasksMap)
      .filter((t) => t.status === 'FAILED')
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  }, [tasksMap]);

  if (visibleTasks.length === 0 && failedTasks.length === 0) return null;

  const visible = expanded ? visibleTasks : visibleTasks.slice(0, VISIBLE_CAP);
  const hiddenCount = Math.max(0, visibleTasks.length - visible.length);

  return (
    <section
      className="border-b border-border bg-surface px-3 py-2"
      aria-label="Dry-runs in progress"
      aria-live="polite"
    >
      {visibleTasks.length > 0 && (
        <>
          <header className="mb-1.5 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 rounded-full bg-indigo-500"
                aria-hidden
              />
              <h3 className="text-[10px] font-bold uppercase tracking-wider text-app-muted">
                Dry-runs
              </h3>
              <span className="rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-indigo-700">
                {visibleTasks.length}
              </span>
            </div>
            {visibleTasks.length > VISIBLE_CAP && (
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
              <DryRunTaskCard
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
                className="self-stretch rounded-full border border-dashed border-border bg-surface px-2 py-1 text-[10px] font-medium text-app-muted hover:bg-surface-muted hover:text-app-text"
              >
                Show {hiddenCount} more
              </button>
            )}
          </div>
        </>
      )}

      {failedTasks.length > 0 && (
        <div className={visibleTasks.length > 0 ? 'mt-2' : ''}>
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
              <DryRunTaskCard
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
