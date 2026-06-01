import React, { useState } from 'react';
import { FiSettings, FiUsers } from 'react-icons/fi';
import { authKeys } from '@/features/auth/queries';
import { AnalyticsBodySkeleton } from '@/features/analytics/components/AnalyticsSkeleton';
import { queryClient } from '@/lib/queryClient';
import type { User } from '@/types';
import { useBillingCostDrivers } from '../hooks/useBillingOverview';
import type { BillingCostDriversGroup, BillingUserRole, CostDriver } from '../types/billing.types';
import { BillingCard } from './BillingCard';

const rolePillClassNames: Record<BillingUserRole, string> = {
  admin: 'bg-app-warning-soft text-app-warning-text',
  firm_owner: 'bg-app-accent-soft text-app-accent-text',
  member: 'bg-[rgba(226,232,240,0.72)] text-text-secondary dark:bg-surface-muted',
};

const CostDriverRow = ({
  isCurrentUser = false,
  item,
}: {
  isCurrentUser?: boolean;
  item: CostDriver;
}) => (
  <div>
    <div className="flex items-start justify-between gap-3 text-sm">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <p className="truncate font-semibold text-text-secondary">{item.name}</p>
        {item.role ? (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] ${rolePillClassNames[item.role]}`}
          >
            {item.role}
          </span>
        ) : null}
        {isCurrentUser ? (
          <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-muted">
            (you)
          </span>
        ) : null}
      </div>
      <span className="shrink-0 font-semibold text-text">{item.amountLabel}</span>
    </div>
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
      <div className="h-full rounded-full bg-app-accent" style={{ width: `${item.percentage}%` }} />
    </div>
  </div>
);

export const CostDriversCard: React.FC = () => {
  const [activeTab, setActiveTab] = useState<BillingCostDriversGroup>('user');
  const user = queryClient.getQueryData<User | null>(authKeys.currentUser()) ?? null;
  const { data: items = [], error, isFetching, isLoading } = useBillingCostDrivers(activeTab);
  const currentUserName = [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim();
  const showSkeleton = isLoading || isFetching;

  const getIsCurrentUser = (item: CostDriver) =>
    Boolean(
      item.id === user?.id ||
        (item.email && user?.email && item.email.toLowerCase() === user.email.toLowerCase()) ||
        (currentUserName && item.name.toLowerCase() === currentUserName.toLowerCase())
    );

  return (
    <BillingCard className="flex h-full min-h-[430px] flex-col">
      <div className="px-5 pb-2 pt-5">
        <h2 className="font-poppins text-lg font-semibold text-text-secondary">Top cost drivers</h2>
        <p className="mt-1 text-sm text-muted">Highest spend by user and workflow this cycle.</p>
      </div>
      <div className="flex min-h-0 flex-1 flex-col p-5">
        <div
          className="grid w-full grid-cols-2 rounded-full bg-[rgba(226,232,240,0.55)] p-1 dark:bg-surface-muted/90"
          role="tablist"
          aria-label="Cost driver view"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'user'}
            className={`inline-flex h-9 items-center justify-center gap-2 rounded-full text-sm font-semibold transition ${
              activeTab === 'user'
                ? 'bg-surface text-app-accent-text'
                : 'text-text-secondary hover:text-text'
            }`}
            onClick={() => setActiveTab('user')}
          >
            <FiUsers className="h-4 w-4" />
            By User
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'workflow'}
            className={`inline-flex h-9 items-center justify-center gap-2 rounded-full text-sm font-semibold transition ${
              activeTab === 'workflow'
                ? 'bg-surface text-app-accent-text'
                : 'text-text-secondary hover:text-text'
            }`}
            onClick={() => setActiveTab('workflow')}
          >
            <FiSettings className="h-4 w-4" />
            By Workflow
          </button>
        </div>

        <div className="mt-5 min-h-0 flex-1 space-y-4 overflow-y-auto pr-1" role="tabpanel">
          {error ? (
            <div className="rounded-xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
              Failed to load cost drivers: {error.message}
            </div>
          ) : showSkeleton ? (
            <AnalyticsBodySkeleton className="h-64" />
          ) : items.length ? (
            items.map((item) => (
              <CostDriverRow
                key={item.id ?? item.name}
                isCurrentUser={activeTab === 'user' && getIsCurrentUser(item)}
                item={item}
              />
            ))
          ) : (
            <div className="flex h-64 items-center justify-center rounded-xl border border-border/70 bg-surface-muted/60 px-4 text-center">
              <p className="text-sm text-muted">No cost driver data for this billing cycle.</p>
            </div>
          )}
        </div>
      </div>
    </BillingCard>
  );
};
