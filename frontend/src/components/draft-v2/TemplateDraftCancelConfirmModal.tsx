import { useState, type ReactElement } from 'react';

import { Modal } from '@/components/common';
import { useStudioStore } from '@/stores/useStudioStore';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import { useToastStore } from '@/stores/useToastStore';

/**
 * Confirmation modal for cancelling an in-progress v2 template draft.
 * Mirrors the legacy CancelConfirmModal UX (amber warning icon, Yes/No CTAs).
 */
export const TemplateDraftCancelConfirmModal = (): ReactElement | null => {
  const taskId = useTemplateDraftStore((s) => s.cancelConfirmTaskId);
  const task = useTemplateDraftStore((s) => (taskId ? s.tasks[taskId] : null));
  const studioTemplates = useStudioStore((s) => s.templates);
  const closeCancelConfirm = useTemplateDraftStore((s) => s.closeCancelConfirm);
  const cancelTask = useTemplateDraftStore((s) => s.cancelTask);
  const addToast = useToastStore((s) => s.addToast);
  const [isCancelling, setIsCancelling] = useState(false);

  if (!task) return null;

  const liveTemplateName =
    studioTemplates.find((t) => t.id === task.template_id)?.name ??
    task.template_name ??
    task.template_id;

  const handleConfirm = async (): Promise<void> => {
    setIsCancelling(true);
    const result = await cancelTask(task.task_id);
    setIsCancelling(false);
    if (result.success) {
      addToast('Generation cancelled', 'info');
    } else {
      addToast(result.error ?? 'Failed to cancel generation', 'error');
    }
  };

  return (
    <Modal isOpen onClose={closeCancelConfirm} size="lg" showCloseButton={false}>
      <div className="bg-surface px-4 pb-4 pt-5 sm:p-6 sm:pb-4">
        <div className="sm:flex sm:items-start">
          <div className="mx-auto flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-yellow-100 sm:mx-0 sm:h-10 sm:w-10">
            <svg
              className="h-6 w-6 text-yellow-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <div className="mt-3 flex-1 text-center sm:ml-4 sm:mt-0 sm:text-left">
            <h3 className="text-lg font-semibold leading-6 text-text">
              Cancel draft?
            </h3>
            <div className="mt-2">
              <p className="text-sm text-muted">
                Are you sure you want to cancel this draft?
              </p>
              <p className="mt-2 text-sm font-medium text-text-secondary">
                {liveTemplateName}
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-surface-muted px-4 py-3 sm:flex sm:flex-row-reverse sm:gap-2 sm:px-6">
        <button
          type="button"
          onClick={() => void handleConfirm()}
          disabled={isCancelling}
          className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-yellow-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-yellow-700 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
        >
          {isCancelling ? 'Cancelling…' : 'Yes, cancel'}
        </button>
        <button
          type="button"
          onClick={closeCancelConfirm}
          disabled={isCancelling}
          className="mt-3 inline-flex w-full justify-center rounded-md border border-border bg-surface px-4 py-2 text-sm font-semibold text-text-secondary shadow-sm transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50 sm:mt-0 sm:w-auto"
        >
          No, keep going
        </button>
      </div>
    </Modal>
  );
};

export default TemplateDraftCancelConfirmModal;
