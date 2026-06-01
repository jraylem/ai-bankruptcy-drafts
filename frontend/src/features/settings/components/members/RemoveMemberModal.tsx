import NiceModal, { useModal } from '@ebay/nice-modal-react';
import { Modal } from '@/components/common';
import { roleLabelFor } from './settings.helpers';

export const RemoveMemberModal = NiceModal.create(
  ({ email, onConfirm, role }: { email: string; onConfirm: () => void; role: string }) => {
    const modal = useModal();
    const roleLabel = roleLabelFor(role);
    const roleArticle = roleLabel === 'admin' ? 'an' : 'a';

    return (
      <Modal isOpen={modal.visible} onClose={modal.hide} size="md" showCloseButton>
        <div className="px-6 py-6">
          <header className="pr-10">
            <h2 className="font-poppins text-xl font-semibold text-app-danger-text">
              Remove {roleLabel === 'admin' ? 'Admin' : 'Member'}
            </h2>
          </header>

          <div className="mt-8">
            <h3 className="text-lg font-semibold leading-7 text-text">
              Are you sure you want to remove {email} as {roleArticle} {roleLabel}?
            </h3>
            <p className="mt-3 text-sm leading-6 text-text-secondary">
              This action will revoke their access to the firm. You can re-invite them later if
              needed.
            </p>
          </div>

          <div className="mt-8 flex justify-end gap-2 border-t border-border pt-4">
            <button
              type="button"
              onClick={modal.hide}
              className="inline-flex h-10 items-center justify-center rounded-lg border border-border px-4 text-sm font-semibold text-text-secondary transition hover:bg-surface-muted"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                onConfirm();
                modal.hide();
              }}
              className="inline-flex h-10 items-center justify-center rounded-lg bg-app-danger-text px-4 text-sm font-semibold text-white transition hover:bg-app-danger-text/90"
            >
              Remove {roleLabel === 'admin' ? 'Admin' : 'Member'}
            </button>
          </div>
        </div>
      </Modal>
    );
  }
);
