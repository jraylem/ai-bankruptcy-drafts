import { useEffect, useMemo, useState } from 'react';
import { FiCheck, FiChevronRight, FiLayers, FiX } from 'react-icons/fi';
import { Modal } from '@/components/common';
import { cn } from '@/utils';
import type { BranchCompanion, BundleCompanion } from './types';

interface BranchPickerModalProps {
  isOpen: boolean;
  templateName: string;
  caseLabel?: string | null;
  companions: BundleCompanion[];
  onSubmit: (bundlePicks: Record<string, string>) => void;
  onCancel: () => void;
}

/**
 * Pre-flight branch-companion picker for the dry-run / draft flow.
 *
 * If a lead template has any `branch` companions, the paralegal MUST
 * answer each branch's question (picking one option) BEFORE the dry-run
 * pipeline kicks off — otherwise the bundling engine has no way to
 * know which child template to schedule for that branch.
 *
 * Returns a `bundle_picks: Record<companion_id, branch_option_id>` map
 * the page forwards to `dryRunTemplateV2` / `resumeDryRunV2` /
 * (future) the draft endpoint.
 *
 * `fixed` companions don't appear here — they always run.
 */
export const BranchPickerModal = ({
  isOpen,
  templateName,
  caseLabel,
  companions,
  onSubmit,
  onCancel,
}: BranchPickerModalProps) => {
  const branches = useMemo(
    () =>
      companions.filter((c): c is BranchCompanion => c.kind === 'branch'),
    [companions],
  );

  const [picks, setPicks] = useState<Record<string, string>>({});

  // Reset on every fresh open. Tracks the open-edge so prop changes
  // while open don't blow away in-progress picks.
  useEffect(() => {
    if (isOpen) {
      setPicks({});
    }
  }, [isOpen]);

  const allPicked = branches.every((b) => picks[b.id]);
  const pickedCount = branches.filter((b) => picks[b.id]).length;

  const handlePick = (companionId: string, optionId: string): void => {
    setPicks((prev) => ({ ...prev, [companionId]: optionId }));
  };

  const handleSubmit = (): void => {
    if (!allPicked) return;
    onSubmit(picks);
  };

  return (
    <Modal isOpen={isOpen} onClose={onCancel} size="2xl" showCloseButton={false}>
      <div className="flex max-h-[min(85vh,780px)] flex-col">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-app-accent-text">
              Before we render
            </p>
            <h2
              className="mt-0.5 text-lg font-semibold text-text-secondary"
              title={templateName}
            >
              Pick the companion path for this packet
            </h2>
            <p className="mt-1 text-sm text-muted">
              {pickedCount} of {branches.length} answered
              {caseLabel && (
                <>
                  {' · '}
                  <span className="font-mono text-text-secondary">
                    {caseLabel}
                  </span>
                </>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-surface-muted hover:text-text-secondary"
          >
            <FiX className="h-5 w-5" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto bg-surface-muted/30 px-6 py-5">
          <ul className="space-y-4">
            {branches.map((branch) => (
              <li
                key={branch.id}
                className="rounded-xl border border-border bg-surface p-4"
              >
                <div className="flex items-start gap-2">
                  <FiLayers className="mt-0.5 h-4 w-4 shrink-0 text-app-accent-text" />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium uppercase tracking-wider text-subtle">
                      {branch.label || 'Choose at draft time'}
                    </p>
                    <h3 className="mt-0.5 text-sm font-semibold text-text-secondary">
                      {branch.question || 'Pick one'}
                    </h3>
                  </div>
                </div>
                <div className="mt-3 space-y-1.5">
                  {branch.options.length === 0 ? (
                    <p className="rounded-md border border-dashed border-border bg-surface-muted/40 px-3 py-2 text-[11px] italic text-subtle">
                      No options configured for this branch. Open the
                      companions modal on the lead template to add answers.
                    </p>
                  ) : (
                    branch.options.map((opt) => {
                      const selected = picks[branch.id] === opt.id;
                      return (
                        <button
                          key={opt.id}
                          type="button"
                          onClick={() => handlePick(branch.id, opt.id)}
                          className={cn(
                            'flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left motion-safe:transition-colors',
                            selected
                              ? 'border-app-accent bg-app-accent-soft/40'
                              : 'border-border bg-surface hover:bg-surface-muted/60',
                          )}
                          role="radio"
                          aria-checked={selected}
                        >
                          <span
                            className={cn(
                              'inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full ring-1',
                              selected
                                ? 'bg-app-accent ring-app-accent'
                                : 'ring-border',
                            )}
                          >
                            {selected && (
                              <span className="h-1.5 w-1.5 rounded-full bg-white" />
                            )}
                          </span>
                          <span
                            className={cn(
                              'text-sm',
                              selected
                                ? 'font-semibold text-app-accent-text'
                                : 'text-text-secondary',
                            )}
                          >
                            {opt.option_label || '(unlabeled answer)'}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-surface px-6 py-4">
          <button
            type="button"
            onClick={onCancel}
            className="cursor-pointer rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-semibold text-text-secondary hover:bg-surface-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!allPicked}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold motion-safe:transition-opacity',
              allPicked
                ? 'cursor-pointer bg-app-accent text-white hover:opacity-90'
                : 'cursor-not-allowed bg-surface-muted text-subtle',
            )}
          >
            {allPicked ? (
              <>
                Continue to dry-run
                <FiChevronRight className="h-4 w-4" />
              </>
            ) : (
              <>
                <FiCheck className="h-4 w-4" />
                Answer all to continue
              </>
            )}
          </button>
        </footer>
      </div>
    </Modal>
  );
};
