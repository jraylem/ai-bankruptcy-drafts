import type { User } from '@/types';

export const APP_PERMISSIONS = {
  analytics: 'analytics',
  motionStudio: 'motion_studio',
  caseManagement: 'case_management',
  adminDashboard: 'admin_dashboard',
  approveMotions: 'approve_motions',
  manageMembers: 'manage_members',
} as const;

export type AppPermission = (typeof APP_PERMISSIONS)[keyof typeof APP_PERMISSIONS];

const PRIVILEGED_ROLES = new Set(['firm_owner', 'admin']);

export const hasPermission = (user: User | null | undefined, permission: AppPermission) => {
  if (!user) return false;
  if (user.role && PRIVILEGED_ROLES.has(user.role)) return true;
  return Boolean(user.permissions?.includes(permission));
};

export const hasAnyPermission = (
  user: User | null | undefined,
  permissions: AppPermission[]
) => permissions.some((permission) => hasPermission(user, permission));

export const getDefaultAuthorizedPath = (user: User | null | undefined) => {
  if (hasPermission(user, APP_PERMISSIONS.caseManagement)) return '/case/new';
  if (hasPermission(user, APP_PERMISSIONS.analytics)) return '/analytics';
  if (hasPermission(user, APP_PERMISSIONS.motionStudio)) return '/studio';
  if (hasPermission(user, APP_PERMISSIONS.adminDashboard)) return '/billing';
  return '/settings';
};
