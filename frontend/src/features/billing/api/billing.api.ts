import { API_ENDPOINTS } from '@/constants';
import apiService from '@/services/api';
import { BILLING_USAGE_CATEGORY_METADATA } from '../billing.data';
import type {
  BillingCostDriversGroup,
  BillingCheckoutRequest,
  BillingCheckoutResponse,
  BillingHistoryItem,
  BillingOverview,
  BillingPaymentMethod,
  BillingPortalResponse,
  BillingSubscription,
  BillingUsageCategory,
  BillingUsageCategoryId,
  CostDriver,
} from '../types/billing.types';

type BillingOverviewResponse = {
  base_price_cents: number;
  billing_period: string;
  current_period_end: string | null;
  current_period_start: string | null;
  meter_prices: Array<{
    key: string;
    label: string;
    price_cents: number;
    unit_label: string;
  }>;
  plan_name: string | null;
  stripe_customer_id: string | null;
  subscription_status: BillingSubscription['status'];
};

type UsageBreakdownResponse = {
  billing_period_end: string;
  billing_period_start: string;
  items: Array<{
    current_charge_cents: number;
    key: string;
    label: string;
    rate_cents: number;
    trend_pct: number;
    unit_label: string;
    units_used: number;
  }>;
  mtd_total_cents: number;
  projected_cents: number;
};

type PaymentMethodResponse = {
  brand: string | null;
  exp_month: number | null;
  exp_year: number | null;
  funding: string | null;
  has_payment_method: boolean;
  last4: string | null;
};

type InvoicesResponse = {
  items: Array<{
    amount_cents: number;
    billing_period: string | null;
    invoice_number: string;
    invoice_pdf: string | null;
    invoice_url: string | null;
    paid_at: string | null;
    status: BillingHistoryItem['status'];
    stripe_invoice_id: string;
  }>;
};

type CostDriversResponse =
  | {
      by: 'user';
      items: Array<{
        email: string | null;
        label: string;
        role: string;
        role_display: string;
        total_cents: number;
        user_id: string;
      }>;
    }
  | {
      by: 'workflow';
      items: Array<{
        key: string;
        label: string;
        total_cents: number;
      }>;
    };

const formatCurrencyFromCents = (cents: number | null | undefined) =>
  new Intl.NumberFormat('en-US', {
    currency: 'USD',
    style: 'currency',
  }).format((cents ?? 0) / 100);

const formatBillingDate = (value: string | null | undefined) => {
  if (!value) return 'Pending';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'Pending';
  return parsed.toLocaleDateString(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

const normalizeUsageCategoryId = (key: string): BillingUsageCategoryId | null => {
  if (
    key === 'chat' ||
    key === 'ingestion' ||
    key === 'agt_composition' ||
    key === 'pleading_generation'
  ) {
    return key;
  }
  return null;
};

const buildUsageCategories = (
  overview: BillingOverviewResponse,
  usage: UsageBreakdownResponse | null
): BillingUsageCategory[] => {
  const usageItemsByKey = new Map(usage?.items.map((item) => [item.key, item]) ?? []);
  return overview.meter_prices.flatMap((meter) => {
    const id = normalizeUsageCategoryId(meter.key);
    if (!id) return [];

    const metadata = BILLING_USAGE_CATEGORY_METADATA[id];
    const usageItem = usageItemsByKey.get(meter.key);
    const unitLabel = meter.unit_label || usageItem?.unit_label || 'units';
    const rateCents = usageItem?.rate_cents ?? meter.price_cents;

    return [
      {
        id,
        label: meter.label || usageItem?.label || meter.key,
        description: metadata.description,
        rateLabel: `${formatCurrencyFromCents(rateCents)} / ${unitLabel.replace(/s$/, '')}`,
        unitLabel,
        usageLabel: `${(usageItem?.units_used ?? 0).toLocaleString()} ${unitLabel}`,
        chargeLabel: formatCurrencyFromCents(usageItem?.current_charge_cents),
        icon: metadata.icon,
        trendPct: usageItem?.trend_pct ?? 0,
      },
    ];
  });
};

const buildPaymentMethod = (paymentMethod: PaymentMethodResponse | null): BillingPaymentMethod | null => {
  if (!paymentMethod?.has_payment_method || !paymentMethod.brand || !paymentMethod.last4) {
    return null;
  }

  const brand = paymentMethod.brand[0].toUpperCase() + paymentMethod.brand.slice(1);
  const expiryLabel =
    paymentMethod.exp_month && paymentMethod.exp_year
      ? `Expires ${String(paymentMethod.exp_month).padStart(2, '0')}/${String(paymentMethod.exp_year).slice(-2)}`
      : 'Expiration date unavailable';

  return {
    brand,
    expiryLabel,
    label: `${brand} ending in ${paymentMethod.last4}`,
    last4: paymentMethod.last4,
    status: 'active',
  };
};

const buildBillingHistory = (invoices: InvoicesResponse | null): BillingHistoryItem[] =>
  invoices?.items.map((invoice) => ({
    amountLabel: formatCurrencyFromCents(invoice.amount_cents),
    dateLabel: formatBillingDate(invoice.paid_at),
    id: invoice.invoice_number || invoice.stripe_invoice_id,
    invoicePdfUrl: invoice.invoice_pdf,
    invoiceUrl: invoice.invoice_url,
    periodLabel: invoice.billing_period ?? 'Billing period unavailable',
    status: invoice.status,
  })) ?? [];

const toCostDriverPercentage = (amountCents: number, totalCents: number) => {
  if (totalCents <= 0) return 0;
  return Math.max(1, Math.round((amountCents / totalCents) * 100));
};

const normalizeCostDriverRole = (role: string): CostDriver['role'] => {
  if (role === 'firm_owner' || role === 'admin' || role === 'member') {
    return role;
  }
  return 'member';
};

const ensureData = <T>(response: { data?: T; error?: string }, fallbackMessage: string): T => {
  if (response.error) {
    throw new Error(response.error);
  }
  if (response.data === undefined) {
    throw new Error(fallbackMessage);
  }
  return response.data;
};

export const createBillingCheckoutSession = async (
  checkoutRequest: BillingCheckoutRequest,
): Promise<BillingCheckoutResponse> => {
  const response = await apiService.post<BillingCheckoutResponse>(
    API_ENDPOINTS.BILLING.CHECKOUT,
    checkoutRequest,
  );

  if (response.error) {
    throw new Error(response.error);
  }

  if (!response.data?.checkout_url) {
    throw new Error('Checkout URL was not returned.');
  }

  return response.data;
};

export const fetchBillingPortal = async (): Promise<BillingPortalResponse> => {
  const response = await apiService.get<BillingPortalResponse>(API_ENDPOINTS.BILLING.PORTAL);

  if (response.error) {
    throw new Error(response.error);
  }

  if (!response.data?.portal_url) {
    throw new Error('Billing portal URL was not returned.');
  }

  return response.data;
};

export const fetchBillingSubscription = async (): Promise<BillingSubscription | null> => {
  const response = await apiService.get<BillingSubscription | null>(
    API_ENDPOINTS.BILLING.SUBSCRIPTION,
  );

  if (response.error) {
    throw new Error(response.error);
  }

  return response.data ?? null;
};

export const fetchBillingOverview = async (): Promise<BillingOverview> => {
  const [overview, usage, paymentMethod, invoices, subscription] = await Promise.all([
    apiService
      .get<BillingOverviewResponse>(API_ENDPOINTS.BILLING.OVERVIEW)
      .then((response) => ensureData(response, 'Billing overview was not returned.')),
    apiService
      .get<UsageBreakdownResponse>(API_ENDPOINTS.BILLING.USAGE_BREAKDOWN)
      .then((response) => ensureData(response, 'Billing usage was not returned.')),
    apiService
      .get<PaymentMethodResponse>(API_ENDPOINTS.BILLING.PAYMENT_METHOD)
      .then((response) => ensureData(response, 'Payment method was not returned.')),
    apiService
      .get<InvoicesResponse>(API_ENDPOINTS.BILLING.INVOICES)
      .then((response) => ensureData(response, 'Invoices were not returned.')),
    fetchBillingSubscription(),
  ]);
  const billingHistory = buildBillingHistory(invoices);

  return {
    billingModel: 'pay_as_you_go',
    billingHistory,
    paymentMethod: buildPaymentMethod(paymentMethod),
    summary: {
      lastInvoiceLabel: billingHistory[0]?.amountLabel ?? '$0.00',
      monthToDateLabel: formatCurrencyFromCents(usage?.mtd_total_cents),
      nextInvoiceLabel: formatBillingDate(overview.current_period_end),
      projectedLabel: formatCurrencyFromCents(usage?.projected_cents),
    },
    subscription,
    usageCategories: buildUsageCategories(overview, usage),
  };
};

export const fetchBillingCostDrivers = async (
  group: BillingCostDriversGroup,
): Promise<CostDriver[]> => {
  const response = await apiService.get<CostDriversResponse>(API_ENDPOINTS.BILLING.COST_DRIVERS, {
    params: { by: group },
  });
  const data = ensureData(response, 'Billing cost drivers were not returned.');
  const totalCents = data.items.reduce((sum, item) => sum + item.total_cents, 0);

  if (data.by === 'user') {
    return data.items.map((item) => ({
      amountLabel: formatCurrencyFromCents(item.total_cents),
      email: item.email ?? undefined,
      id: item.user_id,
      name: item.label,
      percentage: toCostDriverPercentage(item.total_cents, totalCents),
      role: normalizeCostDriverRole(item.role),
    }));
  }

  return data.items.map((item) => ({
    amountLabel: formatCurrencyFromCents(item.total_cents),
    id: item.key,
    name: item.label,
    percentage: toCostDriverPercentage(item.total_cents, totalCents),
  }));
};
