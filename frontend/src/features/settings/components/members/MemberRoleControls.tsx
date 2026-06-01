import { SelectDropdown } from '@/components/common';
import { useUpdateSettingsMemberRole } from '../../hooks';
import { ROLE_OPTIONS } from '../../settings.constants';
import type { SettingsMemberRole } from '../../types';

export const RoleSelect = ({
  role,
  userId,
}: {
  role: string;
  userId: string;
}) => {
  const updateRoleMutation = useUpdateSettingsMemberRole();

  if (role === 'firm_owner') {
    return (
      <span className="inline-flex h-8 items-center rounded-lg bg-surface-muted px-2.5 text-xs font-semibold text-muted">
        Firm owner
      </span>
    );
  }

  return (
    <SelectDropdown
      value={role}
      onChange={(nextRole) =>
        updateRoleMutation.mutate({ userId, role: nextRole as SettingsMemberRole })
      }
      options={ROLE_OPTIONS}
      size="sm"
      className="w-24"
      buttonClassName="flex h-8 w-full items-center justify-between rounded-lg border border-border bg-surface px-2.5 text-xs font-semibold text-text-secondary outline-none transition hover:border-app-accent/40 focus:ring-2 focus:ring-app-accent-soft"
    />
  );
};

export const RoleLabel = ({ role }: { role: string }) => {
  const label =
    role === 'superadmin'
      ? 'Superadmin'
      : role === 'firm_owner'
        ? 'Firm owner'
        : role === 'admin'
          ? 'Admin'
          : 'Member';
  return (
    <span className="inline-flex h-8 items-center rounded-lg bg-surface-muted px-2.5 text-xs font-semibold text-muted">
      {label}
    </span>
  );
};
