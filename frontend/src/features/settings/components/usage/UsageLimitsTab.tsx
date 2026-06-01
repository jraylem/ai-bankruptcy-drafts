import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  FiBarChart2,
  FiCreditCard,
  FiDollarSign,
  FiLayers,
  FiSliders,
  FiUsers,
} from 'react-icons/fi';
import { useAuthSession } from '@/features/auth/queries';
import { useSettingsBillingSummary, useSettingsMembers } from '../../hooks';
import { displayNameFor, normalizeRole } from '../members/settings.helpers';

const UsageLimitCard = ({
  description,
  icon,
  label,
  value,
}: {
  description: string;
  icon: ReactNode;
  label: string;
  value: string;
}) => (
  <div className="rounded-2xl border border-border bg-surface p-4">
    <div className="flex h-full min-h-28 items-start gap-3">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-app-accent-soft text-app-accent-text">
        {icon}
      </span>
      <div className="flex min-w-0 flex-1 flex-col self-stretch">
        <div>
          <p className="text-sm font-semibold text-text">{label}</p>
          <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
        </div>
        <p className="mt-auto pt-3 text-lg font-bold text-text-secondary">{value}</p>
      </div>
    </div>
  </div>
);

const CurrencyInput = ({
  ariaLabel,
  disabled,
  onChange,
  value,
}: {
  ariaLabel: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  value: string;
}) => (
  <label className="relative block w-full sm:w-36">
    <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm font-semibold text-muted">
      $
    </span>
    <input
      type="text"
      inputMode="numeric"
      aria-label={ariaLabel}
      disabled={disabled}
      value={value}
      onChange={(event) => onChange(event.target.value.replace(/\D/g, ''))}
      className="h-10 w-full rounded-xl border border-border bg-surface pl-7 pr-3 text-right text-sm font-semibold text-text-secondary outline-none transition placeholder:text-subtle focus:border-app-accent focus:ring-2 focus:ring-app-accent-soft disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-muted"
    />
  </label>
);

const LimitControl = ({
  canEdit,
  description,
  label,
  onChange,
  value,
}: {
  canEdit: boolean;
  description: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) => (
  <div className="rounded-xl border border-border bg-surface-muted px-4 py-3">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p className="text-sm font-semibold text-text">{label}</p>
        <p className="mt-1 text-xs leading-5 text-muted">{description}</p>
      </div>
      <CurrencyInput
        value={value}
        onChange={onChange}
        disabled={!canEdit}
        ariaLabel={`${label} usage limit`}
      />
    </div>
  </div>
);

const formatCurrencyValue = (value: string) => {
  const amount = Number(value || 0);
  return `$${amount.toLocaleString()}`;
};

const formatStatus = (value?: string | null) => {
  if (!value) return 'Billing status unavailable';
  return `Subscription ${value.replace(/_/g, ' ')}`;
};

export const UsageLimitsTab = () => {
  const { user } = useAuthSession();
  const billingSummaryQuery = useSettingsBillingSummary();
  const membersQuery = useSettingsMembers();
  const activeMembers = useMemo(
    () => (membersQuery.data ?? []).filter((member) => member.is_active),
    [membersQuery.data]
  );
  const canManageUsage = ['admin', 'firm_owner', 'superadmin', 'super_admin'].includes(
    normalizeRole(user?.role)
  );
  const [firmMonthlyBudget, setFirmMonthlyBudget] = useState('2500');
  const [defaultMemberCap, setDefaultMemberCap] = useState('300');
  const [adminCap, setAdminCap] = useState('750');
  const [categoryLimits, setCategoryLimits] = useState({
    chatResearch: '450',
    documentIngestion: '650',
    pleadingGeneration: '1200',
    templateStudio: '200',
  });
  const [userLimits, setUserLimits] = useState<Record<string, string>>({});

  const usageMembers = activeMembers.map((member) => {
    const role = normalizeRole(member.role);
    const defaultCap = role === 'admin' || role === 'firm_owner' ? adminCap : defaultMemberCap;
    return {
      cap: userLimits[member.id] ?? defaultCap,
      email: member.email,
      id: member.id,
      name: displayNameFor(member),
      role,
    };
  });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-text">Usage limits</h2>
        <p className="mt-1 text-sm text-muted">
          Set firm-wide defaults and per-user monthly controls for metered work.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <UsageLimitCard
          icon={<FiDollarSign className="h-4 w-4" />}
          label="Firm-wide monthly budget"
          description="Recommended primary guardrail. Stops surprise spend at the firm level."
          value={formatCurrencyValue(firmMonthlyBudget)}
        />
        <UsageLimitCard
          icon={<FiUsers className="h-4 w-4" />}
          label="Per-user default cap"
          description="Recommended secondary guardrail for regular members."
          value={`${formatCurrencyValue(defaultMemberCap)} / user`}
        />
        <UsageLimitCard
          icon={<FiLayers className="h-4 w-4" />}
          label="Category limits"
          description="Useful for chat, ingestion, template studio, and pleading generation."
          value="4 categories"
        />
      </div>

      <div className="rounded-2xl bg-surface p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-app-accent-soft text-app-accent-text">
              <FiCreditCard className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-text">Billing overview</h3>
              {billingSummaryQuery.isLoading ? (
                <div className="mt-2 h-4 w-64 animate-pulse rounded bg-surface-muted" />
              ) : (
                <p className="text-sm capitalize text-muted">
                  {formatStatus(billingSummaryQuery.data?.subscription_status)}
                </p>
              )}
            </div>
          </div>
          <Link
            to="/billing"
            className="inline-flex h-10 items-center justify-center rounded-lg border border-border px-4 text-sm font-semibold text-text-secondary transition hover:border-app-accent/40 hover:text-app-accent-text"
          >
            Manage billing
          </Link>
        </div>
      </div>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-2xl bg-surface p-5">
          <div className="border-b border-border pb-4">
            <div className="flex items-center gap-2">
              <FiSliders className="h-4 w-4 text-muted" />
              <h3 className="text-lg font-semibold text-text">Monthly guardrails</h3>
            </div>
            <p className="mt-1 text-sm text-muted">
              Defaults shown here keep firm usage predictable across drafting, chat, and ingestion.
            </p>
          </div>
          <div className="mt-5 space-y-3">
            <LimitControl
              canEdit={canManageUsage}
              label="Firm monthly budget"
              description="Total monthly metered spend available to the workspace."
              value={firmMonthlyBudget}
              onChange={setFirmMonthlyBudget}
            />
            <LimitControl
              canEdit={canManageUsage}
              label="Default member cap"
              description={`Applied to ${activeMembers.length} active users unless an individual override exists.`}
              value={defaultMemberCap}
              onChange={setDefaultMemberCap}
            />
            <LimitControl
              canEdit={canManageUsage}
              label="Owner and admin cap"
              description="Higher default for users responsible for review and operations."
              value={adminCap}
              onChange={setAdminCap}
            />
          </div>
        </div>

        <div className="rounded-2xl bg-surface p-5">
          <div className="border-b border-border pb-4">
            <div className="flex items-center gap-2">
              <FiBarChart2 className="h-4 w-4 text-muted" />
              <h3 className="text-lg font-semibold text-text">Category allocation</h3>
            </div>
            <p className="mt-1 text-sm text-muted">
              Category limits provide a clear operating plan before heavier usage begins.
            </p>
          </div>
          <div className="mt-5 space-y-3">
            <LimitControl
              canEdit={canManageUsage}
              label="Pleading generation"
              description="Primary drafting workflow budget."
              value={categoryLimits.pleadingGeneration}
              onChange={(value) =>
                setCategoryLimits((current) => ({ ...current, pleadingGeneration: value }))
              }
            />
            <LimitControl
              canEdit={canManageUsage}
              label="Document ingestion"
              description="PDF parsing, extraction, and case setup budget."
              value={categoryLimits.documentIngestion}
              onChange={(value) =>
                setCategoryLimits((current) => ({ ...current, documentIngestion: value }))
              }
            />
            <LimitControl
              canEdit={canManageUsage}
              label="Chat and research"
              description="Workspace chat, review, and analysis budget."
              value={categoryLimits.chatResearch}
              onChange={(value) =>
                setCategoryLimits((current) => ({ ...current, chatResearch: value }))
              }
            />
            <LimitControl
              canEdit={canManageUsage}
              label="Template studio"
              description="Template composition and dry-run budget."
              value={categoryLimits.templateStudio}
              onChange={(value) =>
                setCategoryLimits((current) => ({ ...current, templateStudio: value }))
              }
            />
          </div>
        </div>
      </section>

      <section className="rounded-2xl bg-surface p-5">
        <div className="border-b border-border pb-4">
          <div className="flex items-center gap-2">
            <FiUsers className="h-4 w-4 text-muted" />
            <h3 className="text-lg font-semibold text-text">Per-user limits</h3>
          </div>
          <p className="mt-1 text-sm text-muted">
            Set monthly dollar caps for individual active users.
          </p>
        </div>
        <div className="mt-5 overflow-x-auto rounded-2xl border border-border/70">
          <table className="min-w-full table-auto border-collapse">
            <thead className="bg-surface-muted/75">
              <tr>
                <th className="px-5 py-3 text-left">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                    User
                  </span>
                </th>
                <th className="px-5 py-3 text-left">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                    Role
                  </span>
                </th>
                <th className="px-5 py-3 text-right">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                    Monthly cap
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {membersQuery.isLoading ? (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-muted" colSpan={3}>
                    Loading users...
                  </td>
                </tr>
              ) : usageMembers.length ? (
                usageMembers.map((member) => (
                  <tr
                    key={member.id}
                    className="border-t border-border/70 transition-colors hover:bg-activity-row-hover"
                  >
                    <td className="px-5 py-3">
                      <p className="font-semibold text-text">{member.name}</p>
                      <p className="text-xs text-muted">{member.email}</p>
                    </td>
                    <td className="px-5 py-3">
                      <span className="inline-flex h-8 items-center rounded-lg bg-surface-muted px-2.5 text-xs font-semibold text-muted">
                        {member.role === 'firm_owner'
                          ? 'Firm owner'
                          : member.role === 'admin'
                            ? 'Admin'
                            : 'Member'}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end">
                        <CurrencyInput
                          ariaLabel={`${member.name} monthly usage limit`}
                          disabled={!canManageUsage}
                          value={member.cap}
                          onChange={(value) =>
                            setUserLimits((current) => ({ ...current, [member.id]: value }))
                          }
                        />
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-muted" colSpan={3}>
                    No active users found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
};
