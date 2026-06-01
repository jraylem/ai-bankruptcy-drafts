import React, { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { LuSearch } from 'react-icons/lu';

import { acceptCaseInbox, dismissCaseInbox } from '@/services/case-inbox.service';
import { useToastStore } from '@/stores/useToastStore';
import { useStudioStore } from '@/stores/useStudioStore';
import type { CaseInboxEntry } from '@/types/case-inbox';

import { AcceptConfirmModal } from './AcceptConfirmModal';
import { normalizeCaseNumber } from './formatting';
import { CaseInboxEmptyState } from './CaseInboxEmptyState';
import { CaseInboxLayout } from './CaseInboxLayout';
import { CaseInboxPDFDrawer } from './CaseInboxPDFDrawer';
import { CaseInboxRow } from './CaseInboxRow';
import { CaseInboxSkeleton } from './CaseInboxSkeleton';
import { DismissConfirmModal } from './DismissConfirmModal';
import { useCaseInbox } from './useCaseInbox';

export const CaseInboxPage: React.FC = () => {
  const { entries, isLoading, error, lastUpdatedAt, refetch } = useCaseInbox();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const addToast = useToastStore((s) => s.addToast);
  const [pendingDismiss, setPendingDismiss] = useState<CaseInboxEntry | null>(null);
  const [pendingAccept, setPendingAccept] = useState<CaseInboxEntry | null>(null);
  const [pdfDrawerEntry, setPDFDrawerEntry] = useState<CaseInboxEntry | null>(null);
  const [searchInput, setSearchInput] = useState<string>('');

  const trimmedQuery: string = searchInput.trim().toLowerCase();
  const filteredEntries: CaseInboxEntry[] = useMemo<CaseInboxEntry[]>(() => {
    if (!trimmedQuery) return entries;
    return entries.filter((entry: CaseInboxEntry): boolean => {
      // Search against BOTH the raw value (what's in the DB) and the
      // canonical form so a user can type either "8:26-bk-10491" or the
      // canonical "26-10491" and match the same row.
      const rawCaseNumber: string = (entry.case_number ?? '').toLowerCase();
      const canonicalCaseNumber: string = (normalizeCaseNumber(entry.case_number) ?? '').toLowerCase();
      const caseName: string = (entry.case_name ?? '').toLowerCase();
      return (
        rawCaseNumber.includes(trimmedQuery)
        || canonicalCaseNumber.includes(trimmedQuery)
        || caseName.includes(trimmedQuery)
      );
    });
  }, [entries, trimmedQuery]);

  const searchInputEl: React.ReactElement = (
    <div className="relative">
      <LuSearch
        className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
        aria-hidden="true"
      />
      <input
        type="search"
        value={searchInput}
        onChange={(event: React.ChangeEvent<HTMLInputElement>): void => setSearchInput(event.target.value)}
        placeholder="Search case number or debtor name"
        aria-label="Search pending petitions"
        className="w-72 rounded-md border border-border bg-surface py-1.5 pl-8 pr-3 text-sm text-text placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
      />
    </div>
  );

  const acceptMutation = useMutation({
    mutationFn: (id: string) => acceptCaseInbox(id),
    onSuccess: (res) => {
      if (res.error || !res.data) {
        addToast(res.error ?? 'Already handled by another paralegal.', 'warning');
        setPendingAccept(null);
        void queryClient.invalidateQueries({ queryKey: ['case-inbox'] });
        return;
      }
      // Outcome-aware toast. The BE re-runs the matcher at action time;
      // if it merged into an unfiled counterpart, the inbox row's stored
      // matches_unfiled_case_id tracks that — use it as the merge signal.
      const debtor = res.data.case.case_name || 'case';
      const merged = pendingAccept?.matches_unfiled_case_id != null;
      addToast(
        merged
          ? `Merged into existing case ${debtor}. Opening…`
          : 'Case accepted. Opening drafting workspace…',
        'success',
      );
      setPendingAccept(null);
      setPDFDrawerEntry(null);
      // Firm rule: a freshly accepted case surfaces at the top of the list.
      useStudioStore.getState().promoteCaseToTop(res.data.case);
      void queryClient.invalidateQueries({ queryKey: ['case-inbox'] });
      navigate(`/case/${encodeURIComponent(res.data.case.id)}`);
    },
    onError: () => {
      addToast('Failed to accept petition. Please retry.', 'error');
      setPendingAccept(null);
    },
  });

  const dismissMutation = useMutation({
    mutationFn: (id: string) => dismissCaseInbox(id),
    onSuccess: (res) => {
      if (res.error) {
        addToast(res.error, 'warning');
      } else if (res.data?.case) {
        // Phase 2 reject-with-merge: BE promoted an unfiled counterpart
        // to filed AND archived the inbox row. Toast names the case.
        const debtor = res.data.case.case_name || 'existing case';
        addToast(
          `Merged into existing case ${debtor} and archived the inbox entry.`,
          'success',
        );
      } else {
        addToast('Petition rejected and moved to Archived.', 'success');
      }
      setPendingDismiss(null);
      setPDFDrawerEntry(null);
      void queryClient.invalidateQueries({ queryKey: ['case-inbox'] });
    },
    onError: () => {
      addToast('Failed to reject. Please retry.', 'error');
      setPendingDismiss(null);
    },
  });

  const onAccept = (entry: CaseInboxEntry) => {
    setPendingAccept(entry);
  };

  const onDismiss = (entry: CaseInboxEntry) => {
    setPendingDismiss(entry);
  };

  let body: React.ReactNode;
  if (error) {
    body = (
      <div className="rounded-lg border border-app-danger-border bg-app-danger-soft p-5 text-sm text-app-danger-text">
        Failed to load inbox: {error}
      </div>
    );
  } else if (isLoading && entries.length === 0) {
    body = <CaseInboxSkeleton />;
  } else if (entries.length === 0) {
    body = (
      <CaseInboxEmptyState
        variant="inbox"
        lastUpdatedAt={lastUpdatedAt}
        onRefresh={refetch}
      />
    );
  } else if (filteredEntries.length === 0) {
    body = (
      <div className="rounded-lg border border-border bg-surface p-8 text-center text-sm text-muted">
        No matches for &ldquo;{searchInput.trim()}&rdquo;.
      </div>
    );
  } else {
    body = (
      <div className="overflow-hidden rounded-lg border border-border bg-surface">
        <table className="w-full table-fixed text-left">
          <thead>
            <tr className="border-b border-border bg-surface-muted/50 text-[11px] font-semibold uppercase tracking-wide text-muted">
              <th className="w-28 whitespace-nowrap py-2 pl-4 pr-4">Received</th>
              <th className="w-32 whitespace-nowrap py-2 pr-4">Case #</th>
              <th className="py-2 pr-4">Debtor</th>
              <th className="w-24 whitespace-nowrap py-2 pr-4">District</th>
              <th className="w-28 whitespace-nowrap py-2 pr-4">SSN</th>
              <th className="w-72 whitespace-nowrap py-2 pr-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredEntries.map((entry) => (
              <CaseInboxRow
                key={entry.id}
                entry={entry}
                isMutating={
                  (acceptMutation.isPending && acceptMutation.variables === entry.id) ||
                  (dismissMutation.isPending && dismissMutation.variables === entry.id)
                }
                onAccept={onAccept}
                onDismiss={onDismiss}
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
      title="Inbox"
      subtitle="From CM/ECF notice emails, ready for paralegal action."
      headerActions={entries.length > 0 ? searchInputEl : null}
      lastUpdatedAt={lastUpdatedAt}
      isLoading={isLoading}
      onRefresh={refetch}
    >
      {body}
      <DismissConfirmModal
        entry={pendingDismiss}
        isMutating={dismissMutation.isPending}
        onConfirm={() => pendingDismiss && dismissMutation.mutate(pendingDismiss.id)}
        onCancel={() => setPendingDismiss(null)}
      />
      <AcceptConfirmModal
        entry={pendingAccept}
        isMutating={acceptMutation.isPending}
        onConfirm={() => pendingAccept && acceptMutation.mutate(pendingAccept.id)}
        onCancel={() => setPendingAccept(null)}
      />
      <CaseInboxPDFDrawer
        entry={pdfDrawerEntry}
        isOpen={!!pdfDrawerEntry}
        onClose={() => setPDFDrawerEntry(null)}
        onAccept={onAccept}
        onDismiss={onDismiss}
        isMutating={
          (acceptMutation.isPending && acceptMutation.variables === pdfDrawerEntry?.id) ||
          (dismissMutation.isPending && dismissMutation.variables === pdfDrawerEntry?.id)
        }
        onRefetchInbox={refetch}
      />
    </CaseInboxLayout>
  );
};

export default CaseInboxPage;
