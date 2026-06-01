import React from 'react';
import { FiDownload, FiExternalLink } from 'react-icons/fi';
import type { BillingHistoryItem } from '../types/billing.types';
import { BillingButton } from './BillingButton';
import { BillingCard } from './BillingCard';

const InvoiceStatus = ({ status }: { status: BillingHistoryItem['status'] }) => (
  <span className="inline-flex rounded-full bg-app-success-soft px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-app-success-text">
    {status}
  </span>
);

interface InvoicesCardProps {
  billingHistory: BillingHistoryItem[];
  onAction: () => void;
}

export const InvoicesCard: React.FC<InvoicesCardProps> = ({ billingHistory, onAction }) => (
  <BillingCard>
    <div className="px-5 pb-4 pt-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-poppins text-lg font-semibold text-text-secondary">
            Recent invoices
          </h2>
          <p className="mt-1 text-sm text-muted">Past invoices and payment history.</p>
        </div>
        <BillingButton onClick={onAction} variant="secondary">
          <FiExternalLink className="h-4 w-4" />
          View all in Stripe
        </BillingButton>
      </div>
    </div>
    <div className="px-5 pb-5">
      <div className="overflow-x-auto rounded-2xl border border-border/70">
        <table className="min-w-full table-fixed border-collapse">
          <thead className="bg-surface-muted/75">
            <tr>
              <th className="w-[24%] px-4 py-3 text-left whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Invoice date
                </span>
              </th>
              <th className="w-[28%] px-4 py-3 text-left whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Billing period
                </span>
              </th>
              <th className="w-[16%] px-4 py-3 text-left whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Amount
                </span>
              </th>
              <th className="w-[16%] px-4 py-3 text-left whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Status
                </span>
              </th>
              <th className="w-[16%] px-4 py-3 text-left whitespace-nowrap">
                <span className="inline-flex items-center whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
                  Actions
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {billingHistory.length ? (
              billingHistory.map((item) => (
                <tr
                  key={item.id}
                  className="border-t border-border/70 transition-colors hover:bg-activity-row-hover"
                >
                  <td className="px-4 py-3">
                    <p className="text-sm font-semibold text-text-secondary">{item.dateLabel}</p>
                    <p className="mt-1 text-xs text-muted">{item.id}</p>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted">{item.periodLabel}</td>
                  <td className="px-4 py-3 text-sm font-semibold text-text">{item.amountLabel}</td>
                  <td className="px-4 py-3">
                    <InvoiceStatus status={item.status} />
                  </td>
                  <td className="px-4 py-3">
                    <BillingButton className="h-[30px]" onClick={onAction} variant="ghost">
                      <FiDownload className="h-4 w-4" />
                      Download
                    </BillingButton>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-4 py-8 text-center text-sm text-muted" colSpan={5}>
                  Invoice history will appear when billing invoices are available.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  </BillingCard>
);
