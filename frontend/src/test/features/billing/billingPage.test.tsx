import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FiMessageSquare } from 'react-icons/fi';
import type { BillingOverview } from '@/features/billing/types/billing.types';
import { BillingPage } from '@/pages/billing';
import type React from 'react';

const { useBillingOverviewMock } = vi.hoisted(() => ({
  useBillingOverviewMock: vi.fn(),
}));

vi.mock('@/components/layout/SidebarLayout', () => ({
  SidebarLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/features/billing/hooks/useBillingOverview', () => ({
  useBillingOverview: () => useBillingOverviewMock(),
}));

const baseOverview: BillingOverview = {
  billingModel: 'pay_as_you_go',
  usageCategories: [
    {
      id: 'chat',
      label: 'Chat',
      description: 'Assistant conversations and case-aware chat interactions.',
      rateLabel: '$0.03 / message',
      unitLabel: 'messages',
      usageLabel: '3,240 messages',
      chargeLabel: '$97.20',
      icon: FiMessageSquare,
      trendPct: 12,
    },
    {
      id: 'ingestion',
      label: 'Ingestion',
      description: 'Document uploads, parsing, and case file indexing.',
      rateLabel: '$0.12 / page',
      unitLabel: 'documents',
      usageLabel: '780 pages',
      chargeLabel: '$93.60',
      icon: FiMessageSquare,
      trendPct: 0,
    },
    {
      id: 'agt_composition',
      label: 'AGT Composition',
      description: 'Agent template composition and workflow configuration.',
      rateLabel: '$6.50 / composition',
      unitLabel: 'compositions',
      usageLabel: '14 compositions',
      chargeLabel: '$91.00',
      icon: FiMessageSquare,
      trendPct: 18,
    },
    {
      id: 'pleading_generation',
      label: 'Pleading Generation',
      description: 'Draft generation for pleadings and related legal documents.',
      rateLabel: '$8.85 / generation',
      unitLabel: 'generations',
      usageLabel: '16 generations',
      chargeLabel: '$141.60',
      icon: FiMessageSquare,
      trendPct: -8,
    },
  ],
  summary: {
    monthToDateLabel: '$312.84',
    projectedLabel: '$486.20',
    lastInvoiceLabel: '$428.75',
    nextInvoiceLabel: 'Jun 1',
  },
  paymentMethod: {
    brand: 'Visa',
    expiryLabel: 'Expires 12/26',
    label: 'Visa ending in 4242',
    last4: '4242',
    status: 'active',
  },
  subscription: null,
  billingHistory: [
    {
      amountLabel: '$428.75',
      dateLabel: '2026-04-30',
      id: 'INV-2026-004',
      periodLabel: 'Apr 2026',
      status: 'paid',
    },
  ],
};

describe('<BillingPage />', () => {
  it('renders the free tier billing state when no subscription exists', () => {
    useBillingOverviewMock.mockReturnValue({ data: baseOverview, error: null, isLoading: false });

    render(<BillingPage />);

    expect(screen.getByRole('heading', { name: 'Billing' })).toBeInTheDocument();
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Pay as you go')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upgrade to pay-as-you-go/i })).toBeInTheDocument();
    expect(screen.getByText('How Pay-as-You-Go Works')).toBeInTheDocument();
    expect(screen.queryByText('Month-to-date spend')).not.toBeInTheDocument();
  });

  // TODO: Re-enable these once the backend billing flow can move the UI out of Free Tier.
  it.skip('renders backend subscription status when available', () => {
    useBillingOverviewMock.mockReturnValue({
      data: {
        ...baseOverview,
        subscription: {
          current_period_end: '2026-06-01T00:00:00+00:00',
          firm_id: 'firm-1',
          status: 'active',
          stripe_subscription_id: 'sub_123',
        },
      },
      error: null,
      isLoading: false,
    });

    render(<BillingPage />);

    expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Current period ends Jun 1, 2026')).toBeInTheDocument();
  });

  it('renders all four planned usage categories', () => {
    useBillingOverviewMock.mockReturnValue({ data: baseOverview, error: null, isLoading: false });

    render(<BillingPage />);

    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('Ingestion')).toBeInTheDocument();
    expect(screen.getByText('AGT Composition')).toBeInTheDocument();
    expect(screen.getByText('Pleading Generation')).toBeInTheDocument();
    expect(screen.getByText('$0.03 / message')).toBeInTheDocument();
    expect(screen.getByText('$8.85 / generation')).toBeInTheDocument();
  });

  it('shows an error state without fallback billing content when billing data fails to load', () => {
    useBillingOverviewMock.mockReturnValue({
      data: undefined,
      error: new Error('Billing failed'),
      isLoading: false,
      isFetching: false,
    });

    render(<BillingPage />);

    expect(screen.getByRole('alert')).toHaveTextContent('Billing data could not be loaded.');
    expect(screen.queryByText('Free Tier Active')).not.toBeInTheDocument();
    expect(screen.queryByText('Month-to-date spend')).not.toBeInTheDocument();
  });
});
