import { useEffect, useState } from 'react';
import {
  FiActivity,
  FiEye,
  FiEyeOff,
  FiLoader,
  FiLock,
  FiMonitor,
  FiShield,
  FiTrash2,
} from 'react-icons/fi';
import {
  useChangeSettingsPassword,
  useFirmActivity,
  useRevokeAllSettingsSessions,
  useRevokeSettingsSession,
  useSettingsSessions,
  useTwoFactorStatus,
} from '../../hooks';
import { AnalyticsTablePaginationFooter } from '@/features/analytics/components/AnalyticsTablePaginationFooter';
import { ANALYTICS_TABLE_PAGE_SIZE_OPTIONS } from '@/features/analytics/utils/common.helpers';

const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString() : 'Unavailable';
const formatAction = (value: string) =>
  value
    .replace(/[._-]/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(' ');

const PasswordField = ({
  autoComplete,
  label,
  onChange,
  placeholder,
  value,
}: {
  autoComplete: string;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) => {
  const [showPassword, setShowPassword] = useState(false);

  return (
    <div>
      <label className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary">
        {label}
      </label>
      <div className="relative">
        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
          <FiLock className="h-4 w-4" />
        </span>
        <input
          type={showPassword ? 'text' : 'password'}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          className="h-11 w-full rounded-xl border border-border bg-surface-muted pl-10 pr-12 text-sm text-text-secondary outline-none transition placeholder:text-subtle focus:border-app-accent focus:ring-2 focus:ring-app-accent-soft"
        />
        <button
          type="button"
          onClick={() => setShowPassword((current) => !current)}
          className="absolute right-2.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition hover:bg-surface hover:text-text-secondary"
          aria-label={showPassword ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          aria-pressed={showPassword}
        >
          {showPassword ? <FiEyeOff className="h-4 w-4" /> : <FiEye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
};

export const SecurityTab = () => {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [activityPage, setActivityPage] = useState(1);
  const [activityPageSize, setActivityPageSize] = useState(10);
  const sessionsQuery = useSettingsSessions();
  const revokeSessionMutation = useRevokeSettingsSession();
  const revokeAllMutation = useRevokeAllSettingsSessions();
  const changePasswordMutation = useChangeSettingsPassword();
  const twoFactorQuery = useTwoFactorStatus();
  const firmActivityQuery = useFirmActivity({
    limit: activityPageSize,
    offset: (activityPage - 1) * activityPageSize,
  });

  const sessions = sessionsQuery.data ?? [];
  const otherSessionsCount = sessions.filter((session) => !session.is_current).length;
  const activityTotalItems = firmActivityQuery.data?.total ?? 0;
  const activityTotalPages = Math.max(1, Math.ceil(activityTotalItems / activityPageSize));

  useEffect(() => {
    if (activityPage > activityTotalPages) {
      setActivityPage(activityTotalPages);
    }
  }, [activityPage, activityTotalPages]);

  return (
    <div className="space-y-6">
      <section className="rounded-2xl bg-surface p-5">
        <h2 className="text-lg font-semibold text-text">Change Password</h2>
        <form
          className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            changePasswordMutation.mutate(
              { currentPassword, newPassword },
              {
                onSuccess: () => {
                  setCurrentPassword('');
                  setNewPassword('');
                },
              }
            );
          }}
        >
          <PasswordField
            label="Current password"
            value={currentPassword}
            onChange={setCurrentPassword}
            placeholder="Current password"
            autoComplete="current-password"
          />
          <PasswordField
            label="New password"
            value={newPassword}
            onChange={setNewPassword}
            placeholder="New password"
            autoComplete="new-password"
          />
          <button
            type="submit"
            disabled={changePasswordMutation.isPending || !currentPassword || !newPassword}
            className="h-11 rounded-lg bg-app-accent px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {changePasswordMutation.isPending ? 'Saving...' : 'Change password'}
          </button>
        </form>
      </section>

      <section className="rounded-2xl bg-surface p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-text">Active sessions</h2>
            <p className="mt-1 text-sm text-muted">
              Manage devices currently signed into your account.
            </p>
          </div>
          <button
            type="button"
            disabled={revokeAllMutation.isPending || otherSessionsCount === 0}
            onClick={() => revokeAllMutation.mutate()}
            className="h-9 rounded-lg border border-border px-3 text-sm font-semibold text-text-secondary disabled:cursor-not-allowed disabled:opacity-60"
          >
            {revokeAllMutation.isPending ? 'Revoking...' : 'Revoke all others'}
          </button>
        </div>

        {sessionsQuery.isLoading ? (
          <div className="mt-4 space-y-2">
            <div className="h-12 animate-pulse rounded-lg bg-surface-muted" />
            <div className="h-12 animate-pulse rounded-lg bg-surface-muted" />
          </div>
        ) : (
          <div className="mt-4 space-y-2">
            {sessions.map((session) => (
              <div
                key={session.id}
                className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-semibold text-text">
                    <FiMonitor className="h-4 w-4 shrink-0 text-muted" />
                    <span className="truncate">{session.user_agent || 'Unknown device'}</span>
                    {session.is_current ? (
                      <span className="rounded-md bg-app-accent-soft px-2 py-0.5 text-[11px] text-app-accent-text">
                        Current
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    {session.ip_address || 'No IP'} • Expires {formatDateTime(session.expires_at)}
                  </p>
                </div>
                {!session.is_current ? (
                  <button
                    type="button"
                    onClick={() => revokeSessionMutation.mutate(session.id)}
                    disabled={
                      revokeSessionMutation.isPending &&
                      revokeSessionMutation.variables === session.id
                    }
                    className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-app-danger-soft hover:text-app-danger-text"
                  >
                    {revokeSessionMutation.isPending &&
                    revokeSessionMutation.variables === session.id ? (
                      <FiLoader className="h-4 w-4 animate-spin" />
                    ) : (
                      <FiTrash2 className="h-4 w-4" />
                    )}
                  </button>
                ) : null}
              </div>
            ))}
            {sessions.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-sm text-muted">
                No active sessions found.
              </p>
            ) : null}
          </div>
        )}
      </section>

      <section className="rounded-2xl bg-surface p-5">
        <div className="flex items-center gap-2">
          <FiShield className="h-4 w-4 text-muted" />
          <h2 className="text-lg font-semibold text-text">Two-factor authentication</h2>
        </div>
        <p className="mt-1 text-sm text-muted">Add another layer of protection to your account.</p>
        <div className="mt-4 rounded-xl border border-dashed border-border bg-surface-muted px-4 py-3 text-sm text-muted">
          {twoFactorQuery.isLoading
            ? 'Loading 2FA status...'
            : '2FA controls are not enabled yet in backend.'}
        </div>
      </section>

      <section className="rounded-2xl bg-surface p-5">
        <div className="flex items-center gap-2">
          <FiActivity className="h-4 w-4 text-muted" />
          <h2 className="text-lg font-semibold text-text">Firm activity</h2>
        </div>
        <p className="mt-1 text-sm text-muted">
          Recent security and settings events from /api/settings/firm/activity.
        </p>
        {firmActivityQuery.isLoading ? (
          <div className="mt-4 space-y-2">
            <div className="h-12 animate-pulse rounded-lg bg-surface-muted" />
            <div className="h-12 animate-pulse rounded-lg bg-surface-muted" />
          </div>
        ) : firmActivityQuery.data?.items.length ? (
          <>
            <div className="mt-4 overflow-hidden rounded-xl border border-border">
              {firmActivityQuery.data.items.map((item) => (
                <div
                  key={item.id}
                  className="flex items-start justify-between gap-4 border-b border-border px-4 py-3 last:border-b-0"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-text">
                      {formatAction(item.action)}
                    </p>
                    <p className="mt-1 truncate text-xs text-muted">
                      {item.actor_email || 'System'}{' '}
                      {item.resource_type ? `• ${item.resource_type}` : ''}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-muted">
                    {formatDateTime(item.created_at)}
                  </span>
                </div>
              ))}
            </div>
            {activityTotalItems > 10 ? (
              <AnalyticsTablePaginationFooter
                page={activityPage}
                totalPages={activityTotalPages}
                pageSize={activityPageSize}
                pageSizeOptions={ANALYTICS_TABLE_PAGE_SIZE_OPTIONS}
                onPageChange={setActivityPage}
                onPageSizeChange={(nextPageSize) => {
                  setActivityPageSize(nextPageSize);
                  setActivityPage(1);
                }}
                className="mt-4"
                keyPrefix="firm-activity-pagination"
              />
            ) : null}
          </>
        ) : (
          <p className="mt-4 rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
            No firm activity yet.
          </p>
        )}
      </section>
    </div>
  );
};
