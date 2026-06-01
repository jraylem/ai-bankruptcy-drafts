import { act, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BillingCancelPage, BillingSuccessPage } from '@/pages/billing/checkout-return';
import type React from 'react';

const { useBillingOverviewMock } = vi.hoisted(() => ({
  useBillingOverviewMock: vi.fn(),
}));

vi.mock('@/components/layout/SidebarLayout', () => ({
  SidebarLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/features/billing/hooks/useBillingOverview', () => ({
  useBillingOverview: (enabled?: boolean) => useBillingOverviewMock(enabled),
}));

const renderReturnPage = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/billing/success" element={<BillingSuccessPage />} />
        <Route path="/billing/cancel" element={<BillingCancelPage />} />
        <Route path="/billing" element={<div>Billing dashboard</div>} />
      </Routes>
    </MemoryRouter>,
  );

describe('<BillingCheckoutReturnPage />', () => {
  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('shows a stable success return page while Stripe confirmation is pending', () => {
    useBillingOverviewMock.mockReturnValue({
      data: { subscription: null },
      isFetching: false,
      refetch: vi.fn(),
    });

    renderReturnPage('/billing/success?session_id=cs_test_123');

    expect(useBillingOverviewMock).toHaveBeenCalledWith(true);
    expect(screen.getByRole('heading', { name: 'Checkout complete' })).toBeInTheDocument();
    expect(screen.getByText(/still waiting for Stripe confirmation/i)).toBeInTheDocument();
    expect(screen.getByText('Checkout session: cs_test_123')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /Redirecting to billing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Refresh status/i })).toBeInTheDocument();
  });

  it('redirects back to billing after the return progress completes', async () => {
    vi.useFakeTimers();
    useBillingOverviewMock.mockReturnValue({
      data: {
        subscription: {
          current_period_end: '2026-06-01T00:00:00+00:00',
          firm_id: 'firm-1',
          status: 'active',
          stripe_subscription_id: 'sub_123',
        },
      },
      isFetching: false,
      refetch: vi.fn(),
    });

    renderReturnPage('/billing/success');

    expect(screen.getByText('Your subscription is active in BKDrafts.')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /Redirecting to billing/i })).toBeInTheDocument();

    for (let tick = 0; tick < 6; tick += 1) {
      await act(async () => {
        vi.advanceTimersByTime(1_000);
      });
    }

    expect(screen.getByText('Billing dashboard')).toBeInTheDocument();
  });

  it('does not fetch billing overview on the cancel return page', () => {
    useBillingOverviewMock.mockReturnValue({
      data: undefined,
      isFetching: false,
      refetch: vi.fn(),
    });

    renderReturnPage('/billing/cancel');

    expect(useBillingOverviewMock).toHaveBeenCalledWith(false);
    expect(screen.getByRole('heading', { name: 'Checkout cancelled' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /Redirecting to billing/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Refresh status/i })).not.toBeInTheDocument();
  });
});
