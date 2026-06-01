export const ONBOARDING_ROLES = ['admin', 'member'] as const;
export const ONBOARDING_PERMISSION_OPTIONS = [
  { label: 'Analytics', value: 'analytics' },
  { label: 'Motion Studio', value: 'motion_studio' },
  { label: 'Case Management', value: 'case_management' },
  { label: 'Admin Dashboard', value: 'admin_dashboard' },
  { label: 'Approve Motions', value: 'approve_motions' },
  { label: 'Manage Members', value: 'manage_members' },
];
export const ONBOARDING_PRACTICE_TYPES = [
  'bankruptcy',
  'family_law',
  'immigration',
  'estate_planning',
] as const;
export const AVAILABLE_ONBOARDING_PRACTICE_TYPES = ['bankruptcy'] as const;

export type OnboardingRole = (typeof ONBOARDING_ROLES)[number];
export const DEFAULT_ONBOARDING_PERMISSIONS_BY_ROLE: Record<OnboardingRole, string[]> = {
  admin: ONBOARDING_PERMISSION_OPTIONS.map((option) => option.value),
  member: ['analytics', 'motion_studio', 'case_management'],
};
export type OnboardingPracticeType = (typeof ONBOARDING_PRACTICE_TYPES)[number];
export type AvailableOnboardingPracticeType = (typeof AVAILABLE_ONBOARDING_PRACTICE_TYPES)[number];

export const isAvailableOnboardingPracticeType = (
  practiceType: OnboardingPracticeType
): practiceType is AvailableOnboardingPracticeType =>
  (AVAILABLE_ONBOARDING_PRACTICE_TYPES as readonly OnboardingPracticeType[]).includes(practiceType);

export interface InvitedMember {
  email: string;
  permissions: string[];
  role: OnboardingRole;
}

export interface OnboardingFormValues {
  firmName: string;
  firmAddress: string;
  contactNumber: string;
  practiceType: OnboardingPracticeType;
  ownerName: string;
  ownerEmail: string;
  inviteEmail: string;
  invitePermissions: string[];
  inviteRole: OnboardingRole;
}
