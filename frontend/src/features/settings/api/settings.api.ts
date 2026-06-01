import { API_ENDPOINTS } from '@/constants';
import { apiService } from '@/services/api';
import { firmsService } from '@/services/firms.service';
import type {
  FirmMemberResponse,
  FirmResponse,
  InvitationResponse,
  PermissionUpdate,
  SettingsMemberRole,
} from '../types';

export type UpdateSettingsFirmRequest = {
  address: string;
  contactNumber: string;
  firmType: string;
  name: string;
};

export type InviteSettingsMemberRequest = {
  email: string;
  permissions: string[];
  role: SettingsMemberRole;
};

export type SettingsSessionResponse = {
  id: string;
  created_at: string | null;
  expires_at: string;
  ip_address: string | null;
  user_agent: string | null;
  is_current: boolean;
};

export type SettingsSessionListResponse = {
  sessions: SettingsSessionResponse[];
};

export type SettingsBillingSummaryResponse = {
  plan_name: string | null;
  subscription_status: string | null;
  seat_used: number;
  seat_limit: number;
  portal_url: string | null;
};

export type UserSettingsResponse = {
  user_id: string;
  notification_email: boolean;
  notification_inapp: boolean;
  theme: string;
  notify_motion_approved: boolean;
  notify_motion_rejected: boolean;
  email_verified: boolean | null;
  updated_at: string | null;
};

export type UserSettingsUpdate = Partial<
  Pick<
    UserSettingsResponse,
    | 'notification_email'
    | 'notification_inapp'
    | 'notify_motion_approved'
    | 'notify_motion_rejected'
    | 'theme'
  >
>;

export type FirmSettingsResponse = {
  firm_id: string;
  allow_member_invites: boolean;
  motion_approval_required: boolean;
  enable_chat_rooms: boolean;
  enable_motion_comments: boolean;
  allowed_domain: string | null;
  onboarding_status: string | null;
  updated_at: string | null;
};

export type FirmSettingsUpdate = Partial<
  Pick<
    FirmSettingsResponse,
    | 'allow_member_invites'
    | 'motion_approval_required'
    | 'enable_chat_rooms'
    | 'enable_motion_comments'
    | 'allowed_domain'
  >
>;

export type UserPermissionsResponse = {
  role: string;
  role_display: string;
  permissions: string[];
};

export type FirmActivityItem = {
  id: string;
  action: string;
  actor_email?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
};

export type FirmActivityResponse = {
  items: FirmActivityItem[];
  total: number;
  limit: number;
  offset: number;
};

export const fetchSettingsFirm = async (): Promise<FirmResponse> => {
  const response = await firmsService.getFirm();
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load firm profile');
  }
  return response.data;
};

export const updateSettingsFirm = async ({
  address,
  contactNumber,
  firmType,
  name,
}: UpdateSettingsFirmRequest): Promise<FirmResponse> => {
  const response = await firmsService.updateFirm({
    name: name.trim(),
    address: address.trim(),
    firm_type: firmType.trim(),
    contact_number: contactNumber.trim() || undefined,
  });

  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to update firm profile');
  }

  return response.data;
};

export const fetchUserSettings = async (): Promise<UserSettingsResponse> => {
  const response = await apiService.get<UserSettingsResponse>(API_ENDPOINTS.SETTINGS.USER);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load user settings');
  }
  return response.data;
};

export const updateUserSettings = async (
  payload: UserSettingsUpdate
): Promise<UserSettingsResponse> => {
  const response = await apiService.patch<UserSettingsResponse>(API_ENDPOINTS.SETTINGS.USER, payload);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to update user settings');
  }
  return response.data;
};

export const fetchFirmSettings = async (): Promise<FirmSettingsResponse> => {
  const response = await apiService.get<FirmSettingsResponse>(API_ENDPOINTS.SETTINGS.FIRM);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load firm settings');
  }
  return response.data;
};

export const updateFirmSettings = async (
  payload: FirmSettingsUpdate
): Promise<FirmSettingsResponse> => {
  const response = await apiService.patch<FirmSettingsResponse>(API_ENDPOINTS.SETTINGS.FIRM, payload);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to update firm settings');
  }
  return response.data;
};

export const fetchUserPermissions = async (): Promise<UserPermissionsResponse> => {
  const response = await apiService.get<UserPermissionsResponse>(API_ENDPOINTS.SETTINGS.PERMISSIONS);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load permissions');
  }
  return response.data;
};

export const fetchSettingsMembers = async (): Promise<FirmMemberResponse[]> => {
  const response = await firmsService.listMembers();
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load members');
  }
  return response.data;
};

export const fetchSettingsInvitations = async (): Promise<InvitationResponse[]> => {
  const response = await firmsService.listPendingInvitations();
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load invitations');
  }
  return response.data;
};

export const inviteSettingsMember = async ({
  email,
  permissions,
  role,
}: InviteSettingsMemberRequest): Promise<string> => {
  const normalizedEmail = email.trim().toLowerCase();
  if (!normalizedEmail) throw new Error('Email is required');

  const response = await firmsService.inviteMember({ email: normalizedEmail, role, permissions });
  if (response.error) throw new Error(response.error);
  return normalizedEmail;
};

export const resendSettingsInvitation = async (invitationId: string): Promise<string> => {
  const response = await firmsService.resendInvitation(invitationId);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to resend invitation');
  }
  return response.data.email;
};

export const revokeSettingsInvitation = async (invitationId: string): Promise<void> => {
  const response = await firmsService.revokeInvitation(invitationId);
  if (response.error) throw new Error(response.error);
};

export const updateSettingsMemberPermissions = async ({
  userId,
  permissions,
}: PermissionUpdate): Promise<string> => {
  const response = await firmsService.updateMemberPermissions(userId, permissions);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to update permissions');
  }
  return response.data.email;
};

export const updateSettingsMemberRole = async ({
  userId,
  role,
}: {
  role: SettingsMemberRole;
  userId: string;
}): Promise<void> => {
  const response = await apiService.patch(API_ENDPOINTS.SETTINGS.FIRM_MEMBER_ROLE(userId), { role });
  if (response.error) throw new Error(response.error);
};

export const removeSettingsMember = async (userId: string): Promise<void> => {
  const response = await firmsService.removeMember(userId);
  if (response.error) throw new Error(response.error);
};

export const fetchSettingsSessions = async (): Promise<SettingsSessionResponse[]> => {
  const response = await apiService.get<SettingsSessionListResponse>(API_ENDPOINTS.SETTINGS.SECURITY_SESSIONS);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load sessions');
  }
  return response.data.sessions;
};

export const revokeSettingsSession = async (sessionId: string): Promise<void> => {
  const response = await apiService.delete(API_ENDPOINTS.SETTINGS.SECURITY_SESSION(sessionId));
  if (response.error) throw new Error(response.error);
};

export const revokeAllSettingsSessions = async (): Promise<void> => {
  const response = await apiService.post(API_ENDPOINTS.SETTINGS.SECURITY_SESSIONS_REVOKE_ALL);
  if (response.error) throw new Error(response.error);
};

export const changeSettingsPassword = async ({
  currentPassword,
  newPassword,
}: {
  currentPassword: string;
  newPassword: string;
}): Promise<void> => {
  const response = await apiService.post(API_ENDPOINTS.SETTINGS.PASSWORD, {
    current_password: currentPassword,
    new_password: newPassword,
  });
  if (response.error) throw new Error(response.error);
};

export const fetchSettingsBillingSummary = async (): Promise<SettingsBillingSummaryResponse> => {
  const response = await apiService.get<SettingsBillingSummaryResponse>(
    API_ENDPOINTS.SETTINGS.BILLING_SUMMARY
  );
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load billing summary');
  }
  return response.data;
};

export const fetchTwoFactorStatus = async (): Promise<Record<string, unknown>> => {
  const response = await apiService.get<Record<string, unknown>>(API_ENDPOINTS.SETTINGS.SECURITY_2FA);
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load 2FA status');
  }
  return response.data;
};

export const fetchFirmActivity = async ({
  limit = 10,
  offset = 0,
}: {
  limit?: number;
  offset?: number;
} = {}): Promise<FirmActivityResponse> => {
  const response = await apiService.get<FirmActivityResponse>(API_ENDPOINTS.SETTINGS.FIRM_ACTIVITY, {
    params: { limit, offset },
  });
  if (response.error || !response.data) {
    throw new Error(response.error || 'Unable to load firm activity');
  }
  return response.data;
};
