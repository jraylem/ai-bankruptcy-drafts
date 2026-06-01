import { useState } from 'react';
import { FiMail } from 'react-icons/fi';
import { z } from 'zod';
import { SelectDropdown } from '@/components/common';
import { getEmailDomain, isEmailInAllowedDomain } from '@/utils/emailDomain';
import {
  DEFAULT_PERMISSIONS_BY_ROLE,
  PERMISSION_OPTIONS,
  ROLE_OPTIONS,
} from '../../settings.constants';
import { useInviteSettingsMember, useSettingsFirm } from '../../hooks';
import type { SettingsMemberRole } from '../../types';

export const AddMemberForm = () => {
  const firmQuery = useSettingsFirm();
  const ownerEmail = firmQuery.data?.owner_email ?? '';
  const allowedDomain = getEmailDomain(ownerEmail);
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [role, setRole] = useState<SettingsMemberRole>('admin');
  const [permissions, setPermissions] = useState<string[]>(DEFAULT_PERMISSIONS_BY_ROLE.admin);
  const inviteMutation = useInviteSettingsMember(() => {
    setEmail('');
    setEmailError(null);
    setRole('admin');
    setPermissions(DEFAULT_PERMISSIONS_BY_ROLE.admin);
  });

  const sendInvite = () => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail) {
      setEmailError('Enter an email before sending an invite');
      return;
    }

    if (!z.string().email().safeParse(normalizedEmail).success) {
      setEmailError('Enter a valid email');
      return;
    }

    if (normalizedEmail === ownerEmail.trim().toLowerCase()) {
      setEmailError('You are already listed as the workspace owner');
      return;
    }

    if (!allowedDomain) {
      setEmailError('Firm owner email is missing a domain');
      return;
    }

    if (!isEmailInAllowedDomain(normalizedEmail, allowedDomain)) {
      setEmailError(`Invite must use @${allowedDomain}`);
      return;
    }

    setEmailError(null);
    inviteMutation.mutate({ email: normalizedEmail, permissions, role });
  };

  return (
    <section className="rounded-2xl bg-surface p-5">
      <h2 className="font-poppins text-lg font-semibold text-text">Add Member</h2>
      <div className="mt-4 flex flex-col gap-3 xl:flex-row xl:items-start">
        <div className="w-full max-w-lg">
          <div
            className={`flex flex-col rounded-lg border bg-surface focus-within:ring-2 md:flex-row ${
              emailError
                ? 'border-app-danger-text focus-within:ring-app-danger-soft'
                : 'border-border focus-within:border-app-accent/55 focus-within:ring-app-accent-soft'
            }`}
          >
            <input
              type="email"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setEmailError(null);
              }}
              placeholder={allowedDomain ? `name@${allowedDomain}` : 'Email'}
              className="h-10 min-w-0 flex-1 rounded-lg border-0 bg-transparent px-3 text-sm text-text outline-none placeholder:text-muted focus:ring-0"
            />
            <div className="border-t border-border md:w-40 md:border-l md:border-t-0">
              <SelectDropdown
                value={role}
                onChange={(value) => {
                  const nextRole = value as SettingsMemberRole;
                  setRole(nextRole);
                  setPermissions(DEFAULT_PERMISSIONS_BY_ROLE[nextRole]);
                }}
                options={ROLE_OPTIONS}
                buttonClassName="flex h-10 w-full items-center justify-between rounded-lg bg-surface px-3 text-sm font-semibold text-text outline-none focus:ring-2 focus:ring-app-accent-soft"
              />
            </div>
          </div>
          {emailError ? (
            <p className="mt-1.5 text-xs font-medium text-app-danger-text">{emailError}</p>
          ) : allowedDomain ? (
            <p className="mt-1.5 text-xs text-muted">Invites must use @{allowedDomain}.</p>
          ) : null}
        </div>

        <div className="w-full xl:w-56">
          <SelectDropdown
            multiple
            values={permissions}
            onValuesChange={setPermissions}
            options={PERMISSION_OPTIONS}
            placeholder="Permissions"
            multipleSummaryLabel={(count) => `${count} permissions`}
            buttonClassName="flex h-10 w-full items-center justify-between rounded-lg border border-border bg-surface px-3 text-sm font-semibold text-text-secondary outline-none transition hover:border-app-accent/40 focus:ring-2 focus:ring-app-accent-soft"
          />
        </div>

        <button
          type="button"
          onClick={sendInvite}
          disabled={inviteMutation.isPending || firmQuery.isLoading}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-app-accent px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-app-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <FiMail className="h-4 w-4" />
          {inviteMutation.isPending ? 'Inviting...' : 'Invite'}
        </button>
      </div>
    </section>
  );
};
