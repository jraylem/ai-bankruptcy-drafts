import { useState } from 'react';
import NiceModal, { useModal } from '@ebay/nice-modal-react';
import { FiShield } from 'react-icons/fi';
import { Modal } from '@/components/common';
import { PERMISSION_OPTIONS, permissionLabels } from '../../settings.constants';
import { SettingsActionIconButton } from './SettingsActionIconButton';

export const PermissionSummary = ({ permissions }: { permissions: string[] }) => {
  if (permissions.length === 0) {
    return (
      <span className="inline-flex rounded-lg bg-surface px-2 py-1 text-xs font-medium text-muted">
        Role defaults
      </span>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {permissions.map((permission) => (
        <span
          key={permission}
          className="rounded-lg bg-surface px-2 py-1 text-[11px] font-medium text-text-secondary"
        >
          {permissionLabels[permission] ?? permission}
        </span>
      ))}
    </div>
  );
};

const PermissionsModal = NiceModal.create(
  ({
    email,
    onSave,
    permissions,
  }: {
    email: string;
    onSave: (permissions: string[]) => void;
    permissions: string[];
  }) => {
    const modal = useModal();
    const [draftPermissions, setDraftPermissions] = useState(permissions);
    const togglePermission = (permission: string) => {
      setDraftPermissions((current) =>
        current.includes(permission)
          ? current.filter((item) => item !== permission)
          : [...current, permission]
      );
    };

    return (
      <Modal isOpen={modal.visible} onClose={modal.hide} size="md" showCloseButton>
        <div className="px-6 py-6">
          <header className="pr-8">
            <h2 className="font-poppins text-xl font-semibold text-text">Edit Permissions</h2>
            <p className="mt-1 truncate text-sm text-muted">{email}</p>
          </header>

          <div className="mt-5 rounded-xl border border-border bg-page p-3">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-muted">
              Current permissions
            </p>
            <PermissionSummary permissions={permissions} />
          </div>

          <div className="mt-5 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {PERMISSION_OPTIONS.map((option) => {
              const checked = draftPermissions.includes(option.value);
              return (
                <label
                  key={option.value}
                  className="flex cursor-pointer items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium text-text-secondary transition hover:bg-surface-muted"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => togglePermission(option.value)}
                    className="h-4 w-4 rounded border-border text-app-accent focus:ring-app-accent"
                  />
                  {option.label}
                </label>
              );
            })}
          </div>

          <div className="mt-6 flex justify-end gap-2 border-t border-border pt-4">
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
                onSave(draftPermissions);
                modal.hide();
              }}
              className="inline-flex h-10 items-center justify-center rounded-lg bg-app-accent px-4 text-sm font-semibold text-white transition hover:bg-app-accent/90"
            >
              Save
            </button>
          </div>
        </div>
      </Modal>
    );
  }
);

export const PermissionsAction = ({
  disabled = false,
  email,
  onSave,
  permissions,
}: {
  disabled?: boolean;
  email: string;
  onSave?: (permissions: string[]) => void;
  permissions: string[];
}) => (
  <SettingsActionIconButton
    aria-label={`Edit permissions for ${email}`}
    onClick={() => {
      if (!onSave) return;
      void NiceModal.show(PermissionsModal, { email, onSave, permissions });
    }}
    disabled={disabled}
    className="hover:bg-app-accent-soft hover:text-app-accent-text disabled:cursor-not-allowed"
    label="Edit permissions"
  >
    <FiShield className="h-4 w-4" />
  </SettingsActionIconButton>
);
