import React, { useEffect, useRef, useState } from 'react';
import { DatePicker } from '@/components/common';
import { AiInsightsOverlay } from './AiInsightsOverlay';
import { useAnalyticsFiltersStore } from '../../stores/useAnalyticsFiltersStore';
import type { AnalyticsRangePreset } from '../../types/dashboard.types';
import { formatAnalyticsRangeLabel } from '../../utils/dashboard.mappers';

interface AnalyticsHeaderProps {
  title: string;
}

const getEndPickerOpenMonth = (startDate: string) => {
  if (!startDate) return '';

  const [year, month, day] = startDate.split('-').map(Number);
  if (!year || !month || !day) return startDate;

  const lastDayOfMonth = new Date(year, month, 0).getDate();

  if (day !== lastDayOfMonth) {
    return startDate;
  }

  const nextMonth = new Date(year, month, 1);
  const nextMonthYear = nextMonth.getFullYear();
  const nextMonthValue = `${nextMonth.getMonth() + 1}`.padStart(2, '0');
  const nextMonthDay = `${nextMonth.getDate()}`.padStart(2, '0');

  return `${nextMonthYear}-${nextMonthValue}-${nextMonthDay}`;
};

const toInputDate = (date: Date) => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const resolveRangeWindow = (
  preset: AnalyticsRangePreset,
  customStart: string,
  customEnd: string
) => {
  if (preset === 'custom') {
    return { start: customStart, end: customEnd };
  }

  const end = new Date();
  end.setHours(0, 0, 0, 0);
  const start = new Date(end);

  if (preset === '7d') {
    start.setDate(end.getDate() - 6);
  } else if (preset === '30d') {
    start.setDate(end.getDate() - 29);
  }

  return { start: toInputDate(start), end: toInputDate(end) };
};

export const AnalyticsHeader: React.FC<AnalyticsHeaderProps> = ({ title }) => {
  const customFilterRef = useRef<HTMLDivElement>(null);
  const [openPicker, setOpenPicker] = useState<'start' | 'end' | null>(null);
  const {
    rangePreset,
    customStart,
    customEnd,
    isCustomFilterOpen,
    setRangePreset,
    setCustomStart,
    setCustomEnd,
    toggleCustomFilter,
    closeCustomFilter,
  } = useAnalyticsFiltersStore();
  const endPickerOpenMonth = getEndPickerOpenMonth(customStart);
  const rangeWindow = resolveRangeWindow(rangePreset, customStart, customEnd);

  const rangeLabel = formatAnalyticsRangeLabel(rangeWindow.start, rangeWindow.end);
  const presetFilters: Array<{ label: string; value: AnalyticsRangePreset }> = [
    { label: 'Today', value: 'today' },
    { label: '7 Days', value: '7d' },
    { label: '30 Days', value: '30d' },
  ];

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (customFilterRef.current && !customFilterRef.current.contains(event.target as Node)) {
        closeCustomFilter();
        setOpenPicker(null);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [closeCustomFilter]);

  return (
    <>
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0 pr-4">
          <h1 className="font-poppins text-3xl font-extrabold tracking-tight text-text">{title}</h1>
          <p className="mt-1 text-xs font-medium italic text-subtle">{rangeLabel}</p>
        </div>

        <div className="pointer-events-none opacity-0">
          <div className="flex items-center rounded-full bg-surface/75 p-1">
            {presetFilters.map((filter) => (
              <span key={filter.value} className="rounded-full px-4 py-2 text-sm font-medium">
                {filter.label}
              </span>
            ))}
            <span className="rounded-full px-4 py-2 text-sm font-medium">Custom</span>
          </div>
        </div>
      </div>

      <div className="sticky top-4 z-20 -mt-[52px] mb-10 flex justify-end">
        <div className="inline-flex items-center gap-3">
          <AiInsightsOverlay />
          <div className="inline-flex items-center rounded-full bg-surface/75 p-1 shadow-[0_12px_32px_rgba(15,23,42,0.10)] backdrop-blur-xl">
            {presetFilters.map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => {
                  setRangePreset(filter.value);
                  setOpenPicker(null);
                }}
                className={`rounded-full px-4 py-2 text-sm font-medium transition-all ${
                  rangePreset === filter.value
                    ? 'bg-app-accent-soft font-semibold text-app-accent-text'
                    : 'text-muted hover:text-app-accent-text'
                }`}
              >
                {filter.label}
              </button>
            ))}

            <div className="relative" ref={customFilterRef}>
              <button
                type="button"
                onClick={() => {
                  toggleCustomFilter();
                  setOpenPicker((current) => (current ? null : 'start'));
                }}
                className={`rounded-full px-4 py-2 text-sm font-medium transition-all ${
                  rangePreset === 'custom'
                    ? 'bg-app-accent-soft font-semibold text-app-accent-text'
                    : 'text-muted hover:text-app-accent-text'
                }`}
              >
                Custom
              </button>

              {isCustomFilterOpen ? (
                <div className="absolute right-0 top-[calc(100%+12px)] z-30 w-[520px] rounded-2xl bg-surface/95 p-5 shadow-xl backdrop-blur-xl">
                  <div className="grid gap-5 md:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium text-text-secondary">
                        Start Date
                      </label>
                      <DatePicker
                        value={customStart}
                        onChange={(value) => {
                          setCustomStart(value);
                          setOpenPicker('end');
                        }}
                        placeholder="Select start date..."
                        className="mt-2"
                        usePortal={false}
                        dayShape="circle"
                        isOpen={openPicker === 'start'}
                        onOpenChange={(isOpen) =>
                          setOpenPicker((current) => {
                            if (isOpen) return 'start';
                            return current === 'start' ? null : current;
                          })
                        }
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text-secondary">
                        End Date
                      </label>
                      <DatePicker
                        value={customEnd}
                        onChange={(value) => {
                          setCustomEnd(value);
                          setOpenPicker(null);
                        }}
                        placeholder="Select end date..."
                        className="mt-2"
                        usePortal={false}
                        dayShape="circle"
                        isOpen={openPicker === 'end'}
                        onOpenChange={(isOpen) =>
                          setOpenPicker((current) => {
                            if (isOpen) return 'end';
                            return current === 'end' ? null : current;
                          })
                        }
                        minDate={customStart}
                        openToDate={endPickerOpenMonth}
                      />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
