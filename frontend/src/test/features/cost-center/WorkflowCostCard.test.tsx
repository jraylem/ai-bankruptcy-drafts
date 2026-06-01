import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WorkflowCostCard } from '@/features/cost-center/WorkflowCostCard';
import type { WorkflowMetricEntry } from '@/types/costs';

const baseProps = {
  title: 'Chat',
  icon: <span data-testid="icon" />,
  includesHint: 'Includes chat + guardrail calls.',
};

const sessionEntry = (
  count: number,
  avg: number
): WorkflowMetricEntry => ({ unit: 'session', count, avg_cost_usd: avg });

describe('<WorkflowCostCard />', () => {
  it('renders total + per-unit breakdown when count > 0', () => {
    render(
      <WorkflowCostCard
        {...baseProps}
        totalUsd={100}
        metrics={[sessionEntry(4, 25)]}
      />
    );
    expect(screen.getByText('Chat')).toBeInTheDocument();
    expect(screen.getByText('$100.00')).toBeInTheDocument();
    expect(screen.getByText('$25.00')).toBeInTheDocument();
    expect(screen.getByText('avg / session')).toBeInTheDocument();
    expect(screen.getByText('4 sessions')).toBeInTheDocument();
  });

  it('renders multiple breakdown lines (chat: session + message + case)', () => {
    render(
      <WorkflowCostCard
        {...baseProps}
        totalUsd={100}
        metrics={[
          { unit: 'session', count: 4, avg_cost_usd: 25 },
          { unit: 'message', count: 20, avg_cost_usd: 5 },
          { unit: 'case', count: 2, avg_cost_usd: 50 },
        ]}
      />
    );
    expect(screen.getByText('avg / session')).toBeInTheDocument();
    expect(screen.getByText('avg / message')).toBeInTheDocument();
    expect(screen.getByText('avg / case')).toBeInTheDocument();
    expect(screen.getByText('4 sessions')).toBeInTheDocument();
    expect(screen.getByText('20 messages')).toBeInTheDocument();
    expect(screen.getByText('2 cases')).toBeInTheDocument();
  });

  it('singularizes unit at count 1', () => {
    render(
      <WorkflowCostCard
        {...baseProps}
        totalUsd={50}
        metrics={[{ unit: 'case', count: 1, avg_cost_usd: 50 }]}
      />
    );
    expect(screen.getByText('1 case')).toBeInTheDocument();
  });

  it('shows empty hint when all metrics have count 0', () => {
    render(
      <WorkflowCostCard
        {...baseProps}
        totalUsd={0}
        metrics={[sessionEntry(0, 0), { unit: 'message', count: 0, avg_cost_usd: 0 }]}
      />
    );
    expect(screen.getByText('$0.00')).toBeInTheDocument();
    expect(screen.getByText('No sessions yet')).toBeInTheDocument();
    expect(screen.queryByText(/avg \//)).toBeNull();
  });

  it('uses thousands formatting for large totals', () => {
    render(
      <WorkflowCostCard
        {...baseProps}
        totalUsd={12500}
        metrics={[sessionEntry(5, 2500)]}
      />
    );
    expect(screen.getByText('$12,500')).toBeInTheDocument();
  });

  it('renders the pleadings shape (run + case)', () => {
    render(
      <WorkflowCostCard
        title="Pleadings"
        icon={<span />}
        includesHint=""
        totalUsd={180}
        metrics={[
          { unit: 'run', count: 3, avg_cost_usd: 60 },
          { unit: 'case', count: 2, avg_cost_usd: 90 },
        ]}
      />
    );
    expect(screen.getByText('avg / run')).toBeInTheDocument();
    expect(screen.getByText('avg / case')).toBeInTheDocument();
    expect(screen.getByText('3 runs')).toBeInTheDocument();
    expect(screen.getByText('2 cases')).toBeInTheDocument();
  });
});
