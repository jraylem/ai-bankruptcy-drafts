import React from 'react';
import { FiShield, FiUsers } from 'react-icons/fi';
import { BillingButton } from './BillingButton';
import { BillingCard } from './BillingCard';

interface UsageControlsCardProps {
  onAction: () => void;
}

export const UsageControlsCard: React.FC<UsageControlsCardProps> = ({ onAction }) => (
  <BillingCard>
    <div className="px-5 pb-2 pt-5">
      <h2 className="font-poppins text-lg font-semibold text-text-secondary">Usage controls</h2>
      <p className="mt-1 text-sm text-muted">Spending controls and user-level usage caps.</p>
    </div>
    <div className="space-y-4 p-5">
      <div className="rounded-xl bg-[rgba(241,245,249,0.72)] p-4 dark:bg-surface-muted/80">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface text-text-secondary">
              <FiShield className="h-4 w-4" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-text-secondary">Firm-wide spend alert</p>
                <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-muted">
                  Not set
                </span>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted">
                Get notified when monthly spend exceeds a threshold.
              </p>
            </div>
          </div>
          <BillingButton className="h-[30px] shrink-0 text-xs" onClick={onAction} variant="accent">
            Configure
          </BillingButton>
        </div>
      </div>

      <div className="rounded-xl bg-[rgba(241,245,249,0.72)] p-4 dark:bg-surface-muted/80">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface text-text-secondary">
              <FiUsers className="h-4 w-4" />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-text-secondary">Per-user usage limits</p>
                <span className="shrink-0 rounded-full bg-app-accent-soft px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-app-accent-text">
                  Planned
                </span>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted">
                Individual spend or usage caps will be managed in team settings.
              </p>
            </div>
          </div>
          <BillingButton
            className="h-[30px] shrink-0 gap-1.5 text-xs"
            onClick={onAction}
            variant="primary"
          >
            Manage
          </BillingButton>
        </div>
      </div>
    </div>
  </BillingCard>
);
