import { useQuery } from '@tanstack/react-query';

import { fetchCaseInbox } from '@/services/case-inbox.service';
import type { CaseInboxEntry } from '@/types/case-inbox';

export interface UseCaseInboxReturn {
  entries: CaseInboxEntry[];
  /** Total pending count for the sidebar badge — same value as
   *  `entries.length` (derived client-side from the list response per
   *  the architect's "no separate /count endpoint" call). */
  pendingCount: number;
  isLoading: boolean;
  error: string | null;
  lastUpdatedAt: number | null;
  refetch: () => void;
}

/** Main /inbox query: firm-scoped, status='ready'. 30s staleTime matches
 *  the Cost Center pattern (background SWR, no aggressive polling). */
export function useCaseInbox(): UseCaseInboxReturn {
  const query = useQuery({
    queryKey: ['case-inbox', 'ready'],
    queryFn: async () => {
      const res = await fetchCaseInbox();
      if (!res.data) {
        throw new Error(res.error ?? 'Failed to load inbox.');
      }
      return res.data;
    },
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  const entries = query.data?.entries ?? [];
  return {
    entries,
    pendingCount: entries.length,
    isLoading: query.isLoading,
    error: query.error ? String(query.error.message ?? query.error) : null,
    lastUpdatedAt: query.dataUpdatedAt || null,
    refetch: () => void query.refetch(),
  };
}
