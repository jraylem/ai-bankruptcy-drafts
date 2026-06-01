import React, { useEffect, useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import {
  FiAlertCircle,
  FiBriefcase,
  FiCheckCircle,
  FiMail,
  FiPhone,
  FiSave,
  FiShield,
} from 'react-icons/fi';
import { z } from 'zod';
import {
  useFirmSettings,
  useSettingsFirm,
  useUpdateFirmSettings,
  useUpdateSettingsFirm,
  useUpdateUserSettings,
  useUserPermissions,
  useUserSettings,
} from '../../hooks';
import { permissionLabels } from '../../settings.constants';
import { getEmailDomain, isEmailInAllowedDomain } from '@/utils/emailDomain';

const createFirmProfileSchema = (ownerEmail: string) => {
  const ownerDomain = getEmailDomain(ownerEmail);

  return z
    .object({
      name: z.string().trim().min(1, 'Firm name is required.'),
      address: z.string().trim().email('Enter a valid firm email address.'),
      firmType: z.string().trim().optional().default(''),
      contactNumber: z
        .string()
        .trim()
        .refine((value) => !value || /^\d+$/.test(value), {
          message: 'Contact number must contain numbers only.',
        }),
    })
    .superRefine((values, context) => {
      if (isEmailInAllowedDomain(values.address, ownerDomain)) return;

      context.addIssue({
        code: 'custom',
        path: ['address'],
        message: ownerDomain
          ? `Firm email must use @${ownerDomain}`
          : 'Firm email must match the owner email domain.',
      });
    });
};

type FirmProfileSchema = ReturnType<typeof createFirmProfileSchema>;
type FirmProfileFormInput = z.input<FirmProfileSchema>;
type FirmProfileFormValues = z.output<FirmProfileSchema>;

const ProfileField = ({
  error,
  icon,
  label,
  numericOnly = false,
  ...inputProps
}: React.InputHTMLAttributes<HTMLInputElement> & {
  error?: string;
  icon: React.ReactNode;
  label: string;
  numericOnly?: boolean;
}) => (
  <div>
    <label className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary">
      {label}
    </label>
    <div className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
        {icon}
      </span>
      <input
        {...inputProps}
        inputMode={numericOnly ? 'numeric' : inputProps.inputMode}
        pattern={numericOnly ? '[0-9]*' : inputProps.pattern}
        onInput={(event) => {
          if (numericOnly) {
            event.currentTarget.value = event.currentTarget.value.replace(/\D/g, '');
          }
          inputProps.onInput?.(event);
        }}
        className={`h-11 w-full rounded-xl border bg-surface-muted pl-10 pr-3 text-sm text-text-secondary outline-none transition placeholder:text-subtle focus:ring-2 ${
          error
            ? 'border-app-danger-text focus:border-app-danger-text focus:ring-app-danger-soft'
            : 'border-border focus:border-app-accent focus:ring-app-accent-soft'
        }`}
      />
    </div>
    {error ? <p className="mt-1.5 text-xs font-medium text-app-danger-text">{error}</p> : null}
  </div>
);

const ToggleSetting = ({
  checked,
  description,
  disabled,
  label,
  onChange,
}: {
  checked: boolean;
  description: string;
  disabled?: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) => (
  <div className="flex items-start justify-between gap-4 rounded-xl border border-border bg-surface-muted px-4 py-3">
    <div>
      <p className="text-sm font-semibold text-text">{label}</p>
      <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
    </div>
    <button
      type="button"
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition disabled:cursor-not-allowed disabled:opacity-60 ${
        checked ? 'bg-app-accent' : 'bg-border'
      }`}
      aria-pressed={checked}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition ${
          checked ? 'left-5.2' : 'left-0.5'
        }`}
      />
    </button>
  </div>
);

const formatPermissionLabel = (permission: string) =>
  permissionLabels[permission] ??
  permission
    .replace(/_/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');

export const ProfileTab = () => {
  const firmQuery = useSettingsFirm();
  const userSettingsQuery = useUserSettings();
  const firmSettingsQuery = useFirmSettings();
  const permissionsQuery = useUserPermissions();
  const updateFirmMutation = useUpdateSettingsFirm();
  const updateUserSettingsMutation = useUpdateUserSettings();
  const updateFirmSettingsMutation = useUpdateFirmSettings();
  const firm = firmQuery.data;
  const firmProfileSchema = useMemo(
    () => createFirmProfileSchema(firm?.owner_email ?? ''),
    [firm?.owner_email]
  );
  const {
    formState: { errors, isDirty },
    handleSubmit,
    register,
    reset,
  } = useForm<FirmProfileFormInput, unknown, FirmProfileFormValues>({
    resolver: zodResolver(firmProfileSchema),
    defaultValues: {
      name: '',
      address: '',
      firmType: '',
      contactNumber: '',
    },
  });

  useEffect(() => {
    if (!firm) return;
    reset({
      name: firm.name ?? '',
      address: firm.address ?? '',
      firmType: firm.firm_type ?? '',
      contactNumber: firm.contact_number ?? '',
    });
  }, [firm, reset]);

  const onSubmit = async (values: FirmProfileFormValues) => {
    const updatedFirm = await updateFirmMutation
      .mutateAsync({
        ...values,
        firmType: firm?.firm_type ?? values.firmType,
      })
      .catch(() => undefined);
    if (!updatedFirm) return;
    reset({
      name: updatedFirm.name ?? '',
      address: updatedFirm.address ?? '',
      firmType: updatedFirm.firm_type ?? '',
      contactNumber: updatedFirm.contact_number ?? '',
    });
  };

  if (firmQuery.isLoading) {
    return (
      <div className="space-y-6">
        <div className="h-48 animate-pulse rounded-2xl bg-surface" />
      </div>
    );
  }

  if (firmQuery.error || !firm) {
    return (
      <div className="flex items-start gap-2 rounded-xl border border-app-danger-text/25 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
        <FiAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        {firmQuery.error instanceof Error ? firmQuery.error.message : 'Unable to load firm profile'}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-2xl bg-surface p-5">
        <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-poppins text-lg font-semibold text-text">Firm Profile</h2>
            <p className="mt-1 text-sm text-muted">
              Update the firm details used across onboarding, billing, and workspace settings.
            </p>
          </div>
          <span
            className={`inline-flex items-center gap-2 rounded-lg px-2.5 py-1 text-xs font-semibold ${
              firm.is_active
                ? 'bg-app-success-soft text-app-success-text'
                : 'bg-app-danger-soft text-app-danger-text'
            }`}
          >
            <FiCheckCircle className="h-3.5 w-3.5" />
            {firm.is_active ? 'Active firm' : 'Inactive firm'}
          </span>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-5">
          <div className="grid gap-4 lg:grid-cols-2">
            <ProfileField
              label="Firm name"
              icon={<FiBriefcase className="h-4 w-4" />}
              placeholder="Firm name"
              error={errors.name?.message}
              {...register('name')}
            />
            <ProfileField
              label="Practice type"
              icon={<FiBriefcase className="h-4 w-4" />}
              placeholder="Practice type"
              disabled
              error={errors.firmType?.message}
              {...register('firmType')}
            />
            <ProfileField
              label="Contact number"
              icon={<FiPhone className="h-4 w-4" />}
              placeholder="Contact number"
              numericOnly
              error={errors.contactNumber?.message}
              {...register('contactNumber')}
            />
            <ProfileField
              label="Firm email address"
              icon={<FiMail className="h-4 w-4" />}
              placeholder="name@firmdomain.com"
              error={errors.address?.message}
              {...register('address')}
            />
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={!isDirty || updateFirmMutation.isPending}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-app-accent px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-app-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <FiSave className="h-4 w-4" />
              {updateFirmMutation.isPending ? 'Saving...' : 'Save changes'}
            </button>
          </div>
        </form>
      </section>

      <section className="rounded-2xl bg-surface p-5">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-app-accent-soft text-app-accent-text">
            <FiShield className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="font-poppins text-lg font-semibold text-text">Your access</h2>
            <p className="mt-1 text-sm text-muted">
              Your current role and workspace permissions are managed by firm admins.
            </p>
            {permissionsQuery.isLoading ? (
              <div className="mt-4 h-9 w-full max-w-md animate-pulse rounded-lg bg-surface-muted" />
            ) : permissionsQuery.data ? (
              <div className="mt-4 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex h-8 items-center rounded-lg bg-surface-muted px-2.5 text-xs font-semibold text-muted">
                    {permissionsQuery.data.role_display}
                  </span>
                  {permissionsQuery.data.permissions.map((permission) => (
                    <span
                      key={permission}
                      className="inline-flex h-8 items-center rounded-lg bg-app-accent-soft px-2.5 text-xs font-semibold text-app-accent-text"
                    >
                      {formatPermissionLabel(permission)}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <p className="mt-4 rounded-xl border border-dashed border-border px-4 py-4 text-sm text-muted">
                Permission details are unavailable.
              </p>
            )}
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-2xl bg-surface p-5">
          <div className="border-b border-border pb-4">
            <h2 className="font-poppins text-lg font-semibold text-text">User Preferences</h2>
            <p className="mt-1 text-sm text-muted">
              Choose how you receive workspace and motion updates.
            </p>
          </div>
          {userSettingsQuery.isLoading ? (
            <div className="mt-5 space-y-3">
              <div className="h-16 animate-pulse rounded-xl bg-surface-muted" />
              <div className="h-16 animate-pulse rounded-xl bg-surface-muted" />
            </div>
          ) : userSettingsQuery.data ? (
            <div className="mt-5 space-y-3">
              <ToggleSetting
                label="Email notifications"
                description="Receive account, collaboration, and workflow notifications by email."
                checked={userSettingsQuery.data.notification_email}
                disabled={updateUserSettingsMutation.isPending}
                onChange={(notification_email) =>
                  updateUserSettingsMutation.mutate({ notification_email })
                }
              />
              <ToggleSetting
                label="In-app notifications"
                description="Show alerts and badges inside the BKDrafts workspace."
                checked={userSettingsQuery.data.notification_inapp}
                disabled={updateUserSettingsMutation.isPending}
                onChange={(notification_inapp) =>
                  updateUserSettingsMutation.mutate({ notification_inapp })
                }
              />
              <ToggleSetting
                label="Motion approved"
                description="Notify me when a motion I own or follow is approved."
                checked={userSettingsQuery.data.notify_motion_approved}
                disabled={updateUserSettingsMutation.isPending}
                onChange={(notify_motion_approved) =>
                  updateUserSettingsMutation.mutate({ notify_motion_approved })
                }
              />
              <ToggleSetting
                label="Motion rejected"
                description="Notify me when a motion needs revision after review."
                checked={userSettingsQuery.data.notify_motion_rejected}
                disabled={updateUserSettingsMutation.isPending}
                onChange={(notify_motion_rejected) =>
                  updateUserSettingsMutation.mutate({ notify_motion_rejected })
                }
              />
            </div>
          ) : (
            <p className="mt-5 rounded-xl border border-dashed border-border px-4 py-6 text-sm text-muted">
              User settings are unavailable.
            </p>
          )}
        </div>

        <div className="rounded-2xl bg-surface p-5">
          <div className="border-b border-border pb-4">
            <h2 className="font-poppins text-lg font-semibold text-text">Firm Controls</h2>
            <p className="mt-1 text-sm text-muted">
              Manage workspace-level collaboration and review defaults.
            </p>
          </div>
          {firmSettingsQuery.isLoading ? (
            <div className="mt-5 space-y-3">
              <div className="h-16 animate-pulse rounded-xl bg-surface-muted" />
              <div className="h-16 animate-pulse rounded-xl bg-surface-muted" />
            </div>
          ) : firmSettingsQuery.data ? (
            <div className="mt-5 space-y-3">
              <ToggleSetting
                label="Allow member invites"
                description="Let non-owner admins invite users when their permissions allow it."
                checked={firmSettingsQuery.data.allow_member_invites}
                disabled={updateFirmSettingsMutation.isPending}
                onChange={(allow_member_invites) =>
                  updateFirmSettingsMutation.mutate({ allow_member_invites })
                }
              />
              <ToggleSetting
                label="Require motion approval"
                description="Route generated motions through approval before firm-wide reuse."
                checked={firmSettingsQuery.data.motion_approval_required}
                disabled={updateFirmSettingsMutation.isPending}
                onChange={(motion_approval_required) =>
                  updateFirmSettingsMutation.mutate({ motion_approval_required })
                }
              />
              <ToggleSetting
                label="Enable chat rooms"
                description="Allow firm-scoped collaboration rooms for cases and motions."
                checked={firmSettingsQuery.data.enable_chat_rooms}
                disabled={updateFirmSettingsMutation.isPending}
                onChange={(enable_chat_rooms) =>
                  updateFirmSettingsMutation.mutate({ enable_chat_rooms })
                }
              />
              <ToggleSetting
                label="Enable motion comments"
                description="Allow threaded comments on motion drafts and review items."
                checked={firmSettingsQuery.data.enable_motion_comments}
                disabled={updateFirmSettingsMutation.isPending}
                onChange={(enable_motion_comments) =>
                  updateFirmSettingsMutation.mutate({ enable_motion_comments })
                }
              />
              <div className="rounded-xl border border-border bg-surface-muted px-4 py-3">
                <p className="text-sm font-semibold text-text">Allowed email domain</p>
                <p className="mt-1 text-xs leading-5 text-muted">
                  Displayed from backend firm settings. Domain changes affect who can join the
                  firm, so this should stay controlled until product confirms the flow.
                </p>
                <p className="mt-2 text-sm font-medium text-text-secondary">
                  {firmSettingsQuery.data.allowed_domain}
                </p>
              </div>
            </div>
          ) : (
            <p className="mt-5 rounded-xl border border-dashed border-border px-4 py-6 text-sm text-muted">
              Firm settings are unavailable.
            </p>
          )}
        </div>
      </section>
    </div>
  );
};
