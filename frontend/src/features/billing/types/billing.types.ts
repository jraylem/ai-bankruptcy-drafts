import type { IconType } from 'react-icons';

export type BillingModel = 'pay_as_you_go';

export type BillingSubscriptionStatus =
  | 'active'
  | 'trialing'
  | 'past_due'
  | 'canceled'
  | 'incomplete';

export interface BillingSubscription {
  firm_id: string;
  stripe_subscription_id: string | null;
  stripe_customer_id?: string | null;
  status: BillingSubscriptionStatus | null;
  current_period_start?: string | null;
  current_period_end: string | null;
  canceled_at?: string | null;
}

export interface BillingCheckoutRequest {
  cancel_url?: string;
  success_url?: string;
}

export interface BillingCheckoutResponse {
  checkout_url: string;
}

export interface BillingPortalResponse {
  portal_url: string;
}

export type BillingUsageCategoryId =
  | 'chat'
  | 'ingestion'
  | 'agt_composition'
  | 'pleading_generation';

export interface BillingUsageCategory {
  id: BillingUsageCategoryId;
  label: string;
  description: string;
  rateLabel: string;
  unitLabel: string;
  usageLabel: string;
  chargeLabel: string;
  icon: IconType;
  trendPct: number;
}

export interface BillingPaymentMethod {
  brand: string;
  expiryLabel: string;
  label: string;
  last4: string;
  status: 'active' | 'not_connected';
}

export interface BillingHistoryItem {
  amountLabel: string;
  dateLabel: string;
  id: string;
  invoicePdfUrl?: string | null;
  invoiceUrl?: string | null;
  periodLabel: string;
  status: 'draft' | 'open' | 'paid' | 'uncollectible' | 'void';
}

export interface BillingSummary {
  lastInvoiceLabel: string;
  monthToDateLabel: string;
  nextInvoiceLabel: string;
  projectedLabel: string;
}

export interface BillingOverview {
  billingModel: BillingModel;
  billingHistory: BillingHistoryItem[];
  paymentMethod: BillingPaymentMethod | null;
  subscription: BillingSubscription | null;
  summary: BillingSummary;
  usageCategories: BillingUsageCategory[];
}

export type BillingUserRole = 'admin' | 'firm_owner' | 'member';

export type CostDriver = {
  amountLabel: string;
  email?: string;
  id?: string;
  name: string;
  percentage: number;
  role?: BillingUserRole;
};

export type BillingCostDriversGroup = 'user' | 'workflow';
