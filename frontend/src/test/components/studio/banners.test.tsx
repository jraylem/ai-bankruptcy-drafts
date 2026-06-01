import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useStudioStore } from '@/stores/useStudioStore';
import { ActionErrorCard } from '@/components/studio/banners/ActionErrorCard';
import { AwaitingInputBanner } from '@/components/studio/banners/AwaitingInputBanner';
import { DryRunResultBanner } from '@/components/studio/banners/DryRunResultBanner';

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

const baseStoreState = {
  selectedCaseId: null,
  selectedTemplateId: null,
  cases: [],
  templates: [],
  connectors: [],
  referenceData: [],
  templateSpec: [],
  agentConfig: null,
  dryRunResult: null,
  dryRunAwaiting: null,
  draftResult: null,
  draftAwaiting: null,
  flowState: 'new' as const,
  isDirty: false,
  actionError: null,
  error: null,
  templateDocUrl: null,
  originalDocUrl: null,
};

beforeEach(() => useStudioStore.setState(baseStoreState));
afterEach(() => useStudioStore.setState(baseStoreState));

describe('<ActionErrorCard />', () => {
  it('renders nothing when there is no actionError', () => {
    const { container } = render(<ActionErrorCard onJumpToVariable={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders message + validation errors when actionError is set', () => {
    useStudioStore.setState({
      actionError: {
        kind: 'dry-run',
        message: 'Cannot run dry run — 1 variable needs attention',
        validationErrors: ["Variable 'foo' is missing source"],
      },
    });
    render(<ActionErrorCard onJumpToVariable={() => {}} />);
    expect(screen.getByText(/Cannot run dry run/)).toBeInTheDocument();
    expect(screen.getByText(/foo' is missing source/)).toBeInTheDocument();
  });

  it('clicking the validation entry calls onJumpToVariable with the parsed name', () => {
    const onJump = vi.fn();
    useStudioStore.setState({
      actionError: {
        kind: 'dry-run',
        message: 'Issues',
        validationErrors: ["Variable 'debtor_name' is missing source"],
      },
    });
    render(<ActionErrorCard onJumpToVariable={onJump} />);
    fireEvent.click(screen.getByRole('button', { name: /debtor_name/ }));
    expect(onJump).toHaveBeenCalledWith('debtor_name');
  });

  it('renders entry as plain text (not a button) when no variable name is parseable', () => {
    useStudioStore.setState({
      actionError: {
        kind: 'save',
        message: 'Issues',
        validationErrors: ['Some plain error without a quoted name'],
      },
    });
    render(<ActionErrorCard onJumpToVariable={() => {}} />);
    expect(screen.getByText(/Some plain error/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Some plain error/ })).toBeNull();
  });

  it('Retry button calls retryLastAction', () => {
    const retryLastAction = vi.fn().mockResolvedValue({ success: true });
    useStudioStore.setState({
      actionError: { kind: 'dry-run', message: 'failed' },
      retryLastAction,
    });
    render(<ActionErrorCard onJumpToVariable={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Retry/ }));
    expect(retryLastAction).toHaveBeenCalled();
  });

  it('Dismiss button calls clearActionError', () => {
    const clearActionError = vi.fn();
    useStudioStore.setState({
      actionError: { kind: 'dry-run', message: 'failed' },
      clearActionError,
    });
    render(<ActionErrorCard onJumpToVariable={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Dismiss/ }));
    expect(clearActionError).toHaveBeenCalled();
  });
});

describe('<AwaitingInputBanner />', () => {
  it('renders dry-run label + pending count + case name', () => {
    render(
      <AwaitingInputBanner
        kind="dry-run"
        caseName="Doe, John"
        pendingCount={3}
        onContinue={() => {}}
        onDiscard={() => {}}
      />,
    );
    expect(screen.getByText(/Dry run paused/)).toBeInTheDocument();
    expect(screen.getByText(/3 inputs required/)).toBeInTheDocument();
    expect(screen.getByText(/for Doe, John/)).toBeInTheDocument();
  });

  it('renders draft label + correct singular for 1 input + omits case clause when null', () => {
    render(
      <AwaitingInputBanner
        kind="draft"
        caseName={null}
        pendingCount={1}
        onContinue={() => {}}
        onDiscard={() => {}}
      />,
    );
    expect(screen.getByText(/Draft paused/)).toBeInTheDocument();
    expect(screen.getByText(/1 input required/)).toBeInTheDocument();
    expect(screen.queryByText(/ for /)).toBeNull();
  });

  it('Continue + Discard buttons call their handlers', () => {
    const onContinue = vi.fn();
    const onDiscard = vi.fn();
    render(
      <AwaitingInputBanner
        kind="draft"
        caseName="Smith"
        pendingCount={2}
        onContinue={onContinue}
        onDiscard={onDiscard}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Continue/ }));
    fireEvent.click(screen.getByRole('button', { name: /Discard/ }));
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onDiscard).toHaveBeenCalledTimes(1);
  });
});

describe('<DryRunResultBanner />', () => {
  it('renders nothing when there is no dryRunResult', () => {
    const { container } = render(<DryRunResultBanner onJumpToVariable={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the success summary when dryRunResult is present', () => {
    useStudioStore.setState({
      dryRunResult: {
        status: 'completed',
        template_id: 't1',
        resolved_values: [],
        generated_doc_url: 'https://r2/x.docx',
        validation: { valid: true, errors: [], warnings: [] },
        can_generate: true,
      },
    });
    render(<DryRunResultBanner onJumpToVariable={() => {}} />);
    expect(screen.getByText(/Dry run/i)).toBeInTheDocument();
  });
});
