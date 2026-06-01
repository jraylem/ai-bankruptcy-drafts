import React, { useEffect, useMemo, useRef, useState } from 'react';
import Lottie from 'lottie-react';
import {
  FiCheck,
  FiCheckSquare,
  FiChevronDown,
  FiChevronLeft,
  FiChevronRight,
  FiFile,
  FiPlus,
  FiSearch,
  FiUploadCloud,
  FiX,
  FiZap,
} from 'react-icons/fi';
import dryRunAnimation from '@/assets/lottie/dry-run.json';
import { DatePicker, Modal } from '@/components/common';
import { DateRangePicker } from '@/components/common/DateRangePicker';
import { detectDateFormat } from '@/utils/studio/detectDateFormat';
import { strftime } from '@/utils/studio/strftime';
import type { AwaitingDraftState } from '@/hooks/useDraftingPersistence';
import { studioApi } from '@/services/studio.service';
import type {
  AwaitingInputResult,
  DropdownOption,
  PendingDropdown,
  PendingDropdownFromConstants,
  PendingGroupDropdown,
  PendingMultiSelect,
  PendingRecoChips,
  PendingUserInput,
  PendingUserInputDate,
  PendingUserInputPlainText,
  PendingUserInputWithDocs,
  UserSelection,
} from '@/types/studio';

interface AwaitingInputModalProps {
  isOpen: boolean;
  awaiting: AwaitingInputResult | null;
  picks: AwaitingDraftState;
  onPicksChange: (updater: (prev: AwaitingDraftState) => AwaitingDraftState) => void;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (picks: Record<string, UserSelection>) => void;
}

const optionLabel = (opt: DropdownOption): string =>
  opt.display_value ?? `${opt.left} - ${opt.right}`;

const MAX_SUPPORTING_FILES = 10;

// Mirrors the studio page's DRY_RUN_PHRASES — reused here so the
// AwaitingInputModal's "Finalizing…" state matches the pre-pause loader.
const FINALIZE_PHRASES: Array<[string, string]> = [
  ['Resolving', 'the fields'],
  ['Fetching', 'the sources'],
  ['Cross-referencing', 'the record'],
  ['Querying', 'the docket'],
  ['Construing', 'the statute'],
  ['Marshalling', 'the evidence'],
  ['Stipulating', 'the facts'],
  ['Annotating', 'the margins'],
  ['Redlining', 'the draft'],
  ['Filing', 'the caption'],
  ['Compiling', 'the brief'],
  ['Certifying', 'the signature'],
];

const isKeyFilled = (
  key: string,
  pending: PendingUserInput,
  draft: AwaitingDraftState
): boolean => {
  switch (pending.kind) {
    case 'group_dropdown':
      return draft.groupDropdown[key] !== undefined;
    case 'reco_chips':
    case 'dropdown':
    case 'dropdown_from_constants':
    case 'user_input_plain_text':
    case 'user_input_date':
      return typeof draft.singleValue[key] === 'string' && draft.singleValue[key].length > 0;
    case 'user_input_with_docs': {
      const entry = draft.supportingDocs[key];
      return entry !== undefined && entry.user_text.trim().length > 0;
    }
    case 'multi_select': {
      const picks = draft.multiSelect[key] ?? [];
      const minP = pending.min_picks ?? 1;
      const maxP = pending.max_picks ?? null;
      if (picks.length < minP) return false;
      if (maxP !== null && maxP !== undefined && picks.length > maxP) return false;
      return true;
    }
  }
};

const isDraftComplete = (
  keys: string[],
  pendingInputs: Record<string, PendingUserInput>,
  draft: AwaitingDraftState
): boolean => keys.every((k) => isKeyFilled(k, pendingInputs[k], draft));

const unfilledKeys = (
  keys: string[],
  pendingInputs: Record<string, PendingUserInput>,
  draft: AwaitingDraftState
): string[] => keys.filter((k) => !isKeyFilled(k, pendingInputs[k], draft));

const buildPicks = (
  keys: string[],
  pendingInputs: Record<string, PendingUserInput>,
  draft: AwaitingDraftState
): Record<string, UserSelection> => {
  const picks: Record<string, UserSelection> = {};
  for (const k of keys) {
    const p = pendingInputs[k];
    switch (p.kind) {
      case 'group_dropdown': {
        const idx = draft.groupDropdown[k];
        const opt = p.options[idx];
        picks[k] = { left: opt.left, right: opt.right };
        break;
      }
      case 'reco_chips':
      case 'dropdown':
      case 'dropdown_from_constants':
      case 'user_input_plain_text':
      case 'user_input_date': {
        picks[k] = { value: draft.singleValue[k] };
        break;
      }
      case 'user_input_with_docs': {
        const entry = draft.supportingDocs[k];
        picks[k] = {
          user_text: entry.user_text,
          file_urls: entry.file_urls,
        };
        break;
      }
      case 'multi_select': {
        picks[k] = { picked_values: draft.multiSelect[k] ?? [] };
        break;
      }
    }
  }
  return picks;
};

interface BlockHeaderProps {
  title: string;
  isFilled: boolean;
}

const BlockHeader: React.FC<BlockHeaderProps> = ({ title, isFilled }) => {
  return (
    <div className="relative flex items-center justify-between gap-3">
      <p className="text-base font-semibold text-text-secondary sm:text-lg">
        {title}
      </p>
      {isFilled && (
        <span
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-app-success-soft text-app-success-text"
          aria-label="Filled"
        >
          <CheckIcon className="h-4 w-4" />
        </span>
      )}
    </div>
  );
};

interface GroupDropdownBlockProps {
  pending: PendingGroupDropdown;
  propertyName: string;
  pickedIndex: number | undefined;
  onPick: (idx: number) => void;
  isFilled: boolean;
}

const GroupDropdownBlock: React.FC<GroupDropdownBlockProps> = ({
  pending,
  propertyName,
  pickedIndex,
  onPick,
  isFilled,
}) => (
  <>
    <BlockHeader
      title={pending.group_label || propertyName}
      isFilled={isFilled}
    />
    <p className="mt-3 text-[11px] font-semibold uppercase tracking-wider text-subtle">
      {pending.left_label} / {pending.right_label}
    </p>
    <ul className="mt-3 max-h-[280px] space-y-1.5 overflow-y-auto pr-0.5">
      {pending.options.map((opt, idx) => {
        const isPicked = pickedIndex === idx;
        return (
          <li key={idx}>
            <button
              type="button"
              onClick={() => onPick(idx)}
              className={`flex w-full items-start justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors ${
                isPicked
                  ? 'border-app-accent bg-app-accent-soft'
                  : 'border-border bg-surface hover:border-app-accent/40 hover:bg-surface-muted'
              }`}
            >
              <div className="min-w-0">
                <p
                  className={`text-sm ${
                    isPicked ? 'font-semibold text-app-accent-text' : 'text-text-secondary'
                  }`}
                >
                  {optionLabel(opt)}
                </p>
                {opt.display_value && (
                  <p className="mt-0.5 text-[11px] text-muted">
                    {opt.left} · {opt.right}
                  </p>
                )}
              </div>
              {isPicked && <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-app-accent-text" />}
            </button>
          </li>
        );
      })}
    </ul>
  </>
);

interface RecoChipsBlockProps {
  pending: PendingRecoChips;
  propertyName: string;
  value: string;
  onChange: (v: string) => void;
  isFilled: boolean;
}

const RecoChipsBlock: React.FC<RecoChipsBlockProps> = ({
  pending,
  propertyName,
  value,
  onChange,
  isFilled,
}) => (
  <>
    <BlockHeader
      title={pending.label || propertyName}
      isFilled={isFilled}
    />
    <p className="mt-1 text-xs text-muted">
      Pick a suggestion or edit the text freely.
    </p>

    <div className="mt-3">
      <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-subtle">
        Suggestions
      </h4>
      <div className="flex flex-col gap-1.5">
        {pending.chips.map((chip, idx) => {
          const isPicked = value === chip;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onChange(chip)}
              aria-pressed={isPicked}
              title={chip}
              className={`group flex w-full items-center gap-2.5 rounded-full border px-4 py-2 text-left text-xs leading-snug transition-all focus:outline-none focus:ring-2 focus:ring-app-accent-soft focus:ring-offset-1 ${
                isPicked
                  ? 'border-app-accent bg-app-accent-soft text-app-accent-text ring-1 ring-inset ring-app-accent/40'
                  : 'border-border bg-surface text-text-secondary hover:border-app-accent/40 hover:bg-app-accent-soft/30'
              }`}
            >
              {isPicked ? (
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-app-accent text-white">
                  <FiCheck className="h-2.5 w-2.5" strokeWidth={3} />
                </span>
              ) : (
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-subtle transition-colors group-hover:border-app-accent/50 group-hover:text-app-accent-text">
                  <FiPlus className="h-2.5 w-2.5" strokeWidth={2.5} />
                </span>
              )}
              <span className={`truncate ${isPicked ? 'font-medium' : ''}`}>
                {chip}
              </span>
            </button>
          );
        })}
      </div>
    </div>

    <div className="mt-4 rounded-2xl border border-app-accent/30 bg-gradient-to-br from-app-accent-soft/40 via-surface to-surface p-3 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_4px_12px_-4px_rgba(79,70,229,0.12)] ring-1 ring-inset ring-app-accent/10">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-md bg-app-accent-soft text-app-accent-text">
          <FiCheckSquare className="h-3 w-3" strokeWidth={2.5} />
        </span>
        <h4 className="text-xs font-semibold uppercase tracking-[0.08em] text-text-secondary">
          Your response
        </h4>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={6}
        className="block w-full resize-none rounded-xl border border-border bg-surface px-4 py-3 text-[13.5px] leading-[1.6] text-text-secondary shadow-sm transition-colors placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        placeholder="Select a suggestion above, or draft your own response here…"
      />

      <div className="mt-2 flex items-center gap-2.5 rounded-lg border border-app-accent/20 bg-app-accent-soft/40 px-3 py-2">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-app-accent text-white shadow-sm">
          <FiZap className="h-3 w-3" strokeWidth={2.5} />
        </span>
        <p className="min-w-0 flex-1 text-[11px] leading-snug text-text-secondary">
          <span className="font-semibold text-app-accent-text">AI Assistant:</span>{' '}
          We&rsquo;ll refine grammar and legal phrasing without changing the substance.
        </p>
      </div>
    </div>
  </>
);

interface DropdownBlockProps {
  pending: PendingDropdown | PendingDropdownFromConstants;
  propertyName: string;
  value: string;
  onChange: (v: string) => void;
  isFilled: boolean;
}

const DropdownBlock: React.FC<DropdownBlockProps> = ({
  pending,
  propertyName,
  value,
  onChange,
  isFilled,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(() => !value);
  const [search, setSearch] = useState<string>('');
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return pending.options;
    return pending.options.filter((opt) => opt.toLowerCase().includes(q));
  }, [search, pending.options]);

  useEffect(() => {
    if (!isOpen) return;
    setSearch('');
    const focusId = window.setTimeout(() => searchInputRef.current?.focus(), 0);
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    const onClick = (e: MouseEvent): void => {
      if (!containerRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onClick);
    return () => {
      window.clearTimeout(focusId);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onClick);
    };
  }, [isOpen]);

  const handlePick = (opt: string): void => {
    onChange(opt);
    setIsOpen(false);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>): void => {
    if (e.key === 'Enter' && filtered.length > 0) {
      e.preventDefault();
      handlePick(filtered[0]);
    }
  };

  return (
    <>
      <BlockHeader
        title={pending.label || propertyName}
        isFilled={isFilled}
      />
      {pending.options.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-border bg-surface-muted px-3 py-3 text-center text-xs text-muted">
          No options available for this field.
        </p>
      ) : (
        <div ref={containerRef} className="mt-4">
          <button
            type="button"
            onClick={() => setIsOpen((o) => !o)}
            aria-expanded={isOpen}
            aria-haspopup="listbox"
            className={`flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors hover:border-app-accent/60 ${
              value ? 'border-app-accent-soft bg-surface' : 'border-border bg-surface'
            }`}
          >
            <span
              className={`min-w-0 truncate ${
                value ? 'font-medium text-text-secondary' : 'text-muted'
              }`}
            >
              {value || 'Select an option…'}
            </span>
            <FiChevronDown
              className={`h-4 w-4 shrink-0 text-subtle transition-transform ${
                isOpen ? 'rotate-180' : ''
              }`}
            />
          </button>

          {isOpen && (
            <div className="mt-2 overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
              <div className="relative border-b border-border p-2">
                <FiSearch className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                  placeholder="Search…"
                  className="w-full rounded-md border border-border bg-surface-muted py-1.5 pl-8 pr-3 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                />
              </div>
              {filtered.length === 0 ? (
                <p className="px-3 py-4 text-center text-xs text-muted">
                  No matches for “{search}”.
                </p>
              ) : (
                <ul role="listbox" className="max-h-[240px] overflow-y-auto py-1">
                  {filtered.map((opt, idx) => {
                    const isPicked = value === opt;
                    return (
                      <li key={`${opt}-${idx}`} role="option" aria-selected={isPicked}>
                        <button
                          type="button"
                          onClick={() => handlePick(opt)}
                          className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors ${
                            isPicked
                              ? 'bg-app-accent-soft font-semibold text-app-accent-text'
                              : 'text-text-secondary hover:bg-surface-muted'
                          }`}
                        >
                          <span className="min-w-0 break-words">{opt}</span>
                          {isPicked && (
                            <CheckIcon className="h-4 w-4 shrink-0 text-app-accent-text" />
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
};

interface MultiSelectBlockProps {
  pending: PendingMultiSelect;
  propertyName: string;
  value: string[];
  onChange: (next: string[]) => void;
  isFilled: boolean;
}

const buildConstraintLabel = (pending: PendingMultiSelect, picked: number): string => {
  const minP = pending.min_picks ?? 1;
  const maxP = pending.max_picks ?? null;
  if (maxP === null || maxP === undefined) {
    if (minP === 0) return `Optional · ${picked} selected`;
    return `Select at least ${minP} · ${picked} selected`;
  }
  if (minP === maxP) return `Select exactly ${minP} · ${picked} selected`;
  if (minP === 0) return `Select up to ${maxP} (optional) · ${picked} selected`;
  return `Select ${minP}–${maxP} · ${picked} selected`;
};

const MultiSelectBlock: React.FC<MultiSelectBlockProps> = ({
  pending,
  propertyName,
  value,
  onChange,
  isFilled,
}) => {
  const maxP = pending.max_picks ?? null;
  const atMax = maxP !== null && maxP !== undefined && value.length >= maxP;
  const isPicked = (option: string): boolean => value.includes(option);
  const togglePick = (option: string): void => {
    if (isPicked(option)) {
      onChange(value.filter((p) => p !== option));
      return;
    }
    if (atMax) return;
    onChange([...value, option]);
  };
  const constraintLabel = buildConstraintLabel(pending, value.length);

  return (
    <>
      <BlockHeader title={pending.label || propertyName} isFilled={isFilled} />
      <div className="space-y-3">
        {pending.instruction && (
          <p className="text-xs leading-relaxed text-muted">{pending.instruction}</p>
        )}
        <p className="text-[11px] font-medium text-text-secondary">{constraintLabel}</p>
        {pending.options.length === 0 ? (
          <div className="rounded-lg border border-dashed border-app-warning-soft bg-app-warning-soft/30 px-3 py-3 text-xs text-app-warning-text">
            No matching options found in the case file. The variable will be
            skipped — re-run the draft after updating the case documents
            if you expected matches.
          </div>
        ) : (
          <ul role="listbox" aria-multiselectable="true" className="space-y-2">
            {pending.options.map((option, idx) => {
              const picked = isPicked(option);
              const disabled = !picked && atMax;
              // Multi-line example_format renders as bolded headline + muted lines.
              const lines = option.split('\n');
              const headline = lines[0] || '—';
              const secondaryLines = lines.slice(1).filter((l) => l.length > 0);
              return (
                <li
                  key={idx}
                  role="option"
                  aria-selected={picked}
                  aria-disabled={disabled}
                >
                  <button
                    type="button"
                    onClick={() => togglePick(option)}
                    disabled={disabled}
                    className={`flex w-full items-start justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                      picked
                        ? 'border-app-accent ring-2 ring-app-accent/40 bg-app-accent-soft'
                        : disabled
                          ? 'border-border bg-surface opacity-50 cursor-not-allowed'
                          : 'border-border bg-surface hover:border-app-accent/40 hover:bg-surface-muted'
                    }`}
                    title={
                      disabled
                        ? `Maximum ${maxP} reached. Deselect another to switch.`
                        : undefined
                    }
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-text-secondary">
                        {headline}
                      </p>
                      {secondaryLines.map((line, lineIdx) => (
                        <p key={lineIdx} className="mt-0.5 text-[11px] text-muted">
                          {line}
                        </p>
                      ))}
                    </div>
                    <span
                      className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                        picked
                          ? 'border-app-accent bg-app-accent text-white'
                          : 'border-border bg-surface'
                      }`}
                    >
                      {picked && <FiCheck className="h-3 w-3" />}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
};

interface PlainTextBlockProps {
  pending: PendingUserInputPlainText;
  propertyName: string;
  value: string;
  onChange: (v: string) => void;
  isFilled: boolean;
}

const isDateRangeShapedVariable = (propertyName: string): boolean => {
  const name = propertyName.toLowerCase();
  return /(^|_)(period|range|window|span|dates)($|_)/.test(name);
};

const isoToLocalDate = (iso: string): Date | null => {
  const parts = iso.split('-').map((s) => parseInt(s, 10));
  if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
  const [y, m, d] = parts as [number, number, number];
  return new Date(y, m - 1, d);
};

const PlainTextBlock: React.FC<PlainTextBlockProps> = ({
  pending,
  propertyName,
  value,
  onChange,
  isFilled,
}) => {
  const isDateRange = isDateRangeShapedVariable(propertyName);

  return (
    <>
      <BlockHeader title={pending.label || propertyName} isFilled={isFilled} />
      <div className="space-y-3">
        {isDateRange ? (
          <DateRangePicker
            value={value}
            onChange={onChange}
            placeholder={pending.placeholder || 'Select date range…'}
          />
        ) : (
          <textarea
            rows={5}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={pending.placeholder ?? ''}
            className="w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm leading-relaxed text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
        )}
        <div className="rounded-lg border border-dashed border-border bg-surface-muted/40 px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
            {isDateRange ? 'Format on output' : 'Example output'}
          </p>
          <p className="mt-1 text-xs italic leading-relaxed text-text-secondary">
            {pending.example_output_sentence}
          </p>
          <p className="mt-1.5 text-[10px] text-subtle">
            {isDateRange
              ? 'The selected range fills the placeholder as prose (e.g. "April 1, 2026 to April 15, 2026"). The heal step preserves this shape when example_output_sentence follows the same pattern.'
              : 'Your text will be tone-matched to this skeleton sentence before it fills the placeholder. Specific facts come from your input.'}
          </p>
        </div>
      </div>
    </>
  );
};

interface DateInputBlockProps {
  pending: PendingUserInputDate;
  propertyName: string;
  value: string;
  onChange: (v: string) => void;
  isFilled: boolean;
}

const DateInputBlock: React.FC<DateInputBlockProps> = ({
  pending,
  propertyName,
  value,
  onChange,
  isFilled,
}) => {
  // Round-trip the stored formatted value back to ISO so the picker
  // preselects when the user navigates back via the wizard. The stored
  // string was produced by strftime(picked, pending.format), so
  // detectDateFormat parses it back to an ISO sample.
  const valueDate = useMemo(() => detectDateFormat(value), [value]);
  const pickedIso = valueDate?.sampleIso ?? '';

  const handlePickDate = (iso: string): void => {
    if (!iso) {
      onChange('');
      return;
    }
    const dt = isoToLocalDate(iso);
    if (!dt) return;
    onChange(strftime(dt, pending.format));
  };

  return (
    <>
      <BlockHeader title={pending.label || propertyName} isFilled={isFilled} />
      <div className="space-y-3">
        <DatePicker
          value={pickedIso}
          onChange={handlePickDate}
          mode="date"
          placeholder={pending.placeholder || 'Pick a date…'}
          captionLayout="dropdown"
          fromYear={1900}
          toYear={new Date().getFullYear()}
        />
        {value && (
          <div className="rounded-lg border border-dashed border-border bg-surface-muted/40 px-3 py-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
              Will render as
            </p>
            <p className="mt-1 font-mono text-xs text-text-secondary">
              {value}
            </p>
          </div>
        )}
      </div>
    </>
  );
};

interface SupportingDocsBlockProps {
  caseId: string;
  pending: PendingUserInputWithDocs;
  propertyName: string;
  entry: { user_text: string; file_urls: string[] } | undefined;
  onChange: (entry: { user_text: string; file_urls: string[] }) => void;
  isFilled: boolean;
}

const SupportingDocsBlock: React.FC<SupportingDocsBlockProps> = ({
  caseId,
  pending,
  propertyName,
  entry,
  onChange,
  isFilled,
}) => {
  const userText = entry?.user_text ?? '';
  const fileUrls = entry?.file_urls ?? [];
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedFilenames, setUploadedFilenames] = useState<Record<string, string>>({});
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  const accept = useMemo(
    () => pending.accepted_file_types.map((ext) => `.${ext}`).join(','),
    [pending.accepted_file_types]
  );

  const handleFiles = async (files: FileList | null): Promise<void> => {
    if (!files || files.length === 0) return;
    setUploadError(null);
    const remaining = MAX_SUPPORTING_FILES - fileUrls.length;
    if (remaining <= 0) {
      setUploadError(`Maximum ${MAX_SUPPORTING_FILES} files allowed.`);
      return;
    }
    const capped = Array.from(files).slice(0, remaining);
    if (capped.length < files.length) {
      setUploadError(
        `Only ${remaining} more file${remaining === 1 ? '' : 's'} allowed — extras were skipped.`
      );
    }
    setIsUploading(true);
    const result = await studioApi.uploadSupportingDocs(caseId, capped);
    setIsUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (!result.data) {
      setUploadError(result.error ?? 'Upload failed');
      return;
    }
    const newUrls = result.data.map((r) => r.file_url);
    const nameByUrl: Record<string, string> = {};
    for (const r of result.data) nameByUrl[r.file_url] = r.filename;
    setUploadedFilenames((prev) => ({ ...prev, ...nameByUrl }));
    onChange({
      user_text: userText,
      file_urls: [...fileUrls, ...newUrls],
    });
  };

  const removeFileUrl = (idx: number): void => {
    onChange({
      user_text: userText,
      file_urls: fileUrls.filter((_, i) => i !== idx),
    });
  };

  const displayName = (url: string): string => {
    const known = uploadedFilenames[url];
    if (known) return known;
    const parts = url.split('/');
    return parts[parts.length - 1] || url;
  };

  const onBrowseClick = (): void => fileInputRef.current?.click();

  const onDragOver = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };

  const onDragLeave = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    void handleFiles(e.dataTransfer.files);
  };

  const hasFiles = fileUrls.length > 0;

  return (
    <>
      <BlockHeader
        title={pending.label || propertyName}
        isFilled={isFilled}
      />
      <textarea
        value={userText}
        onChange={(e) =>
          onChange({ user_text: e.target.value, file_urls: fileUrls })
        }
        rows={3}
        className="mt-4 w-full resize-none rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        placeholder="Type your response here…"
      />

      <p className="mt-4 text-sm font-semibold text-text-secondary">
        Supporting Documents <span className="font-normal text-muted">(Optional)</span>:
      </p>

      <div className="mt-2 space-y-3 rounded-xl border border-border bg-surface-muted/40 p-3">
        <div className="flex items-start gap-3 rounded-lg border border-app-accent-soft bg-app-accent-soft/60 px-3 py-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface text-app-accent-text shadow-sm">
            <ZapIcon className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-app-accent-text">
              AI-Enhanced
            </p>
            <p className="mt-1 text-xs leading-5 text-text-secondary">
              Upload supporting documents like bank statements, receipts, or pay records
              and the AI will use them to corroborate your explanation with details like
              dates and amounts.
            </p>
          </div>
        </div>

        {hasFiles && (
          <ul className="space-y-1.5">
            {fileUrls.map((url, idx) => (
              <li
                key={url}
                className="flex items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <FileIcon className="h-4 w-4 shrink-0 text-app-accent-text" />
                  <span className="truncate text-xs text-text-secondary">{displayName(url)}</span>
                </div>
                <button
                  type="button"
                  onClick={() => removeFileUrl(idx)}
                  disabled={isUploading}
                  aria-label={`Remove ${displayName(url)}`}
                  className="shrink-0 rounded p-1 text-subtle transition-colors hover:bg-app-danger-soft hover:text-app-danger-text disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <FiX className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {fileUrls.length < MAX_SUPPORTING_FILES && (
          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={onBrowseClick}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onBrowseClick();
              }
            }}
            className={`flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-5 text-center transition-colors ${
              isDragOver
                ? 'border-app-accent bg-app-accent-soft'
                : 'border-border bg-surface hover:border-app-accent/60 hover:bg-app-accent-soft/40'
            } ${isUploading ? 'pointer-events-none opacity-60' : ''}`}
          >
            <FiUploadCloud className="h-7 w-7 text-subtle" />
            <p className="text-sm font-medium text-text-secondary">
              {isUploading ? 'Uploading…' : 'Click to browse or drag and drop'}
            </p>
            <p className="text-xs text-muted">
              {pending.accepted_file_types.map((e) => e.toUpperCase()).join(', ')}{' '}
              ({fileUrls.length}/{MAX_SUPPORTING_FILES} files)
            </p>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={accept}
          onChange={(e) => void handleFiles(e.target.files)}
          disabled={isUploading}
          className="hidden"
        />
        {uploadError && (
          <p className="rounded border border-app-danger-soft bg-app-danger-soft px-2 py-1.5 text-[11px] text-app-danger-text">
            {uploadError}
          </p>
        )}
      </div>
    </>
  );
};

const CheckIcon: React.FC<{ className?: string }> = ({ className }) => (
  <FiCheck className={className ?? 'h-4 w-4'} />
);

const FileIcon: React.FC<{ className?: string }> = ({ className }) => (
  <FiFile className={className ?? 'h-4 w-4'} />
);

const ZapIcon: React.FC<{ className?: string }> = ({ className }) => (
  <FiZap className={className ?? 'h-4 w-4'} />
);

export const AwaitingInputModal: React.FC<AwaitingInputModalProps> = ({
  isOpen,
  awaiting,
  picks,
  onPicksChange,
  isSubmitting,
  onCancel,
  onSubmit,
}) => {
  // Step order in the wizard must match the order the author set up in the
  // studio sidebar (i.e. the docx render order), not whatever order the BE
  // happens to serialize `pending_inputs` in. The awaiting envelope already
  // carries `template_spec` as the canonical ordering — walk it first, then
  // append any pending keys that are missing from it as a safety net.
  const keys = useMemo(() => {
    if (!awaiting) return [];
    const pendingKeys = Object.keys(awaiting.pending_inputs);
    const spec = awaiting.template_spec;
    if (!spec || spec.length === 0) return pendingKeys;
    const seen = new Set<string>();
    const ordered: string[] = [];
    for (const v of spec) {
      const k = v.template_variable;
      if (k && k in awaiting.pending_inputs && !seen.has(k)) {
        ordered.push(k);
        seen.add(k);
      }
    }
    for (const k of pendingKeys) {
      if (!seen.has(k)) ordered.push(k);
    }
    return ordered;
  }, [awaiting]);

  // Fast-lane local state. The parent owns `picks` (often via heavy hosts —
  // the 982-line studio page, the drafting page with localStorage persistence)
  // and syncing to it on every keystroke makes plain-text inputs lag because
  // the parent's entire subtree reconciles per character. We mirror picks
  // locally so typing only re-renders the modal, then push to the parent on
  // a 300ms debounce. Re-hydrate from parent only when the run_id changes
  // (new pause envelope = new fresh state).
  const runId = awaiting?.run_id;
  const [localPicks, setLocalPicks] = useState<AwaitingDraftState>(picks);
  useEffect(() => {
    setLocalPicks(picks);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);
  const onPicksChangeRef = useRef(onPicksChange);
  useEffect(() => {
    onPicksChangeRef.current = onPicksChange;
  }, [onPicksChange]);
  useEffect(() => {
    if (localPicks === picks) return;
    const timer = setTimeout(() => {
      onPicksChangeRef.current(() => localPicks);
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localPicks]);

  const allPicked = useMemo(
    () => (awaiting ? isDraftComplete(keys, awaiting.pending_inputs, localPicks) : false),
    [keys, awaiting, localPicks]
  );

  const missingKeys = useMemo(
    () => (awaiting ? unfilledKeys(keys, awaiting.pending_inputs, localPicks) : []),
    [keys, awaiting, localPicks]
  );

  const filledCount = keys.length - missingKeys.length;

  const [phraseIndex, setPhraseIndex] = useState<number>(0);
  useEffect(() => {
    if (!isSubmitting) return;
    setPhraseIndex(0);
    const id = window.setInterval(() => {
      setPhraseIndex((i) => (i + 1) % FINALIZE_PHRASES.length);
    }, 1800);
    return () => window.clearInterval(id);
  }, [isSubmitting]);

  // Wizard state — reset to step 0 on every new awaiting envelope. BE's run_id
  // changes on any new pause (initial pause, multi-stage resume), which is the
  // signal to reset.
  const [currentStep, setCurrentStep] = useState<number>(0);
  useEffect(() => {
    setCurrentStep(0);
  }, [runId]);

  if (!awaiting) return null;

  const safeStep = Math.min(Math.max(currentStep, 0), Math.max(keys.length - 1, 0));
  const activeKey = keys[safeStep];
  const activePending = activeKey ? awaiting.pending_inputs[activeKey] : null;
  const activeFilled =
    activeKey && activePending ? isKeyFilled(activeKey, activePending, localPicks) : false;
  const isLastStep = safeStep >= keys.length - 1;
  const isFirstStep = safeStep === 0;

  const handleSubmit = (): void => {
    // Flush any pending debounced sync before submitting so the parent's
    // `picks` reflects the user's final input on resume.
    onPicksChange(() => localPicks);
    onSubmit(buildPicks(keys, awaiting.pending_inputs, localPicks));
  };

  const handleNext = (): void => {
    if (!activeFilled) return;
    if (isLastStep) {
      handleSubmit();
      return;
    }
    setCurrentStep((s) => Math.min(s + 1, keys.length - 1));
  };

  const handleBack = (): void => {
    setCurrentStep((s) => Math.max(s - 1, 0));
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onCancel}
      size="2xl"
      showCloseButton={false}
      closeOnBackdropClick={!isSubmitting}
      closeOnEscape={!isSubmitting}
    >
      <div className="flex max-h-[min(95vh,960px)] flex-col">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-5 py-4 sm:px-6 sm:py-5">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-app-accent-soft text-app-accent-text">
                <FiCheckSquare className="h-4 w-4" />
              </span>
              <h2 className="text-base font-semibold text-text-secondary sm:text-lg">
                Complete your draft inputs
              </h2>
            </div>
            <p className="mt-1 text-xs text-muted sm:text-sm">
              {isSubmitting
                ? 'Finalizing the draft — please don’t close this window.'
                : keys.length > 1
                  ? `Step ${safeStep + 1} of ${keys.length} · ${filledCount} of ${keys.length} ready`
                  : `${filledCount} of ${keys.length} ${keys.length === 1 ? 'field' : 'fields'} ready.`}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            aria-label="Close"
            className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-surface-muted hover:text-text-secondary disabled:cursor-not-allowed disabled:opacity-40"
          >
            <FiX className="h-5 w-5" />
          </button>
        </header>

        {!isSubmitting && keys.length > 1 && (
          <div className="shrink-0 border-b border-border bg-surface-muted/60 px-4 py-3 sm:px-6">
            <div className="flex flex-wrap items-center justify-center gap-1.5">
              {keys.map((k, idx) => {
                const filled = isKeyFilled(k, awaiting.pending_inputs[k], localPicks);
                const isCurrent = idx === safeStep;
                const label =
                  awaiting.pending_inputs[k].kind === 'group_dropdown'
                    ? (awaiting.pending_inputs[k] as PendingGroupDropdown).group_label || k
                    : ((awaiting.pending_inputs[k] as
                        | PendingRecoChips
                        | PendingDropdown
                        | PendingDropdownFromConstants
                        | PendingUserInputWithDocs
                        | PendingMultiSelect).label || k);
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setCurrentStep(idx)}
                    className={`group flex w-28 max-w-full flex-col items-center gap-1 rounded-2xl px-2 py-1.5 text-center text-[11px] font-medium leading-snug transition-colors ${
                      isCurrent
                        ? 'bg-app-accent-soft text-app-accent-text'
                        : filled
                          ? 'text-app-success-text hover:bg-surface-muted'
                          : 'text-muted hover:bg-surface-muted'
                    }`}
                  >
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold ring-1 ${
                        isCurrent
                          ? 'bg-app-accent text-white ring-app-accent'
                          : filled
                            ? 'bg-app-success-soft text-app-success-text ring-app-success-soft'
                            : 'bg-surface text-muted ring-border'
                      }`}
                    >
                      {filled && !isCurrent ? (
                        <CheckIcon className="h-3 w-3" />
                      ) : (
                        idx + 1
                      )}
                    </span>
                    <span className="break-words">{label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {isSubmitting ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-8 sm:py-10">
            <Lottie
              animationData={dryRunAnimation}
              loop
              autoplay
              className="h-48 w-full max-w-md sm:h-56"
            />
            <p
              key={phraseIndex}
              className="animate-verb-in text-center text-lg font-semibold text-text-secondary sm:text-xl"
            >
              {FINALIZE_PHRASES[phraseIndex][0]} {FINALIZE_PHRASES[phraseIndex][1]}…
            </p>
            <p className="max-w-sm text-center text-xs text-muted sm:text-sm">
              Running the enhancement agent and assembling the final draft.
            </p>
          </div>
        ) : null}

        {!isSubmitting && activeKey && activePending ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-surface-muted/30 px-4 py-3 sm:px-6 sm:py-4">
            <div
              key={activeKey}
              className={`rounded-xl border bg-surface p-4 shadow-sm transition-colors sm:p-5 ${
                activeFilled ? 'border-app-success-soft' : 'border-border'
              }`}
            >
              {activePending.kind === 'group_dropdown' && (
                <GroupDropdownBlock
                  pending={activePending}
                  propertyName={activeKey}
                  pickedIndex={localPicks.groupDropdown[activeKey]}
                  onPick={(idx) =>
                    setLocalPicks((prev) => ({
                      ...prev,
                      groupDropdown: { ...prev.groupDropdown, [activeKey]: idx },
                    }))
                  }
                  isFilled={activeFilled}
                />
              )}
              {activePending.kind === 'reco_chips' && (
                <RecoChipsBlock
                  pending={activePending}
                  propertyName={activeKey}
                  value={localPicks.singleValue[activeKey] ?? ''}
                  onChange={(v) =>
                    setLocalPicks((prev) => ({
                      ...prev,
                      singleValue: { ...prev.singleValue, [activeKey]: v },
                    }))
                  }
                  isFilled={activeFilled}
                />
              )}
              {(activePending.kind === 'dropdown' ||
                activePending.kind === 'dropdown_from_constants') && (
                <DropdownBlock
                  pending={activePending}
                  propertyName={activeKey}
                  value={localPicks.singleValue[activeKey] ?? ''}
                  onChange={(v) =>
                    setLocalPicks((prev) => ({
                      ...prev,
                      singleValue: { ...prev.singleValue, [activeKey]: v },
                    }))
                  }
                  isFilled={activeFilled}
                />
              )}
              {activePending.kind === 'user_input_with_docs' && (
                <SupportingDocsBlock
                  caseId={awaiting.case_id}
                  pending={activePending}
                  propertyName={activeKey}
                  entry={localPicks.supportingDocs[activeKey]}
                  onChange={(entry) =>
                    setLocalPicks((prev) => ({
                      ...prev,
                      supportingDocs: { ...prev.supportingDocs, [activeKey]: entry },
                    }))
                  }
                  isFilled={activeFilled}
                />
              )}
              {activePending.kind === 'user_input_plain_text' && (
                <PlainTextBlock
                  pending={activePending}
                  propertyName={activeKey}
                  value={localPicks.singleValue[activeKey] ?? ''}
                  onChange={(v) =>
                    setLocalPicks((prev) => ({
                      ...prev,
                      singleValue: { ...prev.singleValue, [activeKey]: v },
                    }))
                  }
                  isFilled={activeFilled}
                />
              )}
              {activePending.kind === 'user_input_date' && (
                <DateInputBlock
                  pending={activePending}
                  propertyName={activeKey}
                  value={localPicks.singleValue[activeKey] ?? ''}
                  onChange={(v) =>
                    setLocalPicks((prev) => ({
                      ...prev,
                      singleValue: { ...prev.singleValue, [activeKey]: v },
                    }))
                  }
                  isFilled={activeFilled}
                />
              )}
              {activePending.kind === 'multi_select' && (
                <MultiSelectBlock
                  pending={activePending}
                  propertyName={activeKey}
                  value={localPicks.multiSelect[activeKey] ?? []}
                  onChange={(next) =>
                    setLocalPicks((prev) => ({
                      ...prev,
                      multiSelect: { ...prev.multiSelect, [activeKey]: next },
                    }))
                  }
                  isFilled={activeFilled}
                />
              )}
            </div>
          </div>
        ) : null}

        <footer className="flex shrink-0 flex-col-reverse gap-2 border-t border-border bg-surface px-5 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:px-6 sm:py-4">
          <div className="flex min-w-0 flex-1 items-center gap-2 text-[11px] text-muted sm:text-xs">
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              className="rounded-lg border border-border px-3 py-2 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm"
            >
              Cancel
            </button>
          </div>
          <div className="flex shrink-0 items-center justify-end gap-2">
            {keys.length > 1 && (
              <button
                type="button"
                onClick={handleBack}
                disabled={isFirstStep || isSubmitting}
                className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-40 sm:text-sm"
              >
                <FiChevronLeft className="h-4 w-4" />
                Back
              </button>
            )}
            <button
              type="button"
              onClick={handleNext}
              disabled={
                isSubmitting ||
                !activeFilled ||
                (isLastStep && !allPicked)
              }
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-all hover:from-indigo-700 hover:to-purple-700 disabled:cursor-not-allowed disabled:opacity-50 sm:text-sm"
            >
              {isSubmitting && (
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth={3} strokeOpacity={0.25} />
                  <path
                    d="M12 2a10 10 0 0 1 10 10"
                    stroke="currentColor"
                    strokeWidth={3}
                    strokeLinecap="round"
                  />
                </svg>
              )}
              {isSubmitting
                ? 'Finalizing…'
                : isLastStep
                  ? 'Complete Draft'
                  : 'Next'}
              {!isSubmitting && !isLastStep && (
                <FiChevronRight className="h-4 w-4" />
              )}
            </button>
          </div>
        </footer>
      </div>
    </Modal>
  );
};

export default AwaitingInputModal;
