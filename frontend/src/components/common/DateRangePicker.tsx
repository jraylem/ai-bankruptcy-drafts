import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { DayPicker } from 'react-day-picker';
import type { DateRange, Matcher } from 'react-day-picker';
import { FiCalendar, FiChevronDown, FiChevronLeft, FiChevronRight } from 'react-icons/fi';

interface DateRangePickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  triggerClassName?: string;
  minDate?: string;
  maxDate?: string;
  usePortal?: boolean;
  numberOfMonths?: 1 | 2;
  isOpen?: boolean;
  onOpenChange?: (isOpen: boolean) => void;
}

const RANGE_SEPARATOR = ' to ';

const formatProseDate = (date: Date): string =>
  date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

const parseProseDate = (value: string): Date | undefined => {
  if (!value) return undefined;
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) return undefined;
  const d = new Date(ts);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
};

const parseRangeValue = (raw: string): DateRange | undefined => {
  if (!raw) return undefined;
  const [fromStr, toStr] = raw.split(RANGE_SEPARATOR);
  const from = parseProseDate(fromStr ?? '');
  const to = parseProseDate(toStr ?? '');
  if (!from && !to) return undefined;
  return { from, to };
};

const formatRangeValue = (range: DateRange): string => {
  if (!range.from && !range.to) return '';
  const from = range.from ? formatProseDate(range.from) : '';
  const to = range.to ? formatProseDate(range.to) : '';
  if (from && !to) return from;
  if (!from && to) return to;
  return `${from}${RANGE_SEPARATOR}${to}`;
};

const parseIsoDate = (value: string | undefined): Date | undefined => {
  if (!value) return undefined;
  const parts = value.split('-');
  if (parts.length !== 3) return undefined;
  const [year, month, day] = parts.map(Number);
  if (!year || !month || !day) return undefined;
  return new Date(year, month - 1, day);
};

export const DateRangePicker: React.FC<DateRangePickerProps> = ({
  value,
  onChange,
  placeholder = 'Select date range…',
  className = '',
  triggerClassName = '',
  minDate,
  maxDate,
  usePortal = true,
  numberOfMonths = 2,
  isOpen: controlledIsOpen,
  onOpenChange,
}) => {
  const [uncontrolledIsOpen, setUncontrolledIsOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState<Date | undefined>(undefined);
  const [menuPosition, setMenuPosition] = useState({
    top: 0,
    left: 0,
    width: 0,
    placement: 'bottom' as 'top' | 'bottom',
  });

  const buttonRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const isControlled = controlledIsOpen !== undefined;
  const isOpen = isControlled ? controlledIsOpen : uncontrolledIsOpen;

  const selectedRange = useMemo(() => parseRangeValue(value), [value]);
  const minDateValue = useMemo(() => parseIsoDate(minDate), [minDate]);
  const maxDateValue = useMemo(() => parseIsoDate(maxDate), [maxDate]);

  const disabledMatchers = useMemo<Matcher[] | undefined>(() => {
    const matchers: Matcher[] = [];
    if (minDateValue) matchers.push({ before: minDateValue });
    if (maxDateValue) matchers.push({ after: maxDateValue });
    return matchers.length > 0 ? matchers : undefined;
  }, [maxDateValue, minDateValue]);

  const displayValue = value;

  useEffect(() => {
    if (!isOpen) return;
    setVisibleMonth(selectedRange?.from ?? selectedRange?.to ?? new Date());
  }, [isOpen, selectedRange]);

  const setOpenState = useCallback(
    (next: boolean) => {
      if (!isControlled) setUncontrolledIsOpen(next);
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  const closeDropdown = useCallback(() => setOpenState(false), [setOpenState]);

  const updateMenuPosition = useCallback(() => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const estimatedHeight = 360;
    const estimatedWidth = numberOfMonths === 2 ? 620 : 332;
    const spaceBelow = window.innerHeight - rect.bottom;
    const openAbove = spaceBelow < estimatedHeight && rect.top > spaceBelow;
    const clampedLeft = Math.min(
      Math.max(12, rect.left),
      Math.max(12, window.innerWidth - estimatedWidth - 12),
    );
    setMenuPosition({
      top: openAbove ? rect.top - estimatedHeight - 8 : rect.bottom + 8,
      left: clampedLeft,
      width: rect.width,
      placement: openAbove ? 'top' : 'bottom',
    });
  }, [numberOfMonths]);

  const handleToggle = () => {
    if (!isOpen) {
      updateMenuPosition();
      setVisibleMonth(selectedRange?.from ?? selectedRange?.to ?? new Date());
      setOpenState(true);
      return;
    }
    closeDropdown();
  };

  const handleSelect = (range: DateRange | undefined) => {
    if (!range) {
      onChange('');
      return;
    }
    onChange(formatRangeValue(range));
    if (range.from && range.to) closeDropdown();
  };

  useEffect(() => {
    const onMouseDown = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node) &&
        !dropdownRef.current?.contains(e.target as Node)
      ) {
        closeDropdown();
      }
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [closeDropdown]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDropdown();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [closeDropdown]);

  useEffect(() => {
    if (!isOpen) return;
    updateMenuPosition();
    const handler = () => updateMenuPosition();
    window.addEventListener('resize', handler);
    window.addEventListener('scroll', handler, true);
    return () => {
      window.removeEventListener('resize', handler);
      window.removeEventListener('scroll', handler, true);
    };
  }, [isOpen, updateMenuPosition]);

  const dropdownMenu = isOpen ? (
    <div
      ref={dropdownRef}
      className={`${usePortal ? 'fixed' : 'absolute left-0 top-[calc(100%+8px)]'} z-[1000] overflow-hidden rounded-2xl border border-app-border bg-app-surface p-2.5 shadow-xl`}
      style={
        usePortal
          ? {
              width: 'fit-content',
              maxWidth: 'calc(100vw - 24px)',
              left: menuPosition.left,
              top: menuPosition.top,
            }
          : { width: 'fit-content', maxWidth: 'min(100vw - 24px, 100%)' }
      }
    >
      <DayPicker
        mode="range"
        selected={selectedRange}
        month={visibleMonth}
        onMonthChange={setVisibleMonth}
        onSelect={handleSelect}
        navLayout="around"
        numberOfMonths={numberOfMonths}
        showOutsideDays
        disabled={disabledMatchers}
        className={`rdp-custom ${menuPosition.placement === 'top' ? 'origin-bottom' : 'origin-top'}`}
        classNames={{
          months: 'flex justify-center gap-4',
          month: 'grid w-fit grid-cols-[36px_1fr_36px] items-center gap-x-2 gap-y-2',
          month_caption: 'col-start-2 row-start-1 flex items-center justify-center',
          caption_label: 'font-poppins text-base font-semibold text-app-text-primary text-center',
          nav: 'contents',
          button_previous:
            'col-start-1 row-start-1 flex h-9 w-9 items-center justify-center rounded-full border border-app-border bg-app-surface text-app-text-muted transition-colors hover:border-app-border-strong hover:bg-app-surface-muted hover:text-app-accent-text',
          button_next:
            'col-start-3 row-start-1 flex h-9 w-9 items-center justify-center rounded-full border border-app-border bg-app-surface text-app-text-muted transition-colors hover:border-app-border-strong hover:bg-app-surface-muted hover:text-app-accent-text',
          month_grid: 'col-span-3 row-start-2 w-fit border-collapse',
          weekdays: 'grid grid-cols-7 gap-0.5 mb-1.5',
          weekday:
            'flex h-7 w-9 items-center justify-center text-[11px] font-semibold uppercase tracking-[0.12em] text-app-text-subtle',
          week: 'grid grid-cols-7 gap-0.5',
          day: 'flex items-center justify-center',
          day_button:
            'rdp-day-trigger flex h-9 w-9 items-center justify-center rounded-xl text-sm font-medium text-app-text-secondary transition-colors hover:bg-app-accent-soft hover:text-app-accent-text',
          selected: 'rdp-selected-day',
          range_start: 'rdp-range-edge',
          range_end: 'rdp-range-edge',
          range_middle: 'rdp-range-middle',
          today: 'rdp-today',
          outside: 'pointer-events-none text-app-text-subtle opacity-60',
          disabled: 'cursor-not-allowed text-app-text-subtle opacity-50',
        }}
        components={{
          Chevron: ({ orientation, ...props }) =>
            orientation === 'left' ? (
              <FiChevronLeft className="h-4 w-4" {...props} />
            ) : (
              <FiChevronRight className="h-4 w-4" {...props} />
            ),
        }}
      />
    </div>
  ) : null;

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={handleToggle}
        className={`flex h-12 w-full items-center justify-between rounded-xl border-0 bg-app-surface-muted px-4 text-left text-sm text-app-text-secondary outline-none transition focus:ring-2 focus:ring-app-accent/20 ${triggerClassName}`}
      >
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-app-accent-soft text-app-accent-text">
            <FiCalendar className="h-3.5 w-3.5" />
          </div>
          <span
            className={
              displayValue
                ? 'truncate text-app-text-secondary'
                : 'truncate text-app-text-muted'
            }
          >
            {displayValue || placeholder}
          </span>
        </div>
        <FiChevronDown
          className={`h-4 w-4 shrink-0 text-app-text-muted transition-transform duration-200 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {isOpen ? (usePortal ? createPortal(dropdownMenu, document.body) : dropdownMenu) : null}
    </div>
  );
};
