import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { AcceptConfirmModal } from '@/features/case-inbox/AcceptConfirmModal';
import type { CaseInboxEntry } from '@/types/case-inbox';

const entry: CaseInboxEntry = {
  id: 'inbox-1',
  case_number: '8:26-bk-01330',
  case_name: 'Nicholas Earl Sampson',
  ssn_last4: '1879',
  ssn_extraction_status: 'found',
  court_district: 'FLSB',
  status: 'ready',
  source: 'gmail_ecf',
  received_at: '2026-05-20T14:30:00Z',
  created_at: '2026-05-20T14:32:00Z',
  archived_at: null,
  dismissed_by_user_id: null,
  petition_pdf_url: null,
  matches_unfiled_case_id: null,
  matched_unfiled_case: null,
};

const entryWithMatch: CaseInboxEntry = {
  ...entry,
  matches_unfiled_case_id: 'case-unfiled-uuid',
  matched_unfiled_case: {
    id: 'case-unfiled-uuid',
    case_name: 'Nicholas E. Sampson',
    ssn_last4: '1879',
    created_at: '2026-05-15T10:00:00Z',
  },
};

describe('<AcceptConfirmModal />', () => {
  it('renders nothing when entry is null', () => {
    const { container } = render(
      <AcceptConfirmModal entry={null} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders Accept copy for ready entries', () => {
    render(
      <AcceptConfirmModal entry={entry} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByText(/Accept Nicholas Earl Sampson/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Accept and open' })).toBeInTheDocument();
  });

  it('renders Reinstate copy for archived entries', () => {
    render(
      <AcceptConfirmModal
        entry={{ ...entry, status: 'archived', archived_at: '2026-05-15T00:00:00Z' }}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(/Reinstate Nicholas Earl Sampson/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reinstate and open' })).toBeInTheDocument();
  });

  it('fires onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn();
    render(<AcceptConfirmModal entry={entry} onConfirm={onConfirm} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Accept and open' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('fires onCancel when Cancel is clicked', () => {
    const onCancel = vi.fn();
    render(<AcceptConfirmModal entry={entry} onConfirm={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('fires onCancel when ESC is pressed', () => {
    const onCancel = vi.fn();
    render(<AcceptConfirmModal entry={entry} onConfirm={vi.fn()} onCancel={onCancel} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('disables both buttons while isMutating', () => {
    render(
      <AcceptConfirmModal
        entry={entry}
        isMutating={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Accepting…' })).toBeDisabled();
  });

  // ─── Phase 2 — unfiled-case match heads-up ─────────────────────────

  it('does NOT render the heads-up block when there is no match', () => {
    render(
      <AcceptConfirmModal entry={entry} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByText(/Existing unfiled case found/)).not.toBeInTheDocument();
  });

  it('renders the heads-up block when entry has a matched unfiled case', () => {
    render(
      <AcceptConfirmModal entry={entryWithMatch} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByText(/Existing unfiled case found/)).toBeInTheDocument();
    expect(screen.getByText(/Nicholas E\. Sampson/)).toBeInTheDocument();
  });

  it('switches the confirm button to "Accept merge and open" when matched', () => {
    render(
      <AcceptConfirmModal entry={entryWithMatch} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: 'Accept merge and open' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Accept and open' })).not.toBeInTheDocument();
  });

  it('shows "Merging…" label while mutating on the merge path', () => {
    render(
      <AcceptConfirmModal
        entry={entryWithMatch}
        isMutating={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Merging…' })).toBeDisabled();
  });
});
