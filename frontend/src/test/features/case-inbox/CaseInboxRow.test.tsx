import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { CaseInboxRow } from '@/features/case-inbox/CaseInboxRow';
import type { CaseInboxEntry } from '@/types/case-inbox';

const baseEntry: CaseInboxEntry = {
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
  petition_pdf_url: 'https://r2.example/petition.pdf',
  matches_unfiled_case_id: null,
  matched_unfiled_case: null,
};

function renderRow(overrides: Partial<CaseInboxEntry> = {}, handlers = {}) {
  const onAccept = vi.fn();
  const onDismiss = vi.fn();
  const onViewPDF = vi.fn();
  render(
    <table>
      <tbody>
        <CaseInboxRow
          entry={{ ...baseEntry, ...overrides }}
          onAccept={onAccept}
          onDismiss={onDismiss}
          onViewPDF={onViewPDF}
          {...handlers}
        />
      </tbody>
    </table>,
  );
  return { onAccept, onDismiss, onViewPDF };
}

describe('<CaseInboxRow />', () => {
  it('shows the Accept button when row is ready', () => {
    renderRow({ status: 'ready' });
    expect(screen.getByRole('button', { name: 'Accept' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
  });

  it('shows the Reinstate button (not Accept) when row is archived', () => {
    renderRow({
      status: 'archived',
      archived_at: '2026-05-18T10:00:00Z',
    });
    expect(screen.getByRole('button', { name: 'Reinstate' })).toBeInTheDocument();
    // Dismiss is hidden on archived rows
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });

  it('annotates archived rows as "archived" when dismissed_by_user_id is null', () => {
    renderRow({
      status: 'archived',
      archived_at: '2026-05-15T10:00:00Z',
      dismissed_by_user_id: null,
    });
    expect(screen.getByText(/Archived/)).toBeInTheDocument();
  });

  it('annotates archived rows as "rejected by another paralegal" when dismissed_by_user_id is set', () => {
    renderRow({
      status: 'archived',
      archived_at: '2026-05-20T13:00:00Z',
      dismissed_by_user_id: 'user-maria',
    });
    expect(screen.getByText(/Rejected/)).toBeInTheDocument();
  });

  it('renders SSN as masked digits when ssn_extraction_status=found', () => {
    renderRow({ ssn_extraction_status: 'found', ssn_last4: '1879' });
    expect(screen.getByText('••••1879')).toBeInTheDocument();
  });

  it('shows amber "Scanned PDF" pill when ssn_extraction_status=scanned_image', () => {
    renderRow({ ssn_extraction_status: 'scanned_image', ssn_last4: null });
    expect(screen.getByText('Scanned PDF')).toBeInTheDocument();
  });

  it('shows muted dash when SSN was not found in text', () => {
    renderRow({ ssn_extraction_status: 'not_found', ssn_last4: null });
    // The dash itself is a non-distinctive character — verify the row has
    // *no* masked SSN and no Scanned PDF pill instead.
    expect(screen.queryByText(/•••/)).toBeNull();
    expect(screen.queryByText('Scanned PDF')).toBeNull();
  });

  it('fires onAccept with the entry on Accept click', () => {
    const { onAccept } = renderRow({ status: 'ready' });
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(onAccept).toHaveBeenCalledTimes(1);
    expect(onAccept).toHaveBeenCalledWith(expect.objectContaining({ id: 'inbox-1' }));
  });

  it('fires onAccept (same handler) when Reinstate is clicked on archived rows', () => {
    const { onAccept } = renderRow({ status: 'archived' });
    fireEvent.click(screen.getByRole('button', { name: 'Reinstate' }));
    expect(onAccept).toHaveBeenCalledTimes(1);
  });

  it('opens the PDF drawer via onViewPDF when View PDF is clicked', () => {
    const { onViewPDF } = renderRow();
    const button = screen.getByRole('button', { name: /open petition pdf in drawer/i });
    fireEvent.click(button);
    expect(onViewPDF).toHaveBeenCalledTimes(1);
    expect(onViewPDF).toHaveBeenCalledWith(expect.objectContaining({ id: 'inbox-1' }));
  });

  it('hides the View PDF affordance when petition_pdf_url is null', () => {
    renderRow({ petition_pdf_url: null });
    expect(screen.queryByRole('button', { name: /open petition pdf in drawer/i })).toBeNull();
  });

  it('disables action buttons while isMutating', () => {
    renderRow({ status: 'ready' }, { isMutating: true });
    expect(screen.getByRole('button', { name: 'Accept' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled();
  });
});
