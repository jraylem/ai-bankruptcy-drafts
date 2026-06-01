import React, { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { LuSearch } from 'react-icons/lu';

import { acceptCaseInbox } from '@/services/case-inbox.service';
import { useToastStore } from '@/stores/useToastStore';
import { useStudioStore } from '@/stores/useStudioStore';
import type { CaseInboxEntry } from '@/types/case-inbox';

import { AcceptConfirmModal } from './AcceptConfirmModal';
import { CaseInboxEmptyState } from './CaseInboxEmptyState';
import { CaseInboxLayout } from './CaseInboxLayout';
import { CaseInboxPDFDrawer } from './CaseInboxPDFDrawer';
import { CaseInboxRow } from './CaseInboxRow';
import { CaseInboxSkeleton } from './CaseInboxSkeleton';
import { useCaseInboxArchived } from './useCaseInboxArchived';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 200;

export const CaseInboxArchivedPage: React.FC = () => {
  const [searchInput, setSearchInput] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [pdfDrawerEntry, setPDFDrawerEntry] = useState<CaseInboxEntry | null>(null);
  const [pendingSummon, setPendingSummon] = useState<CaseInboxEntry | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Auto-focus search per architect — anyone landing here came to find something.
  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  // Debounce search input → query key.
  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(searchInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [searchInput]);

  const { entries, isLoading, error, lastUpdatedAt, refetch } = useCaseInboxArchived({
    q: debouncedQ || undefined,
    limit: PAGE_SIZE,
  });
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const addToast = useToastStore((s) => s.addToast);

  const summonMutation = useMutation({
    mutationFn: (id: string) => acceptCaseInbox(id),
    onSuccess: (res) => {
      if (res.error || !res.data) {
        addToast(res.error ?? 'Already handled by another paralegal.', 'warning');
        setPendingSummon(null);
        void queryClient.invalidateQueries({ queryKey: ['case-inbox'] });
        return;
      }
      addToast('Reinstated. Opening drafting workspace…', 'success');
      setPendingSummon(null);
      setPDFDrawerEntry(null);
      // Firm rule: a reinstated case surfaces at the top of the list.
      useStudioStore.getState().promoteCaseToTop(res.data.case);
      void queryClient.invalidateQueries({ queryKey: ['case-inbox'] });
      navigate(`/case/${encodeURIComponent(res.data.case.id)}`);
    },
    onError: () => {
      addToast('Failed to reinstate petition. Please retry.', 'error');
      setPendingSummon(null);
    },
  });

  const searchInputEl = (
    <div className="relative">
      <LuSearch
        className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        aria-hidden="true"
      />
      <input
        ref={searchRef}
        type="search"
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        placeholder="Search case number or debtor name"
        aria-label="Search archived petitions"
        className="w-72 rounded-md border border-border bg-surface py-1.5 pl-8 pr-3 text-sm text-text placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
      />
    </div>
  );

  let body: React.ReactNode;
  if (error) {
    body = (
      <div className="rounded-lg border border-app-danger-border bg-app-danger-soft p-5 text-sm text-app-danger-text">
        Failed to load archived inbox: {error}
      </div>
    );
  } else if (isLoading && entries.length === 0) {
    body = <CaseInboxSkeleton />;
  } else if (entries.length === 0) {
    body = (
      <CaseInboxEmptyState
        variant="archived"
        lastUpdatedAt={lastUpdatedAt}
        onRefresh={refetch}
      />
    );
  } else {
    body = (
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border bg-surface-muted/50 text-[11px] font-semibold uppercase tracking-wide text-muted">
              <th className="py-2 pl-4 pr-4">Received</th>
              <th className="py-2 pr-4">Case #</th>
              <th className="py-2 pr-4">Debtor</th>
              <th className="py-2 pr-4">District</th>
              <th className="py-2 pr-4">SSN</th>
              <th className="py-2 pr-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <CaseInboxRow
                key={entry.id}
                entry={entry}
                isMutating={summonMutation.isPending && summonMutation.variables === entry.id}
                onAccept={setPendingSummon}
                onDismiss={() => {
                  // No-op for archived rows — dismiss button is hidden there.
                }}
                onViewPDF={setPDFDrawerEntry}
              />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <CaseInboxLayout
      title="Archived"
      subtitle="Petitions you've dismissed or that aged out after 48h. Search by case number or debtor name and click Reinstate to recover one into an active case."
      headerActions={searchInputEl}
      lastUpdatedAt={lastUpdatedAt}
      isLoading={isLoading}
      onRefresh={refetch}
    >
      {body}
      <CaseInboxPDFDrawer
        entry={pdfDrawerEntry}
        isOpen={!!pdfDrawerEntry}
        onClose={() => setPDFDrawerEntry(null)}
        onAccept={setPendingSummon}
        onDismiss={() => {
          // archived rows can't be dismissed; the drawer hides the button.
        }}
        isMutating={summonMutation.isPending && summonMutation.variables === pdfDrawerEntry?.id}
        onRefetchInbox={refetch}
      />
      <AcceptConfirmModal
        entry={pendingSummon}
        isMutating={summonMutation.isPending}
        onConfirm={() => pendingSummon && summonMutation.mutate(pendingSummon.id)}
        onCancel={() => setPendingSummon(null)}
      />
    </CaseInboxLayout>
  );
};

export default CaseInboxArchivedPage;
