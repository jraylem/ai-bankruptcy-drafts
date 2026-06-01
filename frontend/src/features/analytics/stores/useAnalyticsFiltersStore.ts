import { create } from 'zustand';
import type { AnalyticsRangePreset } from '../types/dashboard.types';

const formatDateInput = (date: Date) => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const now = new Date();
const thirtyDaysAgo = new Date(now);
thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

interface AnalyticsFiltersState {
  rangePreset: AnalyticsRangePreset;
  customStart: string;
  customEnd: string;
  isCustomFilterOpen: boolean;
  setRangePreset: (preset: AnalyticsRangePreset) => void;
  setCustomStart: (value: string) => void;
  setCustomEnd: (value: string) => void;
  toggleCustomFilter: () => void;
  closeCustomFilter: () => void;
}

export const useAnalyticsFiltersStore = create<AnalyticsFiltersState>((set) => ({
  rangePreset: '30d',
  customStart: formatDateInput(thirtyDaysAgo),
  customEnd: formatDateInput(now),
  isCustomFilterOpen: false,
  setRangePreset: (preset) =>
    set({
      rangePreset: preset,
      isCustomFilterOpen: preset === 'custom' ? true : false,
    }),
  setCustomStart: (value) =>
    set((state) => ({
      customStart: value,
      customEnd: state.customEnd < value ? value : state.customEnd,
    })),
  setCustomEnd: (value) =>
    set((state) => ({
      customEnd: value < state.customStart ? state.customStart : value,
    })),
  toggleCustomFilter: () =>
    set((state) => ({
      rangePreset: 'custom',
      isCustomFilterOpen: !state.isCustomFilterOpen,
    })),
  closeCustomFilter: () => set({ isCustomFilterOpen: false }),
}));
