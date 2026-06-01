import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { DismissConfirmModal } from '@/features/case-inbox/DismissConfirmModal';
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

describe('<DismissConfirmModal />', () => {
  it('renders nothing when entry is null', () => {
    const { container } = render(
      <DismissConfirmModal
        entry={null}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the debtor name + case number in the title', () => {
    render(
      <DismissConfirmModal
        entry={entry}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Nicholas Earl Sampson/)).toBeInTheDocument();
    // Modal normalizes the raw '8:26-bk-01330' to the canonical 'YY-NNNNN' shape for display.
    expect(screen.getByText(/26-01330/)).toBeInTheDocument();
  });

  it('makes recoverability explicit in the copy ("reinstate" within 48h)', () => {
    render(
      <DismissConfirmModal
        entry={entry}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(/reinstate it/i)).toBeInTheDocument();
    // "Archived" appears 2x in the modal copy — once in the body sentence
    // ("moves to Archived") and once in the "Archived tab" phrase. Both
    // are intentional — verify at least one.
    expect(screen.getAllByText(/Archived/).length).toBeGreaterThanOrEqual(1);
  });

  it('fires onConfirm when the destructive button is clicked', () => {
    const onConfirm = vi.fn();
    render(
      <DismissConfirmModal
        entry={entry}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Reject and archive' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('fires onCancel when Cancel is clicked', () => {
    const onCancel = vi.fn();
    render(
      <DismissConfirmModal
        entry={entry}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('fires onCancel on Escape', () => {
    const onCancel = vi.fn();
    render(
      <DismissConfirmModal
        entry={entry}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('disables both buttons while a rejection is in flight', () => {
    render(
      <DismissConfirmModal
        entry={entry}
        isMutating={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Rejecting…' })).toBeDisabled();
  });

  // ─── Phase 2 — unfiled-case match heads-up ─────────────────────────

  it('does NOT render the heads-up block when there is no match', () => {
    render(
      <DismissConfirmModal entry={entry} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByText(/Existing unfiled case found/)).not.toBeInTheDocument();
  });

  it('renders the heads-up block when entry has a matched unfiled case', () => {
    render(
      <DismissConfirmModal
        entry={entryWithMatch}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByText(/Existing unfiled case found/)).toBeInTheDocument();
    expect(screen.getByText(/Nicholas E\. Sampson/)).toBeInTheDocument();
  });

  it('switches the destructive button to "Reject merge and archive" when matched', () => {
    render(
      <DismissConfirmModal
        entry={entryWithMatch}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('button', { name: 'Reject merge and archive' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Reject and archive' }),
    ).not.toBeInTheDocument();
  });

  it('shows "Merging…" label while mutating on the merge path', () => {
    render(
      <DismissConfirmModal
        entry={entryWithMatch}
        isMutating={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Merging…' })).toBeDisabled();
  });
});
