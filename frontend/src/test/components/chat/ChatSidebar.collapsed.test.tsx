import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// jsdom doesn't ship matchMedia; ChatSidebar reads it at first render to
// detect mobile-collapsed mode. Stub to a desktop response so the
// component goes through its normal collapsed-by-prop branch.
if (typeof window.matchMedia !== 'function') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

vi.mock('@/features/case-inbox/useCaseInbox', () => ({
  useCaseInbox: () => ({ pendingCount: 0 }),
}));

import { ChatSidebar } from '@/components/chat/ChatSidebar';
import { useCaseChatStore, EMPTY_CASE_CHAT_SLICE } from '@/stores/useCaseChatStore';
import { useStudioStore } from '@/stores/useStudioStore';
import { useWorkspaceSplitStore } from '@/stores/useWorkspaceSplitStore';
import type { CaseResponse } from '@/types/studio';

const makeCase = (overrides: Partial<CaseResponse> = {}): CaseResponse => ({
  id: 'case-default',
  case_name: 'John Doe',
  case_number: '26-10700',
  case_number_original: '26-10700',
  court_district: 'EDPA',
  chapter: 13,
  petition_pdf_url: null,
  case_file_collection: 'cf',
  gmail_collection: 'gm',
  courtdrive_collection: 'cd',
  ...overrides,
});

const baseStudioState = {
  selectedCaseId: null as string | null,
  selectedTemplateId: null,
  cases: [] as CaseResponse[],
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

function seedChatSlice(caseId: string, overrides: Partial<{
  isStreaming: boolean;
  hasUnread: boolean;
}>): void {
  useCaseChatStore.setState((state) => ({
    byCase: {
      ...state.byCase,
      [caseId]: {
        ...EMPTY_CASE_CHAT_SLICE,
        ...overrides,
      },
    },
  }));
}

function renderCollapsed(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <ChatSidebar isCollapsed onToggleCollapse={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useStudioStore.setState(baseStudioState);
  useCaseChatStore.setState({ byCase: {} });
  useWorkspaceSplitStore.setState({
    secondaryCaseId: null,
    focusedPane: 'primary',
  });
});

afterEach(() => {
  useStudioStore.setState(baseStudioState);
  useCaseChatStore.setState({ byCase: {} });
});

describe('<ChatSidebar /> collapsed rail', () => {
  it('renders an initials tile for each case', () => {
    useStudioStore.setState({
      cases: [
        makeCase({ id: 'c1', case_name: 'John Doe', case_number: '26-10700' }),
        makeCase({
          id: 'c2',
          case_name: 'John & Jane Smith',
          case_number: '26-20000',
        }),
        makeCase({
          id: 'c3',
          case_name: 'Acme Holdings LLC',
          case_number: '26-30000',
        }),
      ],
    });

    renderCollapsed();

    const rail = screen.getByRole('navigation', { name: 'Cases' });
    expect(within(rail).getByText('JD')).toBeInTheDocument();
    expect(within(rail).getByText('JJ')).toBeInTheDocument();
    expect(within(rail).getByText('AH')).toBeInTheDocument();
  });

  it('does not render the case rail when there are no cases', () => {
    renderCollapsed();
    expect(
      screen.queryByRole('navigation', { name: 'Cases' }),
    ).not.toBeInTheDocument();
  });

  it('marks the primary-selected case with aria-current and shows the focused-pane bar', () => {
    useStudioStore.setState({
      selectedCaseId: 'c1',
      cases: [
        makeCase({ id: 'c1', case_name: 'John Doe', case_number: '26-10700' }),
        makeCase({
          id: 'c2',
          case_name: 'Jane Roe',
          case_number: '26-20000',
        }),
      ],
    });

    renderCollapsed();

    const selectedTile = screen.getByRole('button', {
      name: /John Doe, case 26-10700/,
    });
    expect(selectedTile).toHaveAttribute('aria-current', 'true');
    const otherTile = screen.getByRole('button', {
      name: /Jane Roe, case 26-20000/,
    });
    expect(otherTile).not.toHaveAttribute('aria-current');
  });

  it('encodes streaming state in aria-label', () => {
    useStudioStore.setState({
      cases: [
        makeCase({ id: 'c1', case_name: 'John Doe', case_number: '26-10700' }),
      ],
    });
    seedChatSlice('c1', { isStreaming: true });

    renderCollapsed();

    expect(
      screen.getByRole('button', {
        name: 'John Doe, case 26-10700, AI working',
      }),
    ).toBeInTheDocument();
  });

  it('encodes unread state in aria-label and renders the amber dot', () => {
    useStudioStore.setState({
      cases: [
        makeCase({ id: 'c1', case_name: 'John Doe', case_number: '26-10700' }),
      ],
    });
    seedChatSlice('c1', { hasUnread: true });

    renderCollapsed();

    const tile = screen.getByRole('button', {
      name: 'John Doe, case 26-10700, new activity',
    });
    expect(tile).toBeInTheDocument();
    // Amber dot is the only `bg-amber-500` element in the rail; query
    // by class to assert its presence without coupling to DOM layout.
    expect(tile.querySelector('.bg-amber-500')).not.toBeNull();
  });

  it('streaming wins over unread — no amber dot, no "new activity" in label', () => {
    useStudioStore.setState({
      cases: [
        makeCase({ id: 'c1', case_name: 'John Doe', case_number: '26-10700' }),
      ],
    });
    seedChatSlice('c1', { isStreaming: true, hasUnread: true });

    renderCollapsed();

    const tile = screen.getByRole('button', {
      name: 'John Doe, case 26-10700, AI working',
    });
    expect(tile).toBeInTheDocument();
    expect(tile.querySelector('.bg-amber-500')).toBeNull();
  });

  it('shows the case-preview tooltip on hover with full name and case number', () => {
    // Joint filings arrive newline-separated from the BE; formatCaseName
    // joins them with " and " for display + the row's aria-label.
    useStudioStore.setState({
      cases: [
        makeCase({
          id: 'c1',
          case_name: 'John Smith\nJane Smith',
          case_number: '26-10700',
        }),
      ],
    });

    renderCollapsed();

    fireEvent.mouseEnter(
      screen.getByRole('button', {
        name: /John Smith and Jane Smith, case 26-10700/,
      }),
    );

    expect(screen.getByRole('tooltip', { hidden: true })).toBeInTheDocument();
    expect(screen.getByText('John Smith and Jane Smith')).toBeInTheDocument();
    expect(screen.getByText('26-10700')).toBeInTheDocument();
  });

  it('shows the same tooltip on keyboard focus (not just hover)', () => {
    useStudioStore.setState({
      cases: [
        makeCase({ id: 'c1', case_name: 'John Doe', case_number: '26-10700' }),
      ],
    });

    renderCollapsed();

    const tile = screen.getByRole('button', {
      name: /John Doe, case 26-10700/,
    });
    fireEvent.focus(tile);
    expect(screen.getByRole('tooltip', { hidden: true })).toBeInTheDocument();
    expect(screen.getByText('John Doe')).toBeInTheDocument();
  });
});
