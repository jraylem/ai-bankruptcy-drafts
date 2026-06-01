import React from 'react';
import { FiCreditCard } from 'react-icons/fi';
import type { BillingOverview } from '../types/billing.types';
import { BillingButton } from './BillingButton';
import { BillingCard } from './BillingCard';

interface PaymentMethodCardProps {
  onAction: () => void;
  overview: BillingOverview | undefined;
}

export const PaymentMethodCard: React.FC<PaymentMethodCardProps> = ({ onAction, overview }) => (
  <BillingCard>
    <div className="px-5 pb-2 pt-5">
      <h2 className="font-poppins text-lg font-semibold text-text-secondary">Payment method</h2>
      <p className="mt-1 text-sm text-muted">Default payment method for firm billing.</p>
    </div>
    <div className="space-y-4 p-5">
      <div className="flex items-start justify-between gap-4 rounded-xl bg-[rgba(241,245,249,0.72)] p-4 dark:bg-surface-muted/80">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface text-text-secondary">
            <FiCreditCard className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-text-secondary">
                {overview?.paymentMethod?.label ?? 'Payment method unavailable'}
              </p>
              {overview?.paymentMethod ? (
                <span className="inline-flex rounded-full bg-app-success-soft px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-app-success-text">
                  Default
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-xs leading-5 text-muted">
              {overview?.paymentMethod?.expiryLabel ?? 'Expiration date unavailable'}
            </p>
          </div>
        </div>
        <BillingButton
          className="h-[30px] shrink-0 gap-1.5 text-xs"
          onClick={onAction}
          variant="accent"
        >
          Change
        </BillingButton>
      </div>
    </div>
  </BillingCard>
);
