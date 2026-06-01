import type { FirmMemberResponse } from '../../types';

export const initialsFor = (label: string) =>
  label
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();

export const displayNameFor = (member: FirmMemberResponse) => {
  const fullName = [member.first_name, member.last_name].filter(Boolean).join(' ').trim();
  return fullName || member.email;
};

export const formatDate = (value?: string | null) => {
  if (!value) return '\u2014';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '\u2014';
  return parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

export const normalizeRole = (role?: string | null): string => {
  if (role === 'superadmin' || role === 'super_admin') return 'superadmin';
  if (role === 'firm_owner') return 'firm_owner';
  if (role === 'admin') return 'admin';
  return 'member';
};

export const roleRank = (role?: string | null) => {
  const normalizedRole = normalizeRole(role);
  if (normalizedRole === 'superadmin') return 4;
  if (normalizedRole === 'firm_owner') return 3;
  if (normalizedRole === 'admin') return 2;
  return 1;
};

export const roleLabelFor = (role: string) =>
  role === 'superadmin'
    ? 'superadmin'
    : role === 'firm_owner'
      ? 'firm owner'
      : role === 'admin'
        ? 'admin'
        : 'member';
