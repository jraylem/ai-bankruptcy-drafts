import { beforeEach, describe, expect, it, vi } from 'vitest';
import { API_ENDPOINTS } from '@/constants';
import {
  createBillingCheckoutSession,
  fetchBillingCostDrivers,
  fetchBillingOverview,
  fetchBillingPortal,
  fetchBillingSubscription,
} from '@/features/billing/api/billing.api';

const apiService = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  default: apiService,
}));

describe('billing api', () => {
  beforeEach(() => {
    apiService.get.mockReset();
    apiService.post.mockReset();
  });

  it('creates a checkout session from the backend billing endpoint', async () => {
    const checkoutResponse = {
      checkout_url: 'https://checkout.stripe.com/pay/cs_test_123',
    };
    const checkoutRequest = {
      cancel_url: 'https://app.example.com/billing/cancel',
      success_url: 'https://app.example.com/billing/success?session_id={CHECKOUT_SESSION_ID}',
    };
    apiService.post.mockResolvedValue({ data: checkoutResponse });

    await expect(createBillingCheckoutSession(checkoutRequest)).resolves.toEqual(
      checkoutResponse,
    );

    expect(apiService.post).toHaveBeenCalledWith(
      API_ENDPOINTS.BILLING.CHECKOUT,
      checkoutRequest,
    );
  });

  it('fetches a billing portal URL from the backend billing endpoint', async () => {
    const portalResponse = {
      portal_url: 'https://billing.stripe.com/session/test_123',
    };
    apiService.get.mockResolvedValue({ data: portalResponse });

    await expect(fetchBillingPortal()).resolves.toEqual(portalResponse);

    expect(apiService.get).toHaveBeenCalledWith(API_ENDPOINTS.BILLING.PORTAL);
  });

  it('fetches subscription details from the backend billing endpoint', async () => {
    const subscription = {
      current_period_end: '2026-06-01T00:00:00+00:00',
      firm_id: 'firm-1',
      status: 'active',
      stripe_subscription_id: 'sub_123',
    };
    apiService.get.mockResolvedValue({ data: subscription });

    await expect(fetchBillingSubscription()).resolves.toEqual(subscription);

    expect(apiService.get).toHaveBeenCalledWith(API_ENDPOINTS.BILLING.SUBSCRIPTION);
  });

  it('returns null when no subscription exists', async () => {
    apiService.get.mockResolvedValue({ data: null });

    await expect(fetchBillingSubscription()).resolves.toBeNull();
  });

  it('throws backend errors for query error states', async () => {
    apiService.get.mockResolvedValue({ error: 'Billing unavailable' });

    await expect(fetchBillingSubscription()).rejects.toThrow('Billing unavailable');
  });

  it('builds billing overview data from backend billing endpoints', async () => {
    const backendOverview = {
      base_price_cents: 0,
      billing_period: 'monthly',
      current_period_end: '2026-06-01T00:00:00+00:00',
      current_period_start: '2026-05-01T00:00:00+00:00',
      meter_prices: [
        {
          key: 'chat',
          label: 'Chat',
          price_cents: 3,
          unit_label: 'messages',
        },
      ],
      plan_name: 'Usage',
      stripe_customer_id: 'cus_123',
      subscription_status: 'trialing',
    };
    const usage = {
      billing_period_end: '2026-06-01T00:00:00+00:00',
      billing_period_start: '2026-05-01T00:00:00+00:00',
      items: [
        {
          current_charge_cents: 1234,
          key: 'chat',
          label: 'Chat',
          rate_cents: 3,
          trend_pct: 0,
          unit_label: 'messages',
          units_used: 411,
        },
      ],
      mtd_total_cents: 1234,
      projected_cents: 2468,
    };
    const paymentMethod = {
      brand: 'visa',
      exp_month: 12,
      exp_year: 2028,
      funding: 'credit',
      has_payment_method: true,
      last4: '4242',
    };
    const invoices = {
      items: [
        {
          amount_cents: 1234,
          billing_period: 'May 2026',
          invoice_number: 'INV-001',
          invoice_pdf: 'https://stripe.example/invoice.pdf',
          invoice_url: 'https://stripe.example/invoice',
          paid_at: '2026-05-31T00:00:00+00:00',
          status: 'paid',
          stripe_invoice_id: 'in_123',
        },
      ],
    };
    const subscription = {
      current_period_end: '2026-06-01T00:00:00+00:00',
      current_period_start: '2026-05-01T00:00:00+00:00',
      firm_id: 'firm-1',
      status: 'trialing',
      stripe_customer_id: 'cus_123',
      stripe_subscription_id: 'sub_123',
    };
    apiService.get
      .mockResolvedValueOnce({ data: backendOverview })
      .mockResolvedValueOnce({ data: usage })
      .mockResolvedValueOnce({ data: paymentMethod })
      .mockResolvedValueOnce({ data: invoices })
      .mockResolvedValueOnce({ data: subscription });

    const overview = await fetchBillingOverview();

    expect(overview.subscription).toEqual(subscription);
    expect(overview.summary.monthToDateLabel).toBe('$12.34');
    expect(overview.summary.projectedLabel).toBe('$24.68');
    expect(overview.usageCategories[0]).toMatchObject({
      chargeLabel: '$12.34',
      id: 'chat',
      trendPct: 0,
      usageLabel: '411 messages',
    });
    expect(overview.paymentMethod?.label).toBe('Visa ending in 4242');
    expect(overview.billingHistory[0]).toMatchObject({
      amountLabel: '$12.34',
      id: 'INV-001',
    });
  });

  it('fetches billing cost drivers from the backend endpoint', async () => {
    apiService.get.mockResolvedValue({
      data: {
        by: 'workflow',
        items: [
          {
            key: 'pleading_generation',
            label: 'Pleading Generation',
            total_cents: 885,
          },
        ],
      },
    });

    await expect(fetchBillingCostDrivers('workflow')).resolves.toEqual([
      {
        amountLabel: '$8.85',
        id: 'pleading_generation',
        name: 'Pleading Generation',
        percentage: 100,
      },
    ]);

    expect(apiService.get).toHaveBeenCalledWith(API_ENDPOINTS.BILLING.COST_DRIVERS, {
      params: { by: 'workflow' },
    });
  });
});
