import { useState } from 'react';
import { FiAlertTriangle } from 'react-icons/fi';
import { Modal } from '@/components/common/Modal';

interface DeleteTemplateModalProps {
  isOpen: boolean;
  templateName: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

export const DeleteTemplateModal = ({
  isOpen,
  templateName,
  onConfirm,
  onClose,
}: DeleteTemplateModalProps) => {
  const [busy, setBusy] = useState(false);

  const handleClose = () => {
    if (busy) return;
    onClose();
  };

  const handleConfirm = async () => {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      size="md"
      closeOnBackdropClick={!busy}
    >
      <div className="space-y-5 p-6">
        <header className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-app-danger-text/10 text-app-danger-text">
            <FiAlertTriangle className="h-5 w-5" />
          </span>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-text">
              Delete this template?
            </h2>
            <p className="text-sm text-text-secondary">
              "<span className="font-semibold">{templateName}</span>" will be
              removed from the studio. You can recreate it by uploading the
              same .docx again, but its wizard configuration will be lost.
            </p>
          </div>
        </header>

        <footer className="flex items-center justify-end gap-2 border-t border-border pt-4">
          <button
            type="button"
            onClick={handleClose}
            disabled={busy}
            className="cursor-pointer rounded-md border border-border bg-surface px-4 py-2 text-sm font-medium text-text-secondary hover:bg-surface-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={busy}
            className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-app-danger-text px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy && (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {busy ? 'Deleting…' : 'Delete template'}
          </button>
        </footer>
      </div>
    </Modal>
  );
};
