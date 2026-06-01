import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { FiCheck, FiChevronDown } from 'react-icons/fi';

interface SelectDropdownOption {
  label: string;
  value: string;
}

interface SelectDropdownProps {
  value?: string;
  onChange?: (value: string) => void;
  values?: string[];
  onValuesChange?: (values: string[]) => void;
  options: SelectDropdownOption[];
  placeholder?: string;
  className?: string;
  buttonClassName?: string;
  multiple?: boolean;
  multipleSummaryLabel?: (count: number) => string;
  size?: 'default' | 'sm';
}

const DEFAULT_BUTTON_BASE =
  'flex w-full items-center justify-between border-0 bg-surface-muted text-left text-text-secondary outline-none transition focus:ring-2 focus:ring-option-selected-ring';

const defaultButtonClass = (size: 'default' | 'sm'): string =>
  `${DEFAULT_BUTTON_BASE} ${size === 'sm' ? 'rounded-lg px-2.5 py-1.5 text-xs' : 'rounded-xl px-4 py-3.5 text-sm'}`;

export const SelectDropdown: React.FC<SelectDropdownProps> = ({
  value,
  onChange,
  values,
  onValuesChange,
  options,
  placeholder = 'Select an option',
  className = '',
  buttonClassName,
  multiple = false,
  multipleSummaryLabel,
  size = 'default',
}) => {
  const MENU_GAP = 4;
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

  const selectedValues = useMemo(
    () => (multiple ? values ?? [] : value ? [value] : []),
    [multiple, value, values]
  );
  const selectedOptions = useMemo(
    () => options.filter((option) => selectedValues.includes(option.value)),
    [options, selectedValues]
  );
  const selectedOption = options.find((option) => option.value === value);

  const updateMenuPosition = useCallback(() => {
    if (!buttonRef.current) {
      return;
    }

    const buttonRect = buttonRef.current.getBoundingClientRect();
    const estimatedMenuHeight = Math.min(options.length * 44 + 12, 240);
    const spaceBelow = window.innerHeight - buttonRect.bottom;
    const shouldOpenAbove = spaceBelow < estimatedMenuHeight && buttonRect.top > spaceBelow;

    setMenuPosition({
      top: shouldOpenAbove ? buttonRect.top - MENU_GAP : buttonRect.bottom + MENU_GAP,
      left: buttonRect.left,
      width: buttonRect.width,
      placement: shouldOpenAbove ? 'top' : 'bottom',
    });
  }, [MENU_GAP, options.length]);

  const closeDropdown = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleToggle = () => {
    if (!isOpen) {
      updateMenuPosition();
      setIsOpen(true);
      return;
    }

    closeDropdown();
  };

  const handleSelect = (nextValue: string) => {
    if (multiple) {
      const nextValues = selectedValues.includes(nextValue)
        ? selectedValues.filter((currentValue) => currentValue !== nextValue)
        : [...selectedValues, nextValue];

      onValuesChange?.(nextValues);
      return;
    }

    onChange?.(nextValue);
    closeDropdown();
  };

  const buttonLabel = useMemo(() => {
    if (multiple) {
      if (selectedOptions.length === 0) {
        return placeholder;
      }

      if (selectedOptions.length === 1) {
        return selectedOptions[0]?.label ?? placeholder;
      }

      return multipleSummaryLabel?.(selectedOptions.length) ?? `${selectedOptions.length} selected`;
    }

    return selectedOption?.label || placeholder;
  }, [multiple, multipleSummaryLabel, placeholder, selectedOption, selectedOptions]);

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
    if (!isOpen) {
      return;
    }

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
      className="fixed z-[1000] overflow-hidden rounded-xl border border-border bg-surface shadow-xl"
      style={{
        width: menuPosition.width,
        left: menuPosition.left,
        top: menuPosition.top,
        transform: menuPosition.placement === 'top' ? 'translateY(-100%)' : undefined,
      }}
    >
      <div
        className={`max-h-[240px] overflow-y-auto p-1.5 ${
          menuPosition.placement === 'top' ? 'origin-bottom' : 'origin-top'
        }`}
      >
        {options.map((option) => {
          const isSelected = selectedValues.includes(option.value);

          return (
            <button
              key={option.value}
              type="button"
              onClick={() => handleSelect(option.value)}
              className={`flex w-full items-center justify-between gap-3 rounded-lg text-left transition-colors ${
                size === 'sm' ? 'px-2.5 py-2 text-xs' : 'px-3 py-2.5 text-sm'
              } ${
                isSelected
                  ? 'bg-app-accent-soft text-app-accent-text'
                  : 'text-text-secondary hover:bg-surface-muted'
              }`}
            >
              <span className="truncate">{option.label}</span>
              {multiple && isSelected ? <FiCheck className="h-4 w-4 flex-shrink-0" /> : null}
            </button>
          );
        })}
      </div>
    </div>
  ) : null;

  return (
    <div className={`relative ${className}`} ref={containerRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={handleToggle}
        className={buttonClassName ?? defaultButtonClass(size)}
      >
        <span className={selectedValues.length > 0 ? 'text-text-secondary' : 'text-subtle'}>
          {buttonLabel}
        </span>
        <FiChevronDown
          className={`h-4 w-4 flex-shrink-0 text-subtle transition-transform duration-200 ${
            isOpen ? 'rotate-180' : ''
          }`}
        />
      </button>

      {isOpen && createPortal(dropdownMenu, document.body)}
    </div>
  );
};
