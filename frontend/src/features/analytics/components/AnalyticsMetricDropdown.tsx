import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FiCheck, FiChevronDown } from 'react-icons/fi';

interface AnalyticsMetricOption {
  color: string;
  label: string;
  value: string;
}

interface AnalyticsMetricDropdownProps {
  options: AnalyticsMetricOption[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  label?: string;
}

export const AnalyticsMetricDropdown: React.FC<AnalyticsMetricDropdownProps> = ({
  options,
  selectedValues,
  onChange,
  label = 'Statuses',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState({
    top: 0,
    left: 0,
    width: 0,
    placement: 'bottom' as 'top' | 'bottom',
  });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const metricOptions = useMemo(
    () => options.filter((option) => option.value !== '__all__'),
    [options]
  );
  const allChecked = useMemo(
    () =>
      metricOptions.length > 0 &&
      metricOptions.every((option) => selectedValues.includes(option.value)),
    [metricOptions, selectedValues]
  );

  const selectedCount = selectedValues.length;
  const buttonLabel = useMemo(() => {
    if (allChecked) return 'All';
    if (selectedCount === 0) return `${label} (0)`;
    if (selectedCount === 1) {
      const selected = options.find((option) => option.value === selectedValues[0]);
      return selected ? selected.label : `${label} (1)`;
    }
    return `${label} (${selectedCount})`;
  }, [allChecked, label, options, selectedCount, selectedValues]);

  const updateMenuPosition = useCallback(() => {
    if (!buttonRef.current) return;

    const buttonRect = buttonRef.current.getBoundingClientRect();
    const estimatedMenuHeight = Math.min(options.length * 40 + 14, 248);
    const estimatedMenuWidth = Math.max(buttonRect.width, 168);
    const spaceBelow = window.innerHeight - buttonRect.bottom;
    const shouldOpenAbove = spaceBelow < estimatedMenuHeight && buttonRect.top > spaceBelow;
    const computedLeft = Math.max(
      12,
      Math.min(window.innerWidth - estimatedMenuWidth - 12, buttonRect.right - estimatedMenuWidth)
    );

    setMenuPosition({
      top: shouldOpenAbove ? buttonRect.top - estimatedMenuHeight - 8 : buttonRect.bottom + 8,
      left: computedLeft,
      width: estimatedMenuWidth,
      placement: shouldOpenAbove ? 'top' : 'bottom',
    });
  }, [options.length]);

  const closeDropdown = useCallback(() => setIsOpen(false), []);

  const handleToggle = () => {
    if (!isOpen) {
      updateMenuPosition();
      setIsOpen(true);
      return;
    }
    closeDropdown();
  };

  const handleSelect = (value: string) => {
    const isSelected = selectedValues.includes(value);
    const isAllOption = value === '__all__';

    if (isAllOption) {
      onChange(metricOptions.map((option) => option.value));
      return;
    }

    if (allChecked) {
      onChange([value]);
      return;
    }

    if (isSelected) {
      if (selectedValues.length === 1) return;
      onChange(selectedValues.filter((item) => item !== value));
      return;
    }

    onChange([...selectedValues, value]);
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
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [closeDropdown]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeDropdown();
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [closeDropdown]);

  useEffect(() => {
    if (!isOpen) return;

    updateMenuPosition();

    const handleWindowChange = () => updateMenuPosition();
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
      className="fixed z-[1200] overflow-hidden rounded-[18px] border border-border bg-surface shadow-xl"
      style={{
        width: menuPosition.width,
        left: menuPosition.left,
        top: menuPosition.top,
      }}
    >
      <div
        className={`max-h-[280px] overflow-y-auto p-1.5 ${
          menuPosition.placement === 'top' ? 'origin-bottom' : 'origin-top'
        }`}
      >
        {options.map((option) => {
          const isSelected =
            option.value === '__all__' ? allChecked : selectedValues.includes(option.value);

          return (
            <button
              key={option.value}
              type="button"
              onClick={() => handleSelect(option.value)}
              className={`flex w-full items-center gap-2.5 rounded-[14px] px-3 py-1 text-left text-[13px] transition-colors ${
                isSelected
                  ? 'text-app-accent-text'
                  : 'text-text-secondary hover:bg-surface-muted'
              }`}
            >
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: option.color }}
              />
              <span className="flex-1">{option.label}</span>
              <span
                className={`flex h-4 w-4 items-center justify-center rounded border text-[10px] ${
                  isSelected
                    ? 'border-indigo-500 bg-indigo-500 text-white'
                    : 'border-border bg-surface text-transparent'
                }`}
              >
                <FiCheck className="h-2.5 w-2.5" />
              </span>
            </button>
          );
        })}
      </div>
    </div>
  ) : null;

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={handleToggle}
        className="inline-flex items-center gap-2 rounded-full bg-surface-muted px-3 py-1.5 text-[11px] font-semibold text-muted transition-colors hover:bg-border"
      >
        <span>{buttonLabel}</span>
        <FiChevronDown className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen ? createPortal(dropdownMenu, document.body) : null}
    </div>
  );
};
