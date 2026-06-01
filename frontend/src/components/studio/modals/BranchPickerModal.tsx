import { useEffect, useMemo, useState, type ReactElement } from 'react';
import type {
  BranchBundleCompanion,
  BundleCompanion,
} from '@/types/studio/bundling';

interface BranchPickerModalProps {
  isOpen: boolean;
  title: string;
  confirmLabel: string;
  isRunning: boolean;
  bundleCompanions: BundleCompanion[];
  onClose: () => void;
  onConfirm: (picks: Record<string, string>) => void;
}

interface IndexedBranch {
  index: number;
  companion: BranchBundleCompanion;
}

/**
 * Pre-flight modal asked BEFORE a parent's dry-run / draft kicks off.
 *
 * For every `BranchBundleCompanion` on the parent, the user picks one of
 * the companion's options (e.g. "Yes" / "No"). Fixed companions don't
 * appear here — they always run. The chosen labels are returned as a
 * `Record<companionIndex, optionLabel>` map that the BE uses to schedule
 * the right child template per branch.
 *
 * Only renders when there's at least one branch companion. Studio's
 * `handleCasePickerConfirm` checks the parent's companion list and
 * skips this modal entirely when all companions are fixed.
 */
export const BranchPickerModal = ({
  isOpen,
  title,
  confirmLabel,
  isRunning,
  bundleCompanions,
  onClose,
  onConfirm,
}: BranchPickerModalProps): ReactElement | null => {
  const branches = useMemo<IndexedBranch[]>(
    () =>
      bundleCompanions
        .map((companion, index) => ({ companion, index }))
        .filter(
          (entry): entry is IndexedBranch =>
            entry.companion.kind === 'branch',
        ),
    [bundleCompanions],
  );

  const [picks, setPicks] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!isOpen) return;
    // Default each branch to its first option so the user only has to
    // override the ones they care about. Fixed companions don't appear.
    const seeded: Record<string, string> = {};
    for (const { index, companion } of branches) {
      seeded[String(index)] = companion.options[0]?.label ?? '';
    }
    setPicks(seeded);
  }, [isOpen, branches]);

  if (!isOpen) return null;

  const allPicked = branches.every(({ index }) => Boolean(picks[String(index)]));

  const handleConfirm = (): void => {
    if (!allPicked) return;
    onConfirm(picks);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-xl bg-surface shadow-2xl">
        <header className="flex items-start justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-base font-semibold text-text-secondary">
              {title}
            </h2>
            <p className="mt-0.5 text-xs text-muted">
              Pick which companion document to attach for each branch question.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-subtle hover:bg-surface-muted hover:text-text-secondary"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </header>

        <div className="flex flex-col gap-5 overflow-y-auto px-6 py-5">
          {branches.map(({ index, companion }) => {
            const groupName = `branch_${index}`;
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
            onClick={onClose}
            className="rounded-lg px-3 py-1.5 text-xs text-muted hover:bg-surface-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!allPicked || isRunning}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isRunning ? 'Running…' : confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  );
};

export default BranchPickerModal;
