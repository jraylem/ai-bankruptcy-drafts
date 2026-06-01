import { useEffect, useMemo, useState, type ReactElement } from 'react';

import { Modal } from '@/components/common';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import { useToastStore } from '@/stores/useToastStore';
import type { BranchBundleCompanion } from '@/types/studio/bundling';

/**
 * Pre-flight picker for parent templates with `BranchBundleCompanion` entries.
 *
 * Mounted globally on the Draft v2 page; opens whenever the store's
 * `branchPickerState` is set. Mirrors the visual + interaction model of the
 * studio's `BranchPickerModal` but lives under `draft-v2/` (greenfield, no
 * shared module with the studio).
 */

interface IndexedBranch {
  index: number;
  companion: BranchBundleCompanion;
}

export const TemplateDraftBranchPickerModal = (): ReactElement | null => {
  const state = useTemplateDraftStore((s) => s.branchPickerState);
  const closeBranchPicker = useTemplateDraftStore((s) => s.closeBranchPicker);
  const confirmBranchPicks = useTemplateDraftStore((s) => s.confirmBranchPicks);
  const addToast = useToastStore((s) => s.addToast);

  const branches = useMemo<IndexedBranch[]>(() => {
    if (!state) return [];
    return state.companions
      .map((companion, index) => ({ companion, index }))
      .filter(
        (entry): entry is IndexedBranch => entry.companion.kind === 'branch',
      );
  }, [state]);

  const [picks, setPicks] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!state) return;
    const seeded: Record<string, string> = {};
    for (const { index, companion } of branches) {
      seeded[String(index)] = companion.options[0]?.label ?? '';
    }
    setPicks(seeded);
    setIsSubmitting(false);
  }, [state?.templateId, state?.caseId, branches]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!state) return null;

  const allPicked = branches.every(({ index }) => Boolean(picks[String(index)]));

  const handleConfirm = async (): Promise<void> => {
    if (!allPicked || isSubmitting) return;
    setIsSubmitting(true);
    addToast(`Drafting ${state.templateName}…`, 'info');
    const result = await confirmBranchPicks(picks);
    setIsSubmitting(false);
    if (!result.success) {
      if (result.code === 'DUPLICATE_DRAFT_IN_FLIGHT') {
        addToast(result.error ?? 'A draft is already running for this template.', 'warning');
        return;
      }
      addToast(result.error ?? 'Failed to start draft', 'error');
    }
  };

  return (
    <Modal isOpen onClose={closeBranchPicker} size="md" showCloseButton={false}>
      <div className="flex flex-col" role="dialog" aria-labelledby="td-branch-picker-title">
        <header className="flex items-start justify-between border-b border-border px-6 py-4">
          <div className="min-w-0">
            <h2 id="td-branch-picker-title" className="text-base font-semibold text-text-secondary">
              Pick companion documents
            </h2>
            <p className="mt-0.5 text-xs text-muted">
              {state.templateName} — choose which companion to attach for each branch question.
            </p>
          </div>
          <button
            type="button"
            onClick={closeBranchPicker}
            aria-label="Close"
            className="rounded p-1 text-subtle hover:bg-surface-muted hover:text-text-secondary"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </header>

        <div className="flex max-h-[60vh] flex-col gap-5 overflow-y-auto px-6 py-5">
          {branches.length === 0 && (
            <p className="text-sm text-muted">
              No branch companions on this template — nothing to pick.
            </p>
          )}
          {branches.map(({ index, companion }) => {
            const groupName = `td_branch_${index}`;
            const picked = picks[String(index)];
            return (
              <fieldset
                key={index}
                className="flex flex-col gap-3 rounded-lg border border-border bg-surface-muted p-4"
              >
                <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted">
                  {companion.label}
                </legend>
                <p className="text-sm font-medium text-text-secondary">
                  {companion.question}
                </p>
                <div className="flex flex-col gap-2">
                  {companion.options.map((option) => {
                    const isPicked = picked === option.label;
                    return (
                      <label
                        key={option.label}
                        className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors ${
                          isPicked
                            ? 'border-indigo-300 bg-app-accent-soft'
                            : 'border-transparent hover:bg-surface'
                        }`}
                      >
                        <input
                          type="radio"
                          name={groupName}
                          value={option.label}
                          checked={isPicked}
                          onChange={() =>
                            setPicks((prev) => ({
                              ...prev,
                              [String(index)]: option.label,
                            }))
                          }
                          className="h-4 w-4 accent-indigo-600"
                        />
                        <span className="text-sm font-medium text-text-secondary">
                          {option.label}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            );
          })}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border px-6 py-3">
          <button
            type="button"
            onClick={closeBranchPicker}
            disabled={isSubmitting}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold text-muted transition-colors hover:bg-surface-muted hover:text-text-secondary disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void handleConfirm()}
            disabled={!allPicked || isSubmitting || branches.length === 0}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? 'Starting…' : 'Generate draft'}
          </button>
        </footer>
      </div>
    </Modal>
  );
};

export default TemplateDraftBranchPickerModal;
