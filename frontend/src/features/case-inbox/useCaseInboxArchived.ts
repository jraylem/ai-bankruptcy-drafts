import { useQuery } from '@tanstack/react-query';

import { fetchCaseInboxArchived } from '@/services/case-inbox.service';
import type { CaseInboxEntry } from '@/types/case-inbox';

export interface UseCaseInboxArchivedReturn {
  entries: CaseInboxEntry[];
  isLoading: boolean;
  error: string | null;
  lastUpdatedAt: number | null;
  refetch: () => void;
}

interface Params {
  q?: string;
  limit?: number;
  offset?: number;
}

/** Archived/summon list. `q` searches case_number + case_name ILIKE on the BE.
 *  Empty `q` returns the firm's archived rows newest-first. */
export function useCaseInboxArchived(params: Params = {}): UseCaseInboxArchivedReturn {
  const { q, limit = 50, offset = 0 } = params;
  const query = useQuery({
    queryKey: ['case-inbox', 'archived', { q: q ?? '', limit, offset }],
    queryFn: async () => {
      const res = await fetchCaseInboxArchived({ q, limit, offset });
      if (!res.data) {
        throw new Error(res.error ?? 'Failed to load archived inbox.');
      }
      return res.data;
    },
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  const entries = query.data?.entries ?? [];
  return {
    entries,
    isLoading: query.isLoading,
    error: query.error ? String(query.error.message ?? query.error) : null,
    lastUpdatedAt: query.dataUpdatedAt || null,
    refetch: () => void query.refetch(),
  };
}
