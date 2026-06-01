import { useMemo } from 'react';
import NiceModal from '@ebay/nice-modal-react';
import { FiAlertCircle, FiLoader, FiRefreshCw, FiTrash2 } from 'react-icons/fi';
import { BillingCard } from '@/features/billing/components/BillingCard';
import { useAuthSession } from '@/features/auth/queries';
import {
  useRemoveSettingsMember,
  useResendSettingsInvitation,
  useRevokeSettingsInvitation,
  useSettingsInvitations,
  useSettingsMembers,
  useUpdateSettingsMemberPermissions,
} from '../../hooks';
import type { SettingsMemberRow } from '../../types';
import { AddMemberForm } from './AddMemberForm';
import { RoleLabel, RoleSelect } from './MemberRoleControls';
import { PermissionsAction } from './SettingsPermissionControls';
import { RemoveMemberModal } from './RemoveMemberModal';
import { SettingsActionIconButton } from './SettingsActionIconButton';
import {
  displayNameFor,
  formatDate,
  initialsFor,
  normalizeRole,
  roleRank,
} from './settings.helpers';

const PendingInviteLabel = () => (
  <span className="inline-flex items-center gap-1 rounded-lg bg-app-warning-soft px-2 py-1 text-xs font-semibold text-app-warning-text">
    <span className="h-1.5 w-1.5 rounded-full bg-app-warning-text" />
    Pending invite
  </span>
);

export const MembersTab = () => {
  const { user } = useAuthSession();
  const membersQuery = useSettingsMembers();
  const invitationsQuery = useSettingsInvitations();
  const resendMutation = useResendSettingsInvitation();
  const revokeMutation = useRevokeSettingsInvitation();
  const permissionsMutation = useUpdateSettingsMemberPermissions();
  const removeMemberMutation = useRemoveSettingsMember();

  const rows = useMemo<SettingsMemberRow[]>(() => {
    const memberRows: SettingsMemberRow[] = (membersQuery.data ?? []).map((member) => ({
      kind: 'member',
      id: member.id,
      email: member.email,
      isCurrentUser: member.id === user?.id,
      name: displayNameFor(member),
      role: normalizeRole(member.role),
      permissions: member.permissions ?? [],
      joined: formatDate(member.invitation_accepted_at),
    }));

    const inviteRows: SettingsMemberRow[] = (invitationsQuery.data ?? []).map((invite) => ({
      kind: 'invite',
      id: invite.id,
      email: invite.email,
      name: invite.email,
      role: normalizeRole(invite.role),
      permissions: [],
      joined: 'Not accepted yet',
      expiresAt: formatDate(invite.expires_at),
    }));

    return [...memberRows, ...inviteRows];
  }, [invitationsQuery.data, membersQuery.data, user?.id]);

  const isLoading = membersQuery.isLoading || invitationsQuery.isLoading;
  const error = membersQuery.error ?? invitationsQuery.error;
  const currentUserRank = roleRank(user?.role);
  const canManageMembers =
    normalizeRole(user?.role) === 'superadmin' ||
    normalizeRole(user?.role) === 'firm_owner' ||
    normalizeRole(user?.role) === 'admin' ||
    Boolean(user?.permissions?.includes('manage_members'));
  const canManageRow = (row: SettingsMemberRow) => {
    if (!canManageMembers) return false;
    if (row.kind === 'member' && row.id === user?.id) return false;
    return roleRank(row.role) < currentUserRank;
  };

  return (
    <div className="space-y-6">
      <AddMemberForm />

      <BillingCard>
        <div className="px-5 pb-4 pt-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="font-poppins text-lg font-semibold text-text-secondary">Members</h2>
              <p className="mt-1 text-sm text-muted">
                Firm users and outstanding invitations are managed from this list.
              </p>
            </div>
          </div>
        </div>

        {error ? (
          <div className="m-6 flex items-start gap-2 rounded-xl border border-app-danger-text/25 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            <FiAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            {error instanceof Error ? error.message : 'Unable to load members'}
          </div>
        ) : null}

        <div className="px-5 pb-5">
          <div className="overflow-x-auto rounded-2xl border border-border/70">
            <table className="min-w-full table-auto border-collapse">
              <thead className="bg-surface-muted/75">
                <tr>
                  <th className="w-[700px] px-4 py-3 text-left whitespace-nowrap">
                    <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                      User
                    </span>
                  </th>
                  <th className="w-[200px] px-5 py-3 text-left whitespace-nowrap">
                    <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                      Role
                    </span>
                  </th>
                  <th className="w-[200px] px-5 py-3 text-left whitespace-nowrap">
                    <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                      Joined / expiry
                    </span>
                  </th>
                  <th className="w-[200px] px-5 py-3 text-right whitespace-nowrap">
                    <span className="inline-flex w-full items-center justify-end whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                      Actions
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-sm text-muted" colSpan={4}>
                      Loading members...
                    </td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td className="px-4 py-8 text-center text-sm text-muted" colSpan={4}>
                      No members or pending invitations yet.
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => {
                    const canManage = canManageRow(row);
                    return (
                      <tr
                        key={`${row.kind}-${row.id}`}
                        className="border-t border-border/70 transition-colors hover:bg-activity-row-hover"
                      >
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <span className="grid h-9 w-9 place-items-center rounded-full bg-app-accent-soft text-xs font-bold text-app-accent-text">
                              {initialsFor(row.name)}
                            </span>
                            <div className="min-w-0">
                              <div className="flex min-w-0 flex-wrap items-center gap-2">
                                <p className="truncate font-semibold text-text">{row.name}</p>
                                {row.kind === 'member' && row.isCurrentUser ? (
                                  <span className="shrink-0 text-xs font-semibold text-muted">
                                    (you)
                                  </span>
                                ) : null}
                                {row.kind === 'invite' ? <PendingInviteLabel /> : null}
                              </div>
                              <p className="truncate text-xs text-muted">{row.email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {row.kind === 'member' && canManage ? (
                            <RoleSelect userId={row.id} role={row.role} />
                          ) : (
                            <RoleLabel role={row.role} />
                          )}
                        </td>
                        <td className="px-5 py-3 text-[11px] leading-4 text-muted whitespace-nowrap">
                          {row.kind === 'invite' ? `Expires ${row.expiresAt}` : row.joined}
                        </td>
                        <td className="px-5 py-3">
                          <div className="flex justify-end gap-1">
                            {row.kind === 'member' && canManage ? (
                              <PermissionsAction
                                email={row.email}
                                permissions={row.permissions}
                                onSave={(permissions) =>
                                  permissionsMutation.mutate({
                                    userId: row.id,
                                    permissions,
                                  })
                                }
                              />
                            ) : null}
                            {row.kind === 'invite' && canManage ? (
                              <SettingsActionIconButton
                                onClick={() => resendMutation.mutate(row.id)}
                                disabled={
                                  resendMutation.isPending && resendMutation.variables === row.id
                                }
                                aria-label={`Resend invite to ${row.email}`}
                                label="Resend invite"
                              >
                                {resendMutation.isPending && resendMutation.variables === row.id ? (
                                  <FiLoader className="h-4 w-4 animate-spin" />
                                ) : (
                                  <FiRefreshCw className="h-4 w-4" />
                                )}
                              </SettingsActionIconButton>
                            ) : null}
                            {canManage ? (
                              <SettingsActionIconButton
                                onClick={() => {
                                  if (row.kind === 'invite') revokeMutation.mutate(row.id);
                                  if (row.kind === 'member') {
                                    void NiceModal.show(RemoveMemberModal, {
                                      email: row.email,
                                      onConfirm: () => removeMemberMutation.mutate(row.id),
                                      role: row.role,
                                    });
                                  }
                                }}
                                aria-label={
                                  row.kind === 'invite'
                                    ? `Delete invite for ${row.email}`
                                    : `Remove ${row.email}`
                                }
                                label={row.kind === 'invite' ? 'Delete invite' : 'Remove member'}
                                className="hover:bg-app-danger-soft hover:text-app-danger-text"
                                tooltipAlign="end"
                              >
                                <FiTrash2 className="h-4 w-4" />
                              </SettingsActionIconButton>
                            ) : (
                              <span className="h-8 w-8" aria-hidden="true" />
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </BillingCard>
    </div>
  );
};
