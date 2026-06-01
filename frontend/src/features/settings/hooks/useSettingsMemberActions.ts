import { useMutation } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';
import { useToastStore } from '@/stores/useToastStore';
import {
  changeSettingsPassword,
  inviteSettingsMember,
  removeSettingsMember,
  revokeAllSettingsSessions,
  revokeSettingsSession,
  resendSettingsInvitation,
  revokeSettingsInvitation,
  updateFirmSettings,
  updateSettingsMemberRole,
  updateSettingsMemberPermissions,
  updateUserSettings,
  type FirmSettingsUpdate,
  type InviteSettingsMemberRequest,
  type UserSettingsUpdate,
} from '../api';
import { settingsKeys } from './useSettingsMembers';

export const useInviteSettingsMember = (onInvited?: () => void) => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: (request: InviteSettingsMemberRequest) => inviteSettingsMember(request),
    onSuccess: (invitedEmail) => {
      addToast(`Invitation sent to ${invitedEmail}`, 'success');
      onInvited?.();
      void queryClient.invalidateQueries({ queryKey: settingsKeys.invitations() });
    },
    onError: (error) => {
      addToast(error instanceof Error ? error.message : 'Failed to send invitation', 'error');
    },
  });
};

export const useResendSettingsInvitation = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: resendSettingsInvitation,
    onSuccess: (emailAddress) => {
      addToast(`Invitation resent to ${emailAddress}`, 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.invitations() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to resend invitation', 'error'),
  });
};

export const useRevokeSettingsInvitation = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: revokeSettingsInvitation,
    onSuccess: () => {
      addToast('Invitation deleted', 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.invitations() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to delete invitation', 'error'),
  });
};

export const useUpdateSettingsMemberPermissions = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: updateSettingsMemberPermissions,
    onSuccess: (emailAddress) => {
      addToast(`Permissions updated for ${emailAddress}`, 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.members() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to update permissions', 'error'),
  });
};

export const useUpdateSettingsMemberRole = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: updateSettingsMemberRole,
    onSuccess: () => {
      addToast('Role updated', 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.members() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to update role', 'error'),
  });
};

export const useRemoveSettingsMember = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: removeSettingsMember,
    onSuccess: () => {
      addToast('Member removed', 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.members() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to remove member', 'error'),
  });
};

export const useRevokeSettingsSession = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: revokeSettingsSession,
    onSuccess: () => {
      addToast('Session revoked', 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.sessions() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to revoke session', 'error'),
  });
};

export const useRevokeAllSettingsSessions = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: revokeAllSettingsSessions,
    onSuccess: () => {
      addToast('All other sessions revoked', 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.sessions() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to revoke all sessions', 'error'),
  });
};

export const useChangeSettingsPassword = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: changeSettingsPassword,
    onSuccess: () => {
      addToast('Password updated', 'success');
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to change password', 'error'),
  });
};

export const useUpdateUserSettings = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: (payload: UserSettingsUpdate) => updateUserSettings(payload),
    onSuccess: () => {
      addToast('User settings updated', 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.userSettings() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to update user settings', 'error'),
  });
};

export const useUpdateFirmSettings = () => {
  const addToast = useToastStore((state) => state.addToast);

  return useMutation({
    mutationFn: (payload: FirmSettingsUpdate) => updateFirmSettings(payload),
    onSuccess: () => {
      addToast('Firm settings updated', 'success');
      void queryClient.invalidateQueries({ queryKey: settingsKeys.firmSettings() });
    },
    onError: (error) =>
      addToast(error instanceof Error ? error.message : 'Unable to update firm settings', 'error'),
  });
};
