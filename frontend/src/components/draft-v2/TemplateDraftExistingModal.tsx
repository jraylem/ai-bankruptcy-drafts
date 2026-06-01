import { useMemo, useState, type ReactElement } from 'react';
import {
  LuCircleCheck,
  LuFileClock,
  LuFolderOpen,
  LuSparkles,
} from 'react-icons/lu';

import { Modal } from '@/components/common';
import { useStudioStore } from '@/stores/useStudioStore';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import { useToastStore } from '@/stores/useToastStore';

/**
 * Modal shown when the BE finds a prior COMPLETED log for the same
 * (user, case, template) — user picks "Use existing" or "Regenerate".
 *
 * Visual language (keep consistent if extending):
 *   - Hero icon : LuFileClock inside a `bg-app-accent-soft` circle, indigo/violet
 *                 brand tint. Communicates "prior artifact found" without
 *                 alarming the user (no warning yellows/reds — this is a
 *                 confirmation, not an error).
 *   - Case chip : LuFolderOpen + case_name + monospace case_number. Lets the
 *                 user reconcile WHICH case they're acting on before deciding.
 *   - CTAs      : Primary = "Use existing" (emerald, LuCircleCheck) — the fast,
 *                 free path. Secondary = "Regenerate" (ghost border, LuSparkles)
 *                 — costs an LLM round-trip, deliberately de-emphasized.
 *   - Metadata  : "Original draft on file" — single static line. We intentionally
 *                 avoid a second fetch for the log's created_at on v1; revisit
 *                 once the task payload carries `existing_log_created_at`.
 */
export const TemplateDraftExistingModal = (): ReactElement | null => {
  const taskId = useTemplateDraftStore((s) => s.existingModalTaskId);
  const task = useTemplateDraftStore((s) => (taskId ? s.tasks[taskId] : null));
  const closeExistingModal = useTemplateDraftStore((s) => s.closeExistingModal);
  const adoptExisting = useTemplateDraftStore((s) => s.useExisting);
  const regenerate = useTemplateDraftStore((s) => s.regenerate);
  const openDocumentViewer = useTemplateDraftStore((s) => s.openDocumentViewer);
  const addToast = useToastStore((s) => s.addToast);

  const cases = useStudioStore((s) => s.cases);
  const caseRecord = useMemo(
    () => (task ? cases.find((c) => c.id === task.case_id) ?? null : null),
    [cases, task],
  );

  const [busy, setBusy] = useState<'use' | 'regen' | null>(null);

  if (!task || task.status !== 'EXISTING_FOUND') return null;

  const handleUseExisting = async (): Promise<void> => {
    addToast('Opened existing draft.', 'success');
    openDocumentViewer(task.task_id);
    setBusy('use');
    const result = await adoptExisting(task.task_id);
    setBusy(null);
    if (!result.success) {
      addToast(result.error ?? 'Failed to use existing document', 'error');
    }
  };

  const handleRegenerate = async (): Promise<void> => {
    addToast('Regenerating…', 'info');
    setBusy('regen');
    const result = await regenerate(task.task_id);
    setBusy(null);
    if (!result.success) {
      addToast(result.error ?? 'Failed to regenerate', 'error');
    }
  };

  const templateLabel = task.template_name || task.template_id;
  const isBusy = busy !== null;

  return (
    <Modal isOpen onClose={closeExistingModal} size="md">
      <div
        className="flex flex-col"
        role="dialog"
        aria-labelledby="td-existing-title"
        aria-describedby="td-existing-subtitle"
      >
        <header className="border-b border-border px-6 py-4">
          <h2
            id="td-existing-title"
            className="text-lg font-semibold text-text-secondary"
          >
            Document already drafted
          </h2>
          <p id="td-existing-subtitle" className="mt-1 text-xs text-muted">
            A completed draft already exists for this template and case.
          </p>
        </header>

        <div className="px-6 py-6">
          <div className="flex flex-col items-center text-center">
            <span
              aria-hidden="true"
              className="grid h-14 w-14 place-items-center rounded-full bg-app-accent-soft text-app-accent-text"
            >
              <LuFileClock className="h-6 w-6" />
            </span>
            <p className="mt-3 text-sm font-semibold text-text-secondary">
              {templateLabel}
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-wider text-subtle">
              Original draft on file
            </p>
          </div>

          {caseRecord && (
            <div
              className="mt-5 flex items-start gap-3 rounded-lg border border-border bg-surface-muted px-4 py-3"
              aria-label="Case context"
            >
              <span
                aria-hidden="true"
                className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-surface text-text-secondary"
              >
                <LuFolderOpen className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text-secondary">
                  {caseRecord.case_name}
                </p>
                <p className="mt-0.5 truncate font-mono text-[11px] text-muted">
                  {caseRecord.case_number}
                </p>
              </div>
            </div>
          )}

          {!caseRecord && (
            <p className="mt-5 text-center text-[11px] text-subtle">
              Case details unavailable.
            </p>
          )}

          <p className="mt-4 text-center text-xs text-muted">
            Reuse the existing draft, or run a fresh generation. Regenerating
            keeps the prior draft in your case history.
          </p>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border px-6 py-3">
          <button
            type="button"
            onClick={() => void handleRegenerate()}
            disabled={isBusy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-semibold text-text-secondary transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            <LuSparkles className="h-3.5 w-3.5" aria-hidden="true" />
            {busy === 'regen' ? 'Starting…' : 'Regenerate'}
          </button>
          <button
            type="button"
            onClick={() => void handleUseExisting()}
            disabled={isBusy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <LuCircleCheck className="h-3.5 w-3.5" aria-hidden="true" />
            {busy === 'use' ? 'Loading…' : 'Use existing'}
          </button>
        </footer>
      </div>
    </Modal>
  );
};

export default TemplateDraftExistingModal;
