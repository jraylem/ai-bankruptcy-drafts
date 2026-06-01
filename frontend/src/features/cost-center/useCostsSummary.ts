import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { fetchCostsSummary } from '@/services/costs.service';
import type { CostRange, CostsSummaryResponse } from '@/types/costs';

export interface UseCostsSummaryReturn {
  data: CostsSummaryResponse | null;
  range: CostRange;
  setRange: (next: CostRange) => void;
  isLoading: boolean;
  error: string | null;
  /** ms timestamp of the last successful fetch. Null until first
   *  successful response. Drives the "Updated Xm ago" header line. */
  lastUpdatedAt: number | null;
  refetch: () => void;
}

export function useCostsSummary(
  initialRange: CostRange = 'month',
): UseCostsSummaryReturn {
  const [range, setRange] = useState<CostRange>(initialRange);
  const query = useQuery({
    queryKey: ['costs-summary', range],
    queryFn: async () => {
      const res = await fetchCostsSummary(range);
      if (!res.data) {
        throw new Error(res.error ?? 'Failed to load costs.');
      }
      return res.data;
    },
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  return {
    data: query.data ?? null,
    range,
    setRange,
    isLoading: query.isLoading,
    error: query.error ? String(query.error.message ?? query.error) : null,
    lastUpdatedAt: query.dataUpdatedAt || null,
    refetch: () => void query.refetch(),
  };
}
