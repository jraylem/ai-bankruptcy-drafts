import React, { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';
import type { FieldSource } from '@/types/studio';
import { isEligibleForReference } from './_referenceability';

const OPEN_REF_PATTERN = /\{\{([a-z_][a-z0-9_]*)?$/;
const REF_PATTERN = /\{\{([a-z_][a-z0-9_]*)\}\}/g;

interface VariableReferenceInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  multiline?: boolean;
  inputClassName?: string;
  /** Source of the variable whose query this input is editing. Drives
   *  contextual eligibility — LLM_DRAFT referencers may reference
   *  USER_INPUT-rooted targets (BE's Path B wave-B reach). */
  referencerSource?: FieldSource | null;
}

type RefState = { name: string; isKnown: boolean; isEligible: boolean };

export const VariableReferenceInput = ({
  value,
  onChange,
  placeholder,
  ariaLabel,
  multiline,
  inputClassName,
  referencerSource = null,
}: VariableReferenceInputProps): ReactElement => {
  const templateSpec = useStudioStore((s) => s.templateSpec);

  const byName = useMemo(
    () => new Map(templateSpec.map((v) => [v.template_variable, v])),
    [templateSpec]
  );

  const eligibleVars = useMemo(
    () => templateSpec.filter((v) => isEligibleForReference(v, byName, referencerSource)),
    [templateSpec, byName, referencerSource]
  );

  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [openSource, setOpenSource] = useState<'type' | 'button'>('type');
  const [filter, setFilter] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const filtered = useMemo(() => {
    if (!filter) return eligibleVars;
    const f = filter.toLowerCase();
    return eligibleVars.filter((v) => v.template_variable.toLowerCase().includes(f));
  }, [filter, eligibleVars]);

  useEffect(() => {
    if (openSource === 'button' && isOpen) return;
    const m = OPEN_REF_PATTERN.exec(value);
    if (m) {
      setIsOpen(true);
      setOpenSource('type');
      setFilter(m[1] || '');
      setSelectedIndex(0);
    } else if (openSource === 'type') {
      setIsOpen(false);
      setFilter('');
    }
  }, [value, openSource, isOpen]);

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

  const insertReference = (variableName: string): void => {
    let next: string;
    if (openSource === 'type') {

      next = value.replace(OPEN_REF_PATTERN, `{{${variableName}}}`);
    } else {

      const sep = value.length > 0 && !value.endsWith(' ') ? ' ' : '';
      next = `${value}${sep}{{${variableName}}}`;
    }
    onChange(next);
    setIsOpen(false);
    setFilter('');
    inputRef.current?.focus();
  };

  const removeReference = (name: string): void => {

    const pattern = new RegExp(`\\s?\\{\\{${name}\\}\\}\\s?`);
    const next = value.replace(pattern, (match) => {

      return match.startsWith(' ') && match.endsWith(' ') ? ' ' : '';
    });
    onChange(next);
    inputRef.current?.focus();
  };

  const openButtonPicker = (): void => {
    setOpenSource('button');
    setIsOpen(true);
    setFilter('');
    setSelectedIndex(0);
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
      if (target) insertReference(target.template_variable);
      return;
    }
  };

  const refs: RefState[] = useMemo(() => {
    const out: RefState[] = [];
    for (const m of value.matchAll(REF_PATTERN)) {
      const name = m[1]!;
      const known = templateSpec.find((v) => v.template_variable === name);
      const eligible =
        known !== undefined && isEligibleForReference(known, byName, referencerSource);
      out.push({ name, isKnown: known !== undefined, isEligible: eligible });
    }
    return out;
  }, [value, templateSpec, byName, referencerSource]);

  const hasIssues = refs.some((r) => !r.isKnown || !r.isEligible);

  const previewTokens = useMemo(() => {
    if (refs.length === 0) return [];
    const tokens: { type: 'text' | 'ref'; value: string; ref?: RefState }[] = [];
    let lastIdx = 0;
    let refIdx = 0;
    for (const m of value.matchAll(REF_PATTERN)) {
      const start = m.index ?? 0;
      if (start > lastIdx) {
        tokens.push({ type: 'text', value: value.slice(lastIdx, start) });
      }
      tokens.push({ type: 'ref', value: m[1]!, ref: refs[refIdx] });
      lastIdx = start + m[0].length;
      refIdx++;
    }
    if (lastIdx < value.length) {
      tokens.push({ type: 'text', value: value.slice(lastIdx) });
    }
    return tokens;
  }, [value, refs]);

  const baseInputClass =
    inputClassName ??
    'w-full rounded-lg border border-border bg-surface py-2 pl-3 pr-12 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft';

  return (
    <div className="space-y-1.5" ref={containerRef}>
      <div className="relative">
        {multiline ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            rows={2}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            aria-label={ariaLabel}
            className={baseInputClass}
          />
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            aria-label={ariaLabel}
            className={baseInputClass}
          />
        )}
        <button
          type="button"
          onClick={openButtonPicker}
          aria-label="Insert variable reference"
          title="Insert variable reference (or type {{ )"
          className={`absolute right-1.5 ${
            multiline ? 'top-1.5' : 'top-1/2 -translate-y-1/2'
          } inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-app-accent-soft hover:text-app-accent-text focus:outline-none focus:ring-2 focus:ring-app-accent-soft`}
        >
          <span aria-hidden className="font-mono text-[11px]">{'{{}}'}</span>
          <span className="hidden sm:inline">Variable</span>
        </button>
        {isOpen && (
          <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
            <div className="border-b border-border bg-surface-muted/60 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
              Insert variable
              {filter && <span className="text-text-secondary"> · "{filter}"</span>}
            </div>
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted">
                {filter
                  ? `No variables match "${filter}".`
                  : 'No eligible variables in this template yet.'}{' '}
                Only LLM_DRAFT and SYSTEM_GENERATED variables can be referenced
                (resolved before the user-input pause).
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
                      insertReference(v.template_variable);
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
        )}
      </div>

      {refs.length > 0 && (
        <div
          className={`rounded-md border px-2.5 py-2 text-xs ${
            hasIssues
              ? 'border-app-warning-soft bg-app-warning-soft/40'
              : 'border-border bg-surface-muted/40'
          }`}
        >
          <p
            className={`text-[10px] font-semibold uppercase tracking-wider ${
              hasIssues ? 'text-app-warning-text' : 'text-muted'
            }`}
          >
            Preview at draft time · click ✕ on a pill to remove
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1 break-all font-mono text-text-secondary">
            {previewTokens.map((tok, idx) =>
              tok.type === 'text' ? (
                <span key={`t-${idx}`} className="whitespace-pre-wrap">
                  {tok.value}
                </span>
              ) : (
                <ReferencePill
                  key={`r-${idx}-${tok.value}`}
                  name={tok.value}
                  ref_={tok.ref!}
                  marker={
                    templateSpec.find((v) => v.template_variable === tok.value)
                      ?.template_property_marker || null
                  }
                  onRemove={() => removeReference(tok.value)}
                />
              )
            )}
          </div>
        </div>
      )}
    </div>
  );
};

interface ReferencePillProps {
  name: string;
  ref_: RefState;
  marker: string | null;
  onRemove: () => void;
}

const ReferencePill = ({ name, ref_, marker, onRemove }: ReferencePillProps): ReactElement => {
  const tone = !ref_.isKnown
    ? 'border-app-warning-soft bg-app-warning-soft text-app-warning-text'
    : !ref_.isEligible
    ? 'border-app-warning-soft bg-app-warning-soft/70 text-app-warning-text'
    : 'border-app-accent-soft bg-app-accent-soft text-app-accent-text';
  const label = !ref_.isKnown
    ? `unknown: ${name}`
    : !ref_.isEligible
    ? `ineligible: ${name}`
    : marker || name;
  const tooltip = !ref_.isKnown
    ? `Unknown variable "${name}" — no such variable in this template.`
    : !ref_.isEligible
    ? `"${name}" resolves AFTER this query fires. Only LLM_DRAFT and SYSTEM_GENERATED variables can be referenced.`
    : `{{${name}}} → at draft time substituted with the resolved value (sample shown: "${marker || '(no sample)'}").`;

  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs ${tone}`}
    >
      <span aria-hidden className="text-[10px]">◆</span>
      <span className="font-mono">{label}</span>
      <button
        type="button"
        aria-label={`Remove reference {{${name}}}`}
        onClick={(e) => {
          e.preventDefault();
          onRemove();
        }}
        className="rounded-sm px-0.5 leading-none hover:bg-black/10"
      >
        ×
      </button>
    </span>
  );
};

export default VariableReferenceInput;
