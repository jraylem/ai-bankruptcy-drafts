import { useQuery } from '@tanstack/react-query';
import {
  fetchFirmActivity,
  fetchFirmSettings,
  fetchSettingsBillingSummary,
  fetchSettingsInvitations,
  fetchSettingsMembers,
  fetchSettingsSessions,
  fetchTwoFactorStatus,
  fetchUserPermissions,
  fetchUserSettings,
} from '../api';

export const settingsKeys = {
  all: ['settings'] as const,
  firm: () => [...settingsKeys.all, 'firm'] as const,
  members: () => [...settingsKeys.all, 'members'] as const,
  invitations: () => [...settingsKeys.all, 'invitations'] as const,
  sessions: () => [...settingsKeys.all, 'sessions'] as const,
  billingSummary: () => [...settingsKeys.all, 'billing-summary'] as const,
  userSettings: () => [...settingsKeys.all, 'user-settings'] as const,
  firmSettings: () => [...settingsKeys.all, 'firm-settings'] as const,
  permissions: () => [...settingsKeys.all, 'permissions'] as const,
  twoFactor: () => [...settingsKeys.all, 'two-factor'] as const,
  firmActivity: ({ limit, offset }: { limit: number; offset: number }) =>
    [...settingsKeys.all, 'firm-activity', limit, offset] as const,
};

export const useSettingsMembers = () =>
  useQuery({
    queryKey: settingsKeys.members(),
    queryFn: fetchSettingsMembers,
  });

export const useSettingsInvitations = () =>
  useQuery({
    queryKey: settingsKeys.invitations(),
    queryFn: fetchSettingsInvitations,
  });

export const useSettingsSessions = () =>
  useQuery({
    queryKey: settingsKeys.sessions(),
    queryFn: fetchSettingsSessions,
  });

export const useSettingsBillingSummary = () =>
  useQuery({
    queryKey: settingsKeys.billingSummary(),
    queryFn: fetchSettingsBillingSummary,
  });

export const useUserSettings = () =>
  useQuery({
    queryKey: settingsKeys.userSettings(),
    queryFn: fetchUserSettings,
  });

export const useFirmSettings = () =>
  useQuery({
    queryKey: settingsKeys.firmSettings(),
    queryFn: fetchFirmSettings,
  });

export const useUserPermissions = () =>
  useQuery({
    queryKey: settingsKeys.permissions(),
    queryFn: fetchUserPermissions,
  });

export const useTwoFactorStatus = () =>
  useQuery({
    queryKey: settingsKeys.twoFactor(),
    queryFn: fetchTwoFactorStatus,
  });

export const useFirmActivity = ({ limit, offset }: { limit: number; offset: number }) =>
  useQuery({
    queryKey: settingsKeys.firmActivity({ limit, offset }),
    queryFn: () => fetchFirmActivity({ limit, offset }),
  });
