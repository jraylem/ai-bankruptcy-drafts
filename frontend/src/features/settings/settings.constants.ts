import type {
  SettingsMemberRole,
  SettingsPermissionOption,
  SettingsRoleOption,
  SettingsTabItem,
} from './types';
import { APP_PERMISSIONS } from '@/features/auth/permissions';

export const SETTINGS_TABS: SettingsTabItem[] = [
  {
    id: 'profile',
    label: 'Profile',
    to: '/settings',
    permission: APP_PERMISSIONS.adminDashboard,
  },
  {
    id: 'members',
    label: 'Members',
    to: '/settings/members',
    permission: APP_PERMISSIONS.manageMembers,
  },
  {
    id: 'usage',
    label: 'Usage Limits',
    to: '/settings/usage',
    permission: APP_PERMISSIONS.adminDashboard,
  },
  {
    id: 'security',
    label: 'Security',
    to: '/settings/security',
    permission: APP_PERMISSIONS.adminDashboard,
  },
];

export const ROLE_OPTIONS: SettingsRoleOption[] = [
  { label: 'Admin', value: 'admin' },
  { label: 'Member', value: 'member' },
];

export const PERMISSION_OPTIONS: SettingsPermissionOption[] = [
  { label: 'Analytics', value: 'analytics' },
  { label: 'Motion Studio', value: 'motion_studio' },
  { label: 'Case Management', value: 'case_management' },
  { label: 'Admin Dashboard', value: 'admin_dashboard' },
  { label: 'Approve Motions', value: 'approve_motions' },
  { label: 'Manage Members', value: 'manage_members' },
];

const ADMIN_DEFAULT_PERMISSIONS = PERMISSION_OPTIONS.map((option) => option.value);

export const DEFAULT_PERMISSIONS_BY_ROLE: Record<SettingsMemberRole, string[]> = {
  admin: ADMIN_DEFAULT_PERMISSIONS,
  member: ['analytics', 'motion_studio', 'case_management'],
};

export const permissionLabels: Record<string, string> = {
  analytics: 'Analytics',
  motion_studio: 'Motion Studio',
  case_management: 'Case Management',
  admin_dashboard: 'Admin Dashboard',
  approve_motions: 'Approve Motions',
  manage_members: 'Manage Members',
};
