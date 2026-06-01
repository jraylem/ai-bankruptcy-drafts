import React, { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';
import type { FieldSource } from '@/types/studio';
import { isEligibleForReference } from './_referenceability';

interface DependentVariablesPickerProps {
  value: string[];
  onChange: (next: string[]) => void;
  /** Source of the variable whose dependent_variables list is being
   *  edited. Drives contextual eligibility — LLM_DRAFT referencers may
   *  reference USER_INPUT-rooted targets (BE's Path B wave-B reach). */
  referencerSource?: FieldSource | null;
}

export const DependentVariablesPicker = ({
  value,
  onChange,
  referencerSource = null,
}: DependentVariablesPickerProps): ReactElement => {
  const templateSpec = useStudioStore((s) => s.templateSpec);
  const [isOpen, setIsOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const filterInputRef = useRef<HTMLInputElement>(null);

  const byName = useMemo(
    () => new Map(templateSpec.map((v) => [v.template_variable, v])),
    [templateSpec]
  );

  const eligibleVars = useMemo(
    () => templateSpec.filter((v) => isEligibleForReference(v, byName, referencerSource)),
    [templateSpec, byName, referencerSource]
  );

  const available = useMemo(
    () => eligibleVars.filter((v) => !value.includes(v.template_variable)),
    [eligibleVars, value]
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
            No variables selected. Click "+ Add variable" to insert one.
          </span>
        )}
        {value.map((name) => {
          const known = byName.get(name);
          const eligible =
            known !== undefined && isEligibleForReference(known, byName, referencerSource);
          const tone = !known
            ? 'border-app-warning-soft bg-app-warning-soft text-app-warning-text'
            : !eligible
            ? 'border-app-warning-soft bg-app-warning-soft/70 text-app-warning-text'
            : 'border-app-accent-soft bg-app-accent-soft text-app-accent-text';
          const tooltip = !known
            ? `Unknown variable "${name}" — no such variable in this template.`
            : !eligible
            ? `"${name}" resolves AFTER chip generation. Only LLM_DRAFT and SYSTEM_GENERATED variables can be referenced.`
            : `${name} (${known.source})`;
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
          + Add variable
        </button>
      </div>
      {isOpen && (
        <div className="relative">
          <div className="absolute z-20 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
            <div className="border-b border-border bg-surface-muted/60 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
              Pick a variable
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
                  ? `No variables match "${filter}".`
                  : available.length === 0
                  ? 'No more eligible variables left to add.'
                  : 'No eligible variables.'}
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
                        {v.source}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-muted">
                      {v.template_property_marker || '(no sample value)'}
                    </p>
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

export default DependentVariablesPicker;
