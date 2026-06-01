import { useMemo } from 'react';
import { useAnalyticsFiltersStore } from '../stores/useAnalyticsFiltersStore';

export const useAnalyticsQueryFilters = () => {
  const { rangePreset, customStart, customEnd } = useAnalyticsFiltersStore();

  return useMemo(
    () =>
      rangePreset === 'custom'
        ? { range: rangePreset, start: customStart, end: customEnd }
        : { range: rangePreset },
    [rangePreset, customStart, customEnd]
  );
};
