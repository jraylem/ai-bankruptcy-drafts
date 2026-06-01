import React, { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';

interface DependentChipVariablesPickerProps {
  value: string[];
  onChange: (next: string[]) => void;
  
  selfVariableName?: string;
}

export const DependentChipVariablesPicker = ({
  value,
  onChange,
  selfVariableName,
}: DependentChipVariablesPickerProps): ReactElement => {
  const templateSpec = useStudioStore((s) => s.templateSpec);
  const [isOpen, setIsOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const filterInputRef = useRef<HTMLInputElement>(null);

  const eligibleVars = useMemo(
    () =>
      templateSpec.filter(
        (v) =>
          v.source === 'reco_chips_from_dependent_variables' &&
          v.template_variable !== selfVariableName,
      ),
    [templateSpec, selfVariableName],
  );

  const available = useMemo(
    () => eligibleVars.filter((v) => !value.includes(v.template_variable)),
    [eligibleVars, value],
  );

  const filtered = useMemo(() => {
    if (!filter) return available;
    const f = filter.toLowerCase();
    return available.filter((v) => v.template_variable.toLowerCase().includes(f));
  }, [filter, available]);

  useEffect(() => {
    if (!isOpen) return;
    filterInputRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent): void => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const addVariable = (name: string): void => {
    if (value.includes(name)) return;
    onChange([...value, name]);
    setIsOpen(false);
    setFilter('');
    setSelectedIndex(0);
  };

  const removeVariable = (name: string): void => {
    onChange(value.filter((n) => n !== name));
  };

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (!isOpen) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      setIsOpen(false);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
      return;
    }
    if (e.key === 'Enter' && filtered.length > 0) {
      e.preventDefault();
      const target = filtered[selectedIndex] ?? filtered[0];
      if (target) addVariable(target.template_variable);
    }
  };

  return (
    <div className="space-y-2" ref={containerRef}>
      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-2">
        {value.length === 0 && (
          <span className="px-1 text-xs text-subtle">
            No sibling chip dependencies. Click "+ Add chip ref" to align with another reco-chips
            field's generated chip array.
          </span>
        )}
        {value.map((name) => {
          const isKnownChipSource = eligibleVars.some(
            (v) => v.template_variable === name,
          );
          const tone = isKnownChipSource
            ? 'border-app-accent-soft bg-app-accent-soft text-app-accent-text'
            : 'border-app-warning-soft bg-app-warning-soft text-app-warning-text';
          const tooltip = isKnownChipSource
            ? `${name} (reco_chips_from_dependent_variables)`
            : `${name} — unknown or wrong source type. Must be reco_chips_from_dependent_variables.`;
          return (
            <span
              key={name}
              title={tooltip}
              className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs ${tone}`}
            >
              <span aria-hidden className="text-[10px]">◆</span>
              <span className="font-mono">{name}</span>
              <button
                type="button"
                aria-label={`Remove ${name}`}
                onClick={() => removeVariable(name)}
                className="rounded-sm px-0.5 leading-none hover:bg-black/10"
              >
                ×
              </button>
            </span>
          );
        })}
        <button
          type="button"
          onClick={() => {
            setIsOpen(true);
            setFilter('');
            setSelectedIndex(0);
          }}
          disabled={available.length === 0}
          className="inline-flex items-center gap-1 rounded-md border border-dashed border-border bg-surface px-2 py-0.5 text-xs font-medium text-text-secondary transition-colors hover:bg-app-accent-soft hover:text-app-accent-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          + Add chip ref
        </button>
      </div>
      {isOpen && (
        <div className="relative">
          <div className="absolute z-20 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
            <div className="border-b border-border bg-surface-muted/60 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
              Pick a sibling chip variable
            </div>
            <input
              ref={filterInputRef}
              type="text"
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setSelectedIndex(0);
              }}
              onKeyDown={handleKeyDown}
              placeholder="Filter…"
              className="w-full border-b border-border bg-surface px-3 py-1.5 text-xs text-text-secondary placeholder:text-subtle focus:outline-none"
            />
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted">
                {filter
                  ? `No reco-chips siblings match "${filter}".`
                  : available.length === 0
                  ? 'No more reco_chips_from_dependent_variables siblings to add.'
                  : 'No eligible siblings.'}
              </p>
            ) : (
              <ul role="listbox" className="max-h-60 overflow-y-auto">
                {filtered.map((v, idx) => (
                  <li
                    key={v.template_variable}
                    role="option"
                    aria-selected={idx === selectedIndex}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      addVariable(v.template_variable);
                    }}
                    onMouseEnter={() => setSelectedIndex(idx)}
                    className={`cursor-pointer px-3 py-2 text-sm ${
                      idx === selectedIndex
                        ? 'bg-app-accent-soft text-app-accent-text'
                        : 'text-text-secondary hover:bg-surface-muted'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{v.template_variable}</span>
                      <span className="text-[10px] uppercase tracking-wider text-muted">
                        chip-from-deps
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="border-t border-border bg-surface-muted/40 px-3 py-1.5 text-[10px] text-muted">
              ↑↓ navigate · ↵ insert · Esc cancel
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default DependentChipVariablesPicker;
