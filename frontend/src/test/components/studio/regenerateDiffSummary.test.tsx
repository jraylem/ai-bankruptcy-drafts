import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RegenerateDiffSummary } from '@/components/studio/RegenerateDiffSummary';
import type { RegenerateDiff } from '@/types/studio';

const diffWithAllReasons: RegenerateDiff = {
  added: ['debtor_phone', 'service_address'],
  removed: [
    { name: 'case_no_title', reason: 'merged', merged_into: 'case_number' },
    { name: 'clerk_block', reason: 'ignored' },
    { name: 'docket_title', reason: 'unexpected' },
  ],
  preserved: ['case_number', 'debtor_name', 'chapter'],
};

describe('<RegenerateDiffSummary />', () => {
  it('renders Added section with the count + variable names', () => {
    render(<RegenerateDiffSummary diff={diffWithAllReasons} />);
    expect(screen.getByText(/Added \(2\)/)).toBeInTheDocument();
    expect(screen.getByText('debtor_phone')).toBeInTheDocument();
    expect(screen.getByText('service_address')).toBeInTheDocument();
    expect(screen.getByText(/unrequested/i)).toBeInTheDocument();
  });

  it('renders Removed entries with reason-specific annotations', () => {
    render(<RegenerateDiffSummary diff={diffWithAllReasons} />);
    expect(screen.getByText(/Removed \(3\)/)).toBeInTheDocument();
    // merged → shows "merged into" annotation; the merged_into name also
    // appears in Preserved (it's the merge target), so getAllByText.
    expect(screen.getByText(/merged into/i)).toBeInTheDocument();
    expect(screen.getAllByText('case_number').length).toBeGreaterThan(0);
    // ignored → shows plain "ignored" annotation
    expect(screen.getByText('ignored')).toBeInTheDocument();
    // unexpected → shows "unexpected drop" drift annotation
    expect(screen.getByText(/unexpected drop/i)).toBeInTheDocument();
  });

  it('renders Preserved as a collapsed list with "+N more" expander when many', () => {
    const many: RegenerateDiff = {
      added: [],
      removed: [],
      preserved: ['a', 'b', 'c', 'd', 'e', 'f'],
    };
    render(<RegenerateDiffSummary diff={many} />);
    expect(screen.getByText(/Preserved \(6\)/)).toBeInTheDocument();
    // First three render; the rest hide behind expander
    expect(screen.getByText('a')).toBeInTheDocument();
    expect(screen.getByText('b')).toBeInTheDocument();
    expect(screen.getByText('c')).toBeInTheDocument();
    expect(screen.queryByText('d')).not.toBeInTheDocument();
    expect(screen.getByText(/\+3 more/)).toBeInTheDocument();

    fireEvent.click(screen.getByText(/\+3 more/));
    expect(screen.getByText('d')).toBeInTheDocument();
    expect(screen.getByText('e')).toBeInTheDocument();
    expect(screen.getByText('f')).toBeInTheDocument();
  });

  it('renders the empty-state pill when no changes', () => {
    const empty: RegenerateDiff = { added: [], removed: [], preserved: [] };
    render(<RegenerateDiffSummary diff={empty} />);
    expect(
      screen.getByText(/no changes\. All variables preserved/i),
    ).toBeInTheDocument();
  });
});
