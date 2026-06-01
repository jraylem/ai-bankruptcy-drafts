import type { FirmMemberResponse, FirmResponse, InvitationResponse } from '@/services/firms.service';
import type { AppPermission } from '@/features/auth/permissions';

export type SettingsTab = 'profile' | 'members' | 'usage' | 'security';
export type SettingsMemberRole = 'admin' | 'member';
export type PermissionUpdate = { userId: string; permissions: string[] };

export type SettingsMemberRow =
  | {
      kind: 'member';
      id: string;
      email: string;
      isCurrentUser: boolean;
      name: string;
      permissions: string[];
      role: string;
      joined: string;
    }
  | {
      kind: 'invite';
      id: string;
      email: string;
      name: string;
      role: string;
      permissions: string[];
      joined: string;
      expiresAt: string;
    };

export type SettingsTabItem = {
  id: SettingsTab;
  label: string;
  permission?: AppPermission;
  to: string;
};

export type SettingsRoleOption = {
  label: string;
  value: SettingsMemberRole;
};

export type SettingsPermissionOption = {
  label: string;
  value: string;
};

export type { FirmMemberResponse, FirmResponse, InvitationResponse };
