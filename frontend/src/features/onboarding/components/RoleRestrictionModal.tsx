import NiceModal, { useModal } from '@ebay/nice-modal-react';
import { FiCheck, FiX } from 'react-icons/fi';
import { Modal } from '@/components/common';

const ROLE_COLUMNS = ['Owner', 'Admin', 'Member'] as const;

const RESTRICTIONS = [
  { action: 'Manage billing', owner: true, admin: false, member: false },
  { action: 'Invite members', owner: true, admin: true, member: false },
  { action: 'Assign roles', owner: true, admin: true, member: false },
  { action: 'Use Motion Studio', owner: true, admin: true, member: true },
  { action: 'View analytics', owner: true, admin: true, member: true },
  { action: 'Approve firm templates', owner: true, admin: true, member: false },
] as const;

const permissionIcon = (allowed: boolean) =>
  allowed ? (
    <FiCheck className="mx-auto h-5 w-5 text-emerald-500" aria-label="Allowed" />
  ) : (
    <FiX className="mx-auto h-5 w-5 text-rose-500" aria-label="Restricted" />
  );

export const RoleRestrictionModal = NiceModal.create(() => {
  const modal = useModal();

  return (
    <Modal
      isOpen={modal.visible}
      onClose={modal.hide}
      size="3xl"
      showCloseButton
      closeOnBackdropClick
    >
      <div className="px-8 py-8">
        <header className="pr-10">
          <h2 className="text-3xl font-semibold tracking-normal text-text-secondary">
            Role Restriction Chart
          </h2>
        </header>

        <div className="mt-8 overflow-hidden rounded-xl border border-border">
          <div className="grid grid-cols-[1.4fr_repeat(3,1fr)] bg-surface px-6 py-4 text-sm font-semibold text-text-secondary">
            <span />
            {ROLE_COLUMNS.map((role) => (
              <span key={role} className="text-center">
                {role}
              </span>
            ))}
          </div>

          {RESTRICTIONS.map((row, index) => (
            <div
              key={row.action}
              className={`grid grid-cols-[1.4fr_repeat(3,1fr)] px-6 py-4 text-sm text-text-secondary ${
                index % 2 === 0 ? 'bg-surface-muted' : 'bg-surface'
              }`}
            >
              <span className="font-medium">{row.action}</span>
              <span>{permissionIcon(row.owner)}</span>
              <span>{permissionIcon(row.admin)}</span>
              <span>{permissionIcon(row.member)}</span>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
});

