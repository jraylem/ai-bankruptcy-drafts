import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { CaseInboxPDFDrawer } from '@/features/case-inbox/CaseInboxPDFDrawer';
import type { CaseInboxEntry } from '@/types/case-inbox';

const loadPDFFromUrl = vi.fn();
const clearPDF = vi.fn();

vi.mock('@/stores/usePDFStore', () => ({
  usePDFStore: (selector: (state: unknown) => unknown) => {
    const state = { loadPDFFromUrl, clearPDF };
    return selector(state);
  },
}));

vi.mock('@/components/pdf/PDFViewer', () => ({
  PDFViewer: () => <div data-testid="pdf-viewer-stub" />,
}));

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

function renderDrawer(overrides: Partial<CaseInboxEntry> = {}, props: Partial<Parameters<typeof CaseInboxPDFDrawer>[0]> = {}) {
  const onClose = vi.fn();
  const onAccept = vi.fn();
  const onDismiss = vi.fn();
  const onRefetchInbox = vi.fn();
  const entry = { ...baseEntry, ...overrides };
  render(
    <CaseInboxPDFDrawer
      entry={entry}
      isOpen={true}
      onClose={onClose}
      onAccept={onAccept}
      onDismiss={onDismiss}
      onRefetchInbox={onRefetchInbox}
      {...props}
    />,
  );
  return { entry, onClose, onAccept, onDismiss, onRefetchInbox };
}

beforeEach(() => {
  loadPDFFromUrl.mockReset();
  clearPDF.mockReset();
  loadPDFFromUrl.mockResolvedValue(true);
});

describe('<CaseInboxPDFDrawer />', () => {
  it('renders header metadata when open with a ready entry', () => {
    renderDrawer();
    // Drawer normalizes the raw '8:26-bk-01330' to the canonical 'YY-NNNNN' shape for display.
    expect(screen.getByText('26-01330')).toBeInTheDocument();
    expect(screen.getByText('Nicholas Earl Sampson')).toBeInTheDocument();
    expect(screen.getByText('FLSB')).toBeInTheDocument();
    expect(screen.getByText('••••1879')).toBeInTheDocument();
  });

  it('calls loadPDFFromUrl with inbox-{id} cache key when opened', async () => {
    renderDrawer();
    await waitFor(() => {
      expect(loadPDFFromUrl).toHaveBeenCalledWith(
        'inbox-inbox-1',
        'https://r2.example/petition.pdf',
        'Nicholas Earl Sampson',
      );
    });
  });

  it('renders scanned-PDF warning banner when ssn_extraction_status=scanned_image', () => {
    renderDrawer({ ssn_extraction_status: 'scanned_image', ssn_last4: null });
    expect(screen.getByText(/Scanned PDF — text search will not work/i)).toBeInTheDocument();
  });

  it('fires onAccept(entry) when footer Accept clicked on ready row', () => {
    const { entry, onAccept } = renderDrawer({ status: 'ready' });
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(onAccept).toHaveBeenCalledWith(entry);
  });

  it('renders Reinstate (not Accept) and hides Dismiss for archived rows', () => {
    renderDrawer({ status: 'archived', archived_at: '2026-05-18T10:00:00Z' });
    expect(screen.getByRole('button', { name: 'Reinstate' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Reject/ })).toBeNull();
  });

  it('fires onDismiss(entry) when footer Dismiss clicked on ready row', () => {
    const { entry, onDismiss } = renderDrawer({ status: 'ready' });
    fireEvent.click(screen.getByRole('button', { name: /Reject/ }));
    expect(onDismiss).toHaveBeenCalledWith(entry);
  });

  it('fires onClose when ESC is pressed', () => {
    const { onClose } = renderDrawer();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('fires onClose when footer Close button is clicked', () => {
    const { onClose } = renderDrawer();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('shows retry CTA when loadPDFFromUrl returns false', async () => {
    loadPDFFromUrl.mockResolvedValueOnce(false);
    renderDrawer();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: /open in new tab/i })).toHaveAttribute(
      'href',
      'https://r2.example/petition.pdf',
    );
  });

  it('retry button re-fetches the inbox and retries loadPDFFromUrl', async () => {
    loadPDFFromUrl.mockResolvedValueOnce(false);
    const { onRefetchInbox } = renderDrawer();
    await waitFor(() => screen.getByRole('button', { name: /try again/i }));
    loadPDFFromUrl.mockResolvedValueOnce(true);
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRefetchInbox).toHaveBeenCalled();
    expect(loadPDFFromUrl).toHaveBeenCalledTimes(2);
  });

  it('renders nothing when entry is null', () => {
    const { container } = render(
      <CaseInboxPDFDrawer
        entry={null}
        isOpen={false}
        onClose={vi.fn()}
        onAccept={vi.fn()}
        onDismiss={vi.fn()}
        onRefetchInbox={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
