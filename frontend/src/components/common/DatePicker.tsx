import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { DayPicker } from 'react-day-picker';
import type { Matcher } from 'react-day-picker';
import { FiCalendar, FiChevronDown, FiChevronLeft, FiChevronRight, FiClock } from 'react-icons/fi';

interface RdpDropdownOption {
  value: number;
  label: string;
  disabled?: boolean;
}

interface RdpDropdownProps {
  options?: RdpDropdownOption[];
  value?: number | string;
  onChange?: (event: React.ChangeEvent<HTMLSelectElement>) => void;
  reverse?: boolean;
  // react-day-picker v9 sometimes emits options OUTSIDE the
  // startMonth/endMonth bound (it pads the year list with a few buffer
  // years for visual continuity). minValue/maxValue cull those so the
  // dropdown actually respects the cap callers asked for.
  minValue?: number;
  maxValue?: number;
}

// Inline themed select for the calendar's month / year captions. We render
// the menu absolutely-positioned within the calendar's own DOM tree (no
// portal) so:
//   - The menu width fits the longest option (no truncated month names).
//   - Clicks inside the menu stay inside the calendar's outside-click scope,
//     so picking a month/year doesn't accidentally close the whole popover.
const RdpDropdown: React.FC<RdpDropdownProps> = ({
  options,
  value,
  onChange,
  reverse = false,
  minValue,
  maxValue,
}) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const list = options ?? [];
  const filteredList = useMemo(() => {
    if (minValue === undefined && maxValue === undefined) return list;
    return list.filter((opt) => {
      if (minValue !== undefined && opt.value < minValue) return false;
      if (maxValue !== undefined && opt.value > maxValue) return false;
      return true;
    });
  }, [list, minValue, maxValue]);
  const ordered = useMemo(
    () => (reverse ? [...filteredList].reverse() : filteredList),
    [filteredList, reverse],
  );
  const currentLabel = filteredList.find((o) => String(o.value) === String(value))?.label ?? '';

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent): void => {
      const node = containerRef.current;
      if (!node) return;
      if (node.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [open]);

  const handleSelect = (next: number): void => {
    setOpen(false);
    onChange?.({
      target: { value: String(next) },
    } as unknown as React.ChangeEvent<HTMLSelectElement>);
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex items-center gap-1 rounded-md border border-app-border bg-app-surface px-2 py-1 text-sm font-semibold text-app-text-primary transition-colors hover:border-app-border-strong focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
      >
        <span>{currentLabel}</span>
        <FiChevronDown className="h-3.5 w-3.5 text-app-text-muted" />
      </button>
      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-[calc(100%+4px)] z-50 max-h-56 w-max min-w-full overflow-y-auto rounded-lg border border-app-border bg-app-surface py-1 shadow-lg"
        >
          {ordered.map((opt) => {
            const isSelected = String(opt.value) === String(value);
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={isSelected}
                disabled={opt.disabled}
                onClick={() => handleSelect(opt.value)}
                className={`block w-full px-3 py-1.5 text-left text-sm transition-colors hover:bg-app-accent-soft hover:text-app-accent-text ${
                  isSelected
                    ? 'bg-app-accent-soft font-semibold text-app-accent-text'
                    : 'text-app-text-secondary'
                } ${opt.disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

interface DatePickerProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  mode?: 'date' | 'datetime';
  dayShape?: 'default' | 'circle';
  minDate?: string;
  maxDate?: string;
  openToDate?: string;
  usePortal?: boolean;
  isOpen?: boolean;
  onOpenChange?: (isOpen: boolean) => void;
  triggerClassName?: string;
  // v9 caption layout. 'label' (default) keeps the current arrows-only header.
  // 'dropdown' adds month + year selects so you can jump to any month/year
  // without click-spamming the arrow buttons. When using a dropdown layout,
  // pass `fromYear` / `toYear` to bound the year list (defaults: 1900 → +10).
  captionLayout?: 'label' | 'dropdown' | 'dropdown-months' | 'dropdown-years';
  fromYear?: number;
  toYear?: number;
}

const parseInputDate = (value: string): Date | undefined => {
  if (!value) return undefined;
  const datePart = value.split('T')[0];
  const parts = datePart.split('-');
  if (parts.length !== 3) return undefined;

  const [year, month, day] = parts.map((part) => Number(part));
  if (!year || !month || !day) return undefined;

  return new Date(year, month - 1, day);
};

const formatInputDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const parseInputTime = (value: string): string => {
  if (!value || !value.includes('T')) return '';
  const timePart = value.split('T')[1] || '';
  const [hours = '', minutes = ''] = timePart.split(':');
  if (!hours || !minutes) return '';
  return `${hours}:${minutes}`;
};

const formatInputDateTime = (date: Date, timeValue: string): string => {
  const safeTime = timeValue || '09:00';
  return `${formatInputDate(date)}T${safeTime}`;
};

const parseTimeParts = (
  timeValue: string
): { hour12: string; minute: string; meridiem: 'AM' | 'PM' } => {
  if (!timeValue) {
    return { hour12: '9', minute: '00', meridiem: 'AM' };
  }

  const [hourRaw = '09', minuteRaw = '00'] = timeValue.split(':');
  const hour24 = Number(hourRaw);
  const minute = minuteRaw.padStart(2, '0').slice(0, 2);

  if (Number.isNaN(hour24)) {
    return { hour12: '9', minute: '00', meridiem: 'AM' };
  }

  const meridiem: 'AM' | 'PM' = hour24 >= 12 ? 'PM' : 'AM';
  const normalizedHour = hour24 % 12 || 12;

  return {
    hour12: String(normalizedHour),
    minute,
    meridiem,
  };
};

const formatTime24 = (hour12Value: string, minuteValue: string, meridiem: 'AM' | 'PM'): string => {
  const parsedHour = Number(hour12Value);
  const safeHour = Number.isNaN(parsedHour) ? 9 : Math.min(12, Math.max(1, parsedHour));
  const parsedMinute = Number(minuteValue);
  const safeMinute = Number.isNaN(parsedMinute) ? 0 : Math.min(59, Math.max(0, parsedMinute));

  let hour24 = safeHour % 12;
  if (meridiem === 'PM') {
    hour24 += 12;
  }

  return `${String(hour24).padStart(2, '0')}:${String(safeMinute).padStart(2, '0')}`;
};

const clampHour12Input = (value: string): string => {
  const digits = value.replace(/\D/g, '').slice(0, 2);
  if (!digits) return '';

  const numeric = Number(digits);
  if (Number.isNaN(numeric)) return '';
  if (numeric <= 0) return '1';
  if (numeric > 12) return '12';
  return String(numeric);
};

const clampMinuteInput = (value: string): string => {
  const digits = value.replace(/\D/g, '').slice(0, 2);
  if (!digits) return '';

  const numeric = Number(digits);
  if (Number.isNaN(numeric)) return '';
  return String(Math.min(59, Math.max(0, numeric)));
};

const formatDisplayDate = (value: string, mode: 'date' | 'datetime'): string => {
  const parsed = parseInputDate(value);
  if (!parsed) return '';

  const dateLabel = parsed.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  if (mode === 'date') {
    return dateLabel;
  }

  const timeValue = parseInputTime(value);
  if (!timeValue) return dateLabel;

  const [hours, minutes] = timeValue.split(':').map((part) => Number(part));
  const withTime = new Date(parsed);
  withTime.setHours(hours || 0, minutes || 0, 0, 0);

  const timeLabel = withTime.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });

  return `${dateLabel} at ${timeLabel}`;
};

export const DatePicker: React.FC<DatePickerProps> = ({
  value,
  onChange,
  placeholder = 'Select date...',
  className = '',
  mode = 'date',
  dayShape = 'default',
  minDate,
  maxDate,
  openToDate,
  usePortal = true,
  isOpen: controlledIsOpen,
  onOpenChange,
  triggerClassName = '',
  captionLayout = 'label',
  fromYear,
  toYear,
}) => {
  const [uncontrolledIsOpen, setUncontrolledIsOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState<Date | undefined>(undefined);
  const [timeDraft, setTimeDraft] = useState<{
    hour12: string;
    minute: string;
    meridiem: 'AM' | 'PM';
  }>({
    hour12: '9',
    minute: '00',
    meridiem: 'AM',
  });
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

  const selectedDate = useMemo(() => parseInputDate(value), [value]);
  const minDateValue = useMemo(() => parseInputDate(minDate ?? ''), [minDate]);
  const maxDateValue = useMemo(() => parseInputDate(maxDate ?? ''), [maxDate]);
  const openToDateValue = useMemo(() => parseInputDate(openToDate ?? ''), [openToDate]);
  const disabledMatchers = useMemo<Matcher[] | undefined>(() => {
    const matchers: Matcher[] = [];

    if (minDateValue) {
      matchers.push({ before: minDateValue });
    }

    if (maxDateValue) {
      matchers.push({ after: maxDateValue });
    }

    return matchers.length > 0 ? matchers : undefined;
  }, [maxDateValue, minDateValue]);
  const timeValue = useMemo(() => parseInputTime(value), [value]);
  const timeParts = useMemo(() => parseTimeParts(timeValue), [timeValue]);
  const displayValue = useMemo(() => formatDisplayDate(value, mode), [value, mode]);

  useEffect(() => {
    setTimeDraft({
      hour12: timeParts.hour12,
      minute: timeParts.minute,
      meridiem: timeParts.meridiem,
    });
  }, [timeParts]);

  useEffect(() => {
    setVisibleMonth(selectedDate);
  }, [selectedDate]);

  useEffect(() => {
    if (!isOpen) return;
    setVisibleMonth(openToDateValue ?? selectedDate ?? new Date());
  }, [isOpen, openToDateValue, selectedDate]);

  const updateMenuPosition = useCallback(() => {
    if (!buttonRef.current) return;

    const buttonRect = buttonRef.current.getBoundingClientRect();
    const estimatedMenuHeight = mode === 'datetime' ? 320 : 300;
    const estimatedMenuWidth = mode === 'datetime' ? 500 : 332;
    const spaceBelow = window.innerHeight - buttonRect.bottom;
    const shouldOpenAbove = spaceBelow < estimatedMenuHeight && buttonRect.top > spaceBelow;
    const clampedLeft = Math.min(
      Math.max(12, buttonRect.left),
      Math.max(12, window.innerWidth - estimatedMenuWidth - 12)
    );

    setMenuPosition({
      top: shouldOpenAbove ? buttonRect.top - estimatedMenuHeight - 8 : buttonRect.bottom + 8,
      left: clampedLeft,
      width: buttonRect.width,
      placement: shouldOpenAbove ? 'top' : 'bottom',
    });
  }, [mode]);

  const setOpenState = useCallback(
    (nextOpen: boolean) => {
      if (!isControlled) {
        setUncontrolledIsOpen(nextOpen);
      }
      onOpenChange?.(nextOpen);
    },
    [isControlled, onOpenChange]
  );

  const closeDropdown = useCallback(() => {
    setOpenState(false);
  }, [setOpenState]);

  const handleToggle = () => {
    if (!isOpen) {
      updateMenuPosition();
      setVisibleMonth(openToDateValue ?? selectedDate ?? new Date());
      setOpenState(true);
      return;
    }

    closeDropdown();
  };

  const handleSelect = (date?: Date) => {
    if (!date) return;
    if (mode === 'datetime') {
      onChange(formatInputDateTime(date, timeValue || '09:00'));
      return;
    }

    onChange(formatInputDate(date));
    closeDropdown();
  };

  const handleTimeChange = (nextTime: string) => {
    if (!selectedDate) return;
    onChange(formatInputDateTime(selectedDate, nextTime));
  };

  const updateTimeParts = (
    nextParts: Partial<{ hour12: string; minute: string; meridiem: 'AM' | 'PM' }>
  ) => {
    if (!selectedDate) return;

    const merged = {
      hour12: nextParts.hour12 ?? timeParts.hour12,
      minute: nextParts.minute ?? timeParts.minute,
      meridiem: nextParts.meridiem ?? timeParts.meridiem,
    };

    handleTimeChange(formatTime24(merged.hour12, merged.minute, merged.meridiem));
  };

  const commitTimeDraft = () => {
    if (!selectedDate) return;

    const normalizedHour = clampHour12Input(timeDraft.hour12.trim()) || timeParts.hour12;
    const normalizedMinute = clampMinuteInput(timeDraft.minute.trim()) || timeParts.minute;
    const normalizedMeridiem = timeDraft.meridiem;
    const nextTime = formatTime24(normalizedHour, normalizedMinute, normalizedMeridiem);

    handleTimeChange(nextTime);
    setTimeDraft(parseTimeParts(nextTime));
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node) &&
        !dropdownRef.current?.contains(event.target as Node)
      ) {
        closeDropdown();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [closeDropdown]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeDropdown();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('keydown', handleEscape);
    };
  }, [closeDropdown]);

  useEffect(() => {
    if (!isOpen) return;

    updateMenuPosition();

    const handleWindowChange = () => {
      updateMenuPosition();
    };

    window.addEventListener('resize', handleWindowChange);
    window.addEventListener('scroll', handleWindowChange, true);

    return () => {
      window.removeEventListener('resize', handleWindowChange);
      window.removeEventListener('scroll', handleWindowChange, true);
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
          : {
              width: 'fit-content',
              maxWidth: 'min(100vw - 24px, 100%)',
            }
      }
    >
      <div className={`flex ${mode === 'datetime' ? 'h-full items-stretch gap-3' : 'block'}`}>
        <DayPicker
          mode="single"
          selected={selectedDate}
          month={visibleMonth}
          onMonthChange={setVisibleMonth}
          onSelect={handleSelect}
          navLayout="around"
          showOutsideDays
          disabled={disabledMatchers}
          captionLayout={captionLayout}
          startMonth={
            captionLayout !== 'label' && fromYear !== undefined
              ? new Date(fromYear, 0, 1)
              : undefined
          }
          endMonth={
            captionLayout !== 'label' && toYear !== undefined
              ? new Date(toYear, 11, 31)
              : undefined
          }
          className={`rdp-custom ${menuPosition.placement === 'top' ? 'origin-bottom' : 'origin-top'}`}
          classNames={{
            months: 'flex justify-center',
            month: 'grid w-fit grid-cols-[36px_1fr_36px] items-center gap-x-2 gap-y-2',
            month_caption:
              captionLayout === 'label'
                ? 'col-start-2 row-start-1 flex items-center justify-center'
                : 'col-start-2 row-start-1 flex items-center justify-center gap-1.5',
            caption_label:
              captionLayout === 'label'
                ? 'font-poppins text-base font-semibold text-app-text-primary text-center'
                : 'sr-only',
            dropdowns: 'flex items-center justify-center gap-1.5',
            dropdown_root: 'relative',
            dropdown:
              'cursor-pointer rounded-md border border-app-border bg-app-surface px-2 py-1 pr-6 text-sm font-semibold text-app-text-primary hover:border-app-border-strong focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft appearance-none',
            months_dropdown: '',
            years_dropdown: '',
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
            day_button: `rdp-day-trigger flex h-9 w-9 items-center justify-center text-sm font-medium text-app-text-secondary transition-colors hover:bg-app-accent-soft hover:text-app-accent-text ${
              dayShape === 'circle' ? 'rounded-full' : 'rounded-xl'
            }`,
            selected: `rdp-selected-day ${dayShape === 'circle' ? 'rdp-selected-day-circle' : ''}`,
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
            MonthsDropdown: (props) => <RdpDropdown {...(props as RdpDropdownProps)} />,
            // Years run newest → oldest so the recent year is one click away.
            // Bound by fromYear/toYear so react-day-picker's buffer years
            // don't sneak into the menu.
            // Years run newest → oldest so the recent year is one click away.
            YearsDropdown: (props) => (
              <RdpDropdown
                {...(props as RdpDropdownProps)}
                reverse
                minValue={fromYear}
                maxValue={toYear}
              />
            ),
          }}
        />
        {mode === 'datetime' && (
          <div className="flex h-full flex-1">
            <div className="flex h-full w-[98%] self-stretch flex-col border-l border-app-border pl-3 pt-3">
              <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.12em] text-app-text-subtle">
                Time
              </label>
              <div className="rounded-xl bg-app-surface-muted px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <input
                      type="text"
                      inputMode="numeric"
                      maxLength={2}
                      value={timeDraft.hour12}
                      onChange={(e) => {
                        const nextHour = clampHour12Input(e.target.value);
                        setTimeDraft((current) => ({ ...current, hour12: nextHour }));
                      }}
                      onBlur={commitTimeDraft}
                      className="w-10 border-0 bg-transparent p-0 text-center text-xl font-medium text-app-text-primary outline-none"
                    />
                    <span className="text-xl font-medium text-app-text-muted">:</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      maxLength={2}
                      value={timeDraft.minute}
                      onChange={(e) => {
                        const nextMinute = clampMinuteInput(e.target.value);
                        setTimeDraft((current) => ({ ...current, minute: nextMinute }));
                      }}
                      onBlur={commitTimeDraft}
                      className="w-10 border-0 bg-transparent p-0 text-center text-xl font-medium text-app-text-primary outline-none"
                    />
                  </div>
                  <FiClock className="h-5 w-5 text-app-text-muted" />
                </div>
              </div>
              <div className="mt-2 grid grid-cols-2 rounded-xl bg-app-surface-muted p-1">
                {(['AM', 'PM'] as const).map((period) => {
                  const isSelected = timeDraft.meridiem === period;

                  return (
                    <button
                      key={period}
                      type="button"
                      onClick={() => {
                        setTimeDraft((current) => ({ ...current, meridiem: period }));
                        updateTimeParts({
                          hour12: timeDraft.hour12.trim() || timeParts.hour12,
                          minute: timeDraft.minute.trim() || timeParts.minute,
                          meridiem: period,
                        });
                      }}
                      className={`rounded-lg px-3 py-1 text-sm font-semibold transition ${
                        isSelected
                          ? 'bg-app-accent text-white shadow-sm'
                          : 'text-app-text-muted hover:text-app-text-primary'
                      }`}
                    >
                      {period}
                    </button>
                  );
                })}
              </div>
              <button
                type="button"
                onClick={() => {
                  commitTimeDraft();
                  closeDropdown();
                }}
                className="mt-auto inline-flex w-full items-center justify-center rounded-xl bg-app-accent px-4 py-1.5 text-sm font-semibold text-white transition hover:brightness-110"
                style={{ marginTop: '5.5rem' }}
              >
                Confirm
              </button>
            </div>
          </div>
        )}
      </div>
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
            className={displayValue ? 'truncate text-app-text-secondary' : 'truncate text-app-text-muted'}
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
