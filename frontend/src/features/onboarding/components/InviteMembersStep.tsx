import NiceModal from '@ebay/nice-modal-react';
import { Controller, useFormContext } from 'react-hook-form';
import { FiMail, FiTrash2 } from 'react-icons/fi';
import { SelectDropdown } from '@/components/common';
import { getEmailDomain } from '../schema';
import {
  DEFAULT_ONBOARDING_PERMISSIONS_BY_ROLE,
  type InvitedMember,
  type OnboardingFormValues,
  type OnboardingRole,
} from '../types';
import { RoleRestrictionModal } from './RoleRestrictionModal';

interface InviteMembersStepProps {
  invites: InvitedMember[];
  onAddInvite: () => Promise<void>;
  onRemoveInvite: (email: string) => void;
}

const ROLE_OPTIONS: Array<{ label: string; value: OnboardingRole }> = [
  { label: 'Admin', value: 'admin' },
  { label: 'Member', value: 'member' },
];

export const InviteMembersStep = ({
  invites,
  onAddInvite,
  onRemoveInvite,
}: InviteMembersStepProps) => {
  const {
    control,
    formState: { errors },
    register,
    setValue,
    watch,
  } = useFormContext<OnboardingFormValues>();
  const ownerEmail = watch('ownerEmail');
  const ownerName = watch('ownerName');
  const ownerDomain = getEmailDomain(ownerEmail);

  return (
    <section>
      <div>
        <h1 className="font-poppins text-2xl font-semibold text-app-accent-text">Invite Members</h1>
        <p className="mt-2 max-w-3xl text-sm text-text-secondary">
          Step 2: Add teammates now, or skip and invite them later.{' '}
          <button
            type="button"
            className="font-semibold text-app-accent-text transition hover:text-app-accent-text"
            onClick={() => NiceModal.show(RoleRestrictionModal)}
          >
            See role restrictions
          </button>
        </p>

        <div className="mt-12 flex flex-col gap-6 lg:flex-row lg:items-start">
          <div className="group w-full max-w-[320px] sm:w-[320px]">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary">
              Email
            </label>
            <input
              type="email"
              placeholder={ownerDomain ? `name@${ownerDomain}` : 'name@firmdomain.com'}
              className={`w-full border-0 border-b bg-transparent px-0 pb-2 pt-1 text-sm text-text-secondary outline-none transition-colors placeholder:text-subtle focus:ring-0 ${
                errors.inviteEmail?.message
                  ? 'border-app-danger-text'
                  : 'border-border focus:border-app-accent group-focus-within:border-app-accent'
              }`}
              {...register('inviteEmail')}
            />
            {errors.inviteEmail?.message ? (
              <p className="mt-1.5 text-xs font-medium text-app-danger-text">
                {errors.inviteEmail.message}
              </p>
            ) : null}
          </div>

          <div className="w-max">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary">
              Role
            </label>
            <Controller
              control={control}
              name="inviteRole"
              render={({ field }) => (
                <SelectDropdown
                  value={field.value}
                  onChange={(value) => {
                    const nextRole = value as OnboardingRole;
                    field.onChange(nextRole);
                    setValue('invitePermissions', DEFAULT_ONBOARDING_PERMISSIONS_BY_ROLE[nextRole]);
                  }}
                  options={ROLE_OPTIONS}
                  className="w-max"
                  buttonClassName="flex h-[42px] w-auto min-w-[128px] items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-2 text-sm font-medium text-text-secondary shadow-sm transition hover:border-app-border-strong focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                />
              )}
            />
          </div>

          <button
            type="button"
            onClick={() => void onAddInvite()}
            className="inline-flex h-[42px] w-max items-center justify-center gap-2 self-start rounded-xl bg-app-accent px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-app-accent-text lg:mt-5"
          >
            <FiMail className="h-4 w-4" />
            Invite
          </button>
        </div>
      </div>

      <div className="mt-10 rounded-2xl bg-surface p-5 shadow-sm">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="font-poppins text-lg font-semibold text-text-secondary">Members</h2>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4 rounded-2xl bg-surface-muted px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-app-accent text-sm font-semibold text-white">
                {(ownerName || ownerEmail).charAt(0).toUpperCase()}
              </span>
              <p className="min-w-0 truncate text-sm font-medium text-text-secondary">
                {ownerEmail || 'Owner account'}
              </p>
            </div>
            <span className="shrink-0 rounded-lg bg-app-accent px-3 py-1 text-xs font-semibold text-white">
              Superadmin (you)
            </span>
          </div>

          {invites.map((member) => (
            <div
              key={member.email}
              className="flex items-center justify-between gap-4 rounded-2xl border border-border px-4 py-3"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-app-accent-soft text-sm font-semibold text-app-accent-text">
                  {member.email.charAt(0).toUpperCase()}
                </span>
                <p className="min-w-0 truncate text-sm font-medium text-text-secondary">
                  {member.email}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="rounded-lg bg-app-accent-soft px-3 py-1 text-xs font-semibold capitalize text-app-accent-text">
                  {member.role}
                </span>
                <button
                  type="button"
                  className="rounded-lg p-2 text-text-secondary transition hover:bg-surface-muted hover:text-app-danger-text"
                  aria-label={`Remove ${member.email}`}
                  onClick={() => onRemoveInvite(member.email)}
                >
                  <FiTrash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
