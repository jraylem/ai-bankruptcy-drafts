import { useEffect, useState, type ReactElement } from 'react';

import { AwaitingInputModal } from '@/components/studio-draft/AwaitingInputModal';
import { emptyAwaitingDraftState, type AwaitingDraftState } from '@/hooks/useDraftingPersistence';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import { useToastStore } from '@/stores/useToastStore';
import type {
  AwaitingInputResult,
  ResolvedTemplateValue,
  UserSelection,
} from '@/types/studio/resolution';

/**
 * V2 awaiting-input modal — a thin wrapper around the studio's
 * `AwaitingInputModal` so v2 inherits every pending-kind renderer (group
 * dropdowns, reco chips, multi-select, supporting docs upload, etc.) for
 * free.
 *
 * The studio modal is already fully props-driven; we just shape v2's task
 * record into an `AwaitingInputResult` and route the submit callback back
 * through `useTemplateDraftStore.submitInput`.
 */
export const TemplateDraftInputModal = (): ReactElement | null => {
  const taskId = useTemplateDraftStore((s) => s.inputModalTaskId);
  const task = useTemplateDraftStore((s) => (taskId ? s.tasks[taskId] : null));
  const closeInputModal = useTemplateDraftStore((s) => s.closeInputModal);
  const submitInput = useTemplateDraftStore((s) => s.submitInput);
  const addToast = useToastStore((s) => s.addToast);

  const [picks, setPicks] = useState<AwaitingDraftState>(emptyAwaitingDraftState);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Reset picks every time we open a different task — avoids one task's
  // half-filled answers leaking into another's modal.
  useEffect(() => {
    setPicks(emptyAwaitingDraftState());
    setIsSubmitting(false);
  }, [task?.task_id]);

  if (!task || task.status !== 'AWAITING_INPUT' || !task.pending_inputs) {
    return null;
  }

  const awaiting: AwaitingInputResult = {
    status: 'awaiting_input',
    run_id: task.task_id,
    template_id: task.template_id,
    case_id: task.case_id,
    template_spec: null,
    resolved_values: (task.resolved_values ?? []) as ResolvedTemplateValue[],
    pending_inputs: task.pending_inputs,
    bundle_picks: task.bundle_picks ?? null,
  };

  const handleSubmit = async (
    submittedPicks: Record<string, UserSelection>,
  ): Promise<void> => {
    setIsSubmitting(true);
    const result = await submitInput(task.task_id, submittedPicks);
    setIsSubmitting(false);
    if (!result.success) {
      addToast(result.error ?? 'Failed to submit input', 'error');
    }
  };

  return (
    <AwaitingInputModal
      isOpen
      awaiting={awaiting}
      picks={picks}
      onPicksChange={setPicks}
      isSubmitting={isSubmitting}
      onCancel={closeInputModal}
      onSubmit={(p) => void handleSubmit(p)}
    />
  );
};

export default TemplateDraftInputModal;
