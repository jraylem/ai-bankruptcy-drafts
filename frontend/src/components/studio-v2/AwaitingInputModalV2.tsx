import { useEffect, useMemo, useRef, useState } from 'react';
import type { DragEvent, KeyboardEvent } from 'react';
import {
  FiCalendar,
  FiCheck,
  FiChevronLeft,
  FiChevronRight,
  FiFile,
  FiFileText,
  FiFilter,
  FiList,
  FiSearch,
  FiSliders,
  FiType,
  FiUploadCloud,
  FiUser,
  FiX,
  FiZap,
} from 'react-icons/fi';
import type { IconType } from 'react-icons';
import { Modal } from '@/components/common';
import { cn } from '@/utils';
import { uploadSupportingDocsV2 } from '@/services/studioV2.service';

const MAX_SUPPORTING_FILES = 10;
import type {
  PendingAttorneyPickV2,
  PendingAuthorDateV2,
  PendingAuthorDocsV2,
  PendingAuthorTextV2,
  PendingChipV2,
  PendingDropdownV2,
  PendingMultiSelectV2,
  PendingUserInputV2,
  UserSelectionV2,
} from '@/types/studio-v2';

interface AwaitingInputModalV2Props {
  isOpen: boolean;
  templateName: string;
  caseId: string | null;
  caseLabel?: string | null;
  caseName?: string | null;
  pendingInputs: Record<string, PendingUserInputV2>;
  onSubmit: (picks: Record<string, UserSelectionV2>) => Promise<void> | void;
  onCancel: () => void;
}

/**
 * Stepper-style pending-input picker for the v2 dry-run / draft flow.
 *
 * Layout:
 *   - Top: stepper rail (one chip per pending field, horizontal scroll
 *     on overflow). Active = filled accent; complete = soft accent;
 *     idle = ring-only.
 *   - Body: per-field workspace. List-shape pickers (dropdown /
 *     multi_select / attorney_pick) use a TWO-PANE layout — search +
 *     filterable list on the left, detail card (parsed option fields,
 *     raw_context blockquote) on the right. Form-shape pickers
 *     (chip / author_text / author_date / author_docs) get a single-pane
 *     centered form.
 *   - Footer: Back / "Next: <next field name>" or "Finish & render".
 *
 * Server is stateless during resume — FE owns picks state until
 * Finish & render fires `onSubmit`.
 */
export const AwaitingInputModalV2 = ({
  isOpen,
  templateName,
  caseId,
  caseLabel,
  caseName,
  pendingInputs,
  onSubmit,
  onCancel,
}: AwaitingInputModalV2Props) => {
  const entries = useMemo(
    () => Object.entries(pendingInputs).sort(([a], [b]) => a.localeCompare(b)),
    [pendingInputs],
  );

  const [picks, setPicks] = useState<Record<string, UserSelectionV2>>({});
  const [currentStep, setCurrentStep] = useState<number>(0);
  // Body components (e.g. AuthorDocsBody) can flip this while async work
  // is in-flight so the footer's Next / Finish & render button stays
  // disabled. Prevents submitting a pick mid-upload.
  const [bodyBusy, setBodyBusy] = useState<boolean>(false);

  const envelopeSignature = useMemo(
    () => entries.map(([k]) => k).join('|'),
    [entries],
  );
  useEffect(() => {
    if (isOpen) {
      setPicks({});
      setCurrentStep(0);
      setBodyBusy(false);
    }
  }, [isOpen, envelopeSignature]);

  // Stepping between fields cancels any pending busy flag from the
  // previous step — its uploader unmounts.
  useEffect(() => {
    setBodyBusy(false);
  }, [currentStep]);

  const setPick = (variable: string, sel: UserSelectionV2) => {
    setPicks((prev) => ({ ...prev, [variable]: sel }));
  };

  const { allFilled, filledCount } = useMemo(() => {
    let filled = 0;
    for (const [name, env] of entries) {
      if (isPickFilled(env, picks[name])) filled += 1;
    }
    return { allFilled: filled === entries.length, filledCount: filled };
  }, [entries, picks]);

  const safeStep = Math.min(Math.max(currentStep, 0), Math.max(entries.length - 1, 0));
  const activeEntry = entries[safeStep];
  const activeKey = activeEntry?.[0] ?? null;
  const activeEnvelope = activeEntry?.[1] ?? null;
  const activeFilled =
    activeKey && activeEnvelope
      ? isPickFilled(activeEnvelope, picks[activeKey])
      : false;
  const isLastStep = safeStep >= entries.length - 1;
  const isFirstStep = safeStep === 0;
  const nextEntry = !isLastStep ? entries[safeStep + 1] : null;
  const nextLabel = nextEntry ? (nextEntry[1].label || nextEntry[0]) : null;

  const handleSubmit = async () => {
    if (!allFilled || bodyBusy) return;
    await onSubmit(picks);
  };
  const handleNext = (): void => {
    if (!activeFilled || bodyBusy) return;
    if (isLastStep) {
      void handleSubmit();
      return;
    }
    setCurrentStep((s) => Math.min(s + 1, entries.length - 1));
  };
  const handleBack = (): void => {
    setCurrentStep((s) => Math.max(s - 1, 0));
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onCancel}
      size="3xl"
      showCloseButton={false}
      closeOnBackdropClick={false}
    >
      <div className="flex min-h-[min(82vh,720px)] max-h-[min(92vh,900px)] flex-col">
        <header className="flex shrink-0 items-start justify-between gap-3 border-b border-border px-6 py-5">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-app-accent-text">
              Almost there
            </p>
            <h2
              className="mt-1 text-lg font-semibold text-text-secondary"
              title={templateName}
            >
              A few things to confirm before we render
            </h2>
            {(caseName || caseLabel || templateName) && (
              <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
                {caseName && (
                  <span className="font-medium text-text-secondary">
                    {caseName}
                  </span>
                )}
                {caseName && caseLabel && (
                  <span className="text-subtle">·</span>
                )}
                {caseLabel && (
                  <span className="font-mono text-text-secondary">
                    {caseLabel}
                  </span>
                )}
                {(caseName || caseLabel) && templateName && (
                  <span className="text-subtle">·</span>
                )}
                {templateName && (
                  <span className="truncate">{templateName}</span>
                )}
              </p>
            )}
            <p className="mt-1 text-sm text-muted">
              {entries.length > 0 && activeEnvelope
                ? (
                  <>
                    <span className="font-medium text-text-secondary">
                      {filledCount} of {entries.length} ready
                    </span>
                    {' · '}
                    <span>{activeEnvelope.label || activeKey}</span>
                  </>
                )
                : 'Nothing to pick.'}
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-surface-muted hover:text-text-secondary"
          >
            <FiX className="h-5 w-5" />
          </button>
        </header>

        {entries.length > 1 && (
          <Stepper
            entries={entries}
            picks={picks}
            currentStep={safeStep}
            onJump={setCurrentStep}
          />
        )}

        <div className="min-h-0 flex-1 overflow-y-auto bg-surface-muted/30 px-6 py-5">
          {activeKey && activeEnvelope && (
            <PickerBody
              envelope={activeEnvelope}
              variableName={activeKey}
              pick={picks[activeKey]}
              onChange={(sel) => setPick(activeKey, sel)}
              disabled={false}
              caseId={caseId}
              onBusyChange={setBodyBusy}
            />
          )}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-surface px-6 py-4">
          <button
            type="button"
            onClick={isFirstStep ? onCancel : handleBack}
            className="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-semibold text-text-secondary hover:bg-surface-muted"
          >
            <FiChevronLeft className="h-4 w-4" />
            {isFirstStep ? 'Cancel' : 'Back'}
          </button>
          <button
            type="button"
            onClick={handleNext}
            disabled={!activeFilled || bodyBusy}
            title={bodyBusy ? 'Waiting for upload to finish…' : undefined}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold motion-safe:transition-opacity',
              activeFilled && !bodyBusy
                ? 'cursor-pointer bg-app-accent text-white hover:opacity-90'
                : 'cursor-not-allowed bg-surface-muted text-subtle',
            )}
          >
            {bodyBusy ? (
              <>
                Waiting for upload…
              </>
            ) : isLastStep ? (
              <>
                Finish &amp; render
                <FiCheck className="h-4 w-4" />
              </>
            ) : (
              <>
                Next: <span className="max-w-[10rem] truncate">{nextLabel}</span>
                <FiChevronRight className="h-4 w-4" />
              </>
            )}
          </button>
        </footer>
      </div>
    </Modal>
  );
};

// ─── stepper rail ────────────────────────────────────────────────────

const Stepper = ({
  entries,
  picks,
  currentStep,
  onJump,
}: {
  entries: Array<[string, PendingUserInputV2]>;
  picks: Record<string, UserSelectionV2>;
  currentStep: number;
  onJump: (i: number) => void;
}) => (
  <div className="shrink-0 border-b border-border bg-surface px-4 py-3 sm:px-6">
    <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-thin">
      {entries.map(([k, env], idx) => {
        const filled = isPickFilled(env, picks[k]);
        const isCurrent = idx === currentStep;
        const label = env.label || k;
        const KindIcon = kindIcon(env.kind);
        return (
          <button
            key={k}
            type="button"
            onClick={() => onJump(idx)}
            className={cn(
              'group inline-flex h-9 shrink-0 items-center gap-2 rounded-full px-3 text-xs font-medium motion-safe:transition-colors',
              isCurrent
                ? 'bg-app-accent text-white shadow-sm ring-1 ring-app-accent'
                : filled
                  ? 'bg-app-accent-soft/70 text-app-accent-text hover:bg-app-accent-soft'
                  : 'bg-surface text-muted ring-1 ring-inset ring-border hover:bg-surface-muted',
            )}
          >
            <span
              className={cn(
                'inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold',
                isCurrent
                  ? 'bg-white/20 text-white'
                  : filled
                    ? 'bg-app-accent text-white'
                    : 'bg-surface-muted text-muted',
              )}
            >
              {filled && !isCurrent ? (
                <FiCheck className="h-3 w-3" />
              ) : (
                idx + 1
              )}
            </span>
            <KindIcon className="h-3 w-3 opacity-70" />
            <span className="max-w-[10rem] truncate">{label}</span>
          </button>
        );
      })}
    </div>
  </div>
);

// ─── per-shape picker dispatch ───────────────────────────────────────

interface BodyProps {
  envelope: PendingUserInputV2;
  variableName: string;
  pick: UserSelectionV2 | undefined;
  onChange: (sel: UserSelectionV2) => void;
  disabled: boolean;
  caseId: string | null;
  // Bodies with async work in-flight (e.g. AuthorDocsBody during
  // upload) flip this on, then back off, so the modal's footer
  // Next / Finish button stays disabled until the work settles.
  onBusyChange: (busy: boolean) => void;
}

const PickerBody = ({ envelope, variableName, pick, onChange, disabled, caseId, onBusyChange }: BodyProps) => {
  const shared = { variableName, pick, onChange, disabled, caseId, onBusyChange };
  if (envelope.kind === 'dropdown') return <DropdownBody {...shared} envelope={envelope} />;
  if (envelope.kind === 'chip') return <ChipBody {...shared} envelope={envelope} />;
  if (envelope.kind === 'multi_select') return <MultiSelectBody {...shared} envelope={envelope} />;
  if (envelope.kind === 'author_text') return <AuthorTextBody {...shared} envelope={envelope} />;
  if (envelope.kind === 'author_date') return <AuthorDateBody {...shared} envelope={envelope} />;
  if (envelope.kind === 'author_docs') return <AuthorDocsBody {...shared} envelope={envelope} />;
  if (envelope.kind === 'attorney_pick') return <AttorneyPickBody {...shared} envelope={envelope} />;
  return null;
};

// ─── shared frames ───────────────────────────────────────────────────

const FieldHeading = ({
  label,
  helperText,
}: {
  label: string;
  helperText?: string;
}) => (
  <div className="mb-3">
    <h3 className="text-base font-semibold text-text-secondary">{label}</h3>
    {helperText && <p className="mt-0.5 text-sm text-muted">{helperText}</p>}
  </div>
);

const KindBadge = ({
  envelope,
  variableName,
}: {
  envelope: PendingUserInputV2;
  variableName: string;
}) => {
  const KindIcon = kindIcon(envelope.kind);
  return (
    <div className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-surface-muted px-2 py-0.5 text-[10px] text-subtle">
      <KindIcon className="h-3 w-3" />
      <span>{kindLabel(envelope.kind)}</span>
      <span className="text-subtle/60">·</span>
      <span className="font-mono">{variableName}</span>
    </div>
  );
};

// ─── dropdown (two-pane: filterable list + detail) ──────────────────

const DropdownBody = ({
  envelope, variableName, pick, onChange, disabled,
}: BodyProps & { envelope: PendingDropdownV2 }) => {
  const value = (pick && 'value' in pick) ? pick.value : '';
  const [query, setQuery] = useState('');
  const filtered = useMemo(
    () => filterOptions(envelope.options, query),
    [envelope.options, query],
  );
  const selectedIndex = envelope.options.findIndex((o) => o === value);
  const selectedRawContext = selectedIndex >= 0
    ? envelope.raw_contexts?.[selectedIndex] ?? null
    : null;

  return (
    <div className="space-y-3">
      <FieldHeading
        label={envelope.label || variableName}
        helperText={
          envelope.options.length > 0
            ? `One of ${envelope.options.length} candidate${envelope.options.length === 1 ? '' : 's'} extracted from the source.`
            : undefined
        }
      />

      {envelope.options.length === 0 ? (
        <EmptyExtractionState />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div className="md:col-span-3">
            <ListSearch query={query} onQuery={setQuery} count={envelope.options.length} disabled={disabled} />
            <div className="mt-2 max-h-[min(45vh,420px)] divide-y divide-border overflow-y-auto rounded-lg border border-border bg-surface">
              {filtered.length === 0 ? (
                <FilterEmptyState query={query} onClear={() => setQuery('')} />
              ) : (
                filtered.map(({ opt }) => {
                  const selected = value === opt;
                  return (
                    <ListRow
                      key={opt}
                      label={opt}
                      selected={selected}
                      disabled={disabled}
                      onClick={() => onChange({ value: opt })}
                      role="radio"
                    />
                  );
                })
              )}
            </div>
          </div>
          <div className="md:col-span-2">
            <DetailPane
              envelope={envelope}
              variableName={variableName}
              selectedLabel={value || null}
              rawContext={selectedRawContext}
            />
          </div>
        </div>
      )}
    </div>
  );
};

// ─── multi_select (two-pane, multi-checkbox) ────────────────────────

const MultiSelectBody = ({
  envelope, variableName, pick, onChange, disabled,
}: BodyProps & { envelope: PendingMultiSelectV2 }) => {
  const picked = (pick && 'picked_values' in pick) ? pick.picked_values : [];
  const pickedSet = new Set(picked);
  const toggle = (opt: string) => {
    const next = pickedSet.has(opt)
      ? picked.filter((v) => v !== opt)
      : [...picked, opt];
    onChange({ picked_values: next });
  };
  const [query, setQuery] = useState('');
  const filtered = useMemo(
    () => filterOptions(envelope.options, query),
    [envelope.options, query],
  );

  const pickRangeLabel = envelope.min_picks === envelope.max_picks
    ? `Pick exactly ${envelope.min_picks}`
    : `Pick ${envelope.min_picks}–${envelope.max_picks}`;

  return (
    <div className="space-y-3">
      <FieldHeading
        label={envelope.label || variableName}
        helperText={`${pickRangeLabel} · ${picked.length} picked of ${envelope.options.length} candidates.`}
      />

      {envelope.options.length === 0 ? (
        <EmptyExtractionState />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div className="md:col-span-3">
            <ListSearch query={query} onQuery={setQuery} count={envelope.options.length} disabled={disabled} />
            <div className="mt-2 max-h-[min(45vh,420px)] divide-y divide-border overflow-y-auto rounded-lg border border-border bg-surface">
              {filtered.length === 0 ? (
                <FilterEmptyState query={query} onClear={() => setQuery('')} />
              ) : (
                filtered.map(({ opt }) => {
                  const selected = pickedSet.has(opt);
                  return (
                    <ListRow
                      key={opt}
                      label={opt}
                      selected={selected}
                      disabled={disabled}
                      onClick={() => toggle(opt)}
                      role="checkbox"
                    />
                  );
                })
              )}
            </div>
          </div>
          <div className="md:col-span-2">
            <DetailPane
              envelope={envelope}
              variableName={variableName}
              selectedLabel={
                picked.length === 0
                  ? null
                  : picked.length === 1
                    ? picked[0]
                    : `${picked.length} selected`
              }
              selectedList={picked.length > 1 ? picked : null}
              rawContext={null}
            />
          </div>
        </div>
      )}
    </div>
  );
};

// ─── attorney_pick (two-pane, attorneys list) ────────────────────────

const AttorneyPickBody = ({
  envelope, variableName, pick, onChange, disabled,
}: BodyProps & { envelope: PendingAttorneyPickV2 }) => {
  const [query, setQuery] = useState('');
  const filtered = useMemo(
    () =>
      envelope.options.filter((att) => {
        if (!query.trim()) return true;
        const q = query.toLowerCase();
        return (
          att.display_name.toLowerCase().includes(q) ||
          (att.bar_number ?? '').toLowerCase().includes(q)
        );
      }),
    [envelope.options, query],
  );

  if (envelope.multi_select) {
    const picked = (pick && 'picked_values' in pick) ? pick.picked_values : [];
    const pickedSet = new Set(picked);
    const toggle = (id: string) => {
      const next = pickedSet.has(id)
        ? picked.filter((v) => v !== id)
        : [...picked, id];
      onChange({ picked_values: next });
    };
    const pickRangeLabel = envelope.min_picks === envelope.max_picks
      ? `Pick exactly ${envelope.min_picks}`
      : `Pick ${envelope.min_picks}–${envelope.max_picks}`;
    return (
      <div className="space-y-3">
        <FieldHeading
          label={envelope.label || variableName}
          helperText={`${pickRangeLabel} attorneys · ${picked.length} picked of ${envelope.options.length}.`}
        />
        {envelope.options.length === 0 ? (
          <EmptyRosterState />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
            <div className="md:col-span-3">
              <ListSearch query={query} onQuery={setQuery} count={envelope.options.length} disabled={disabled} placeholder="Search attorneys…" />
              <div className="mt-2 max-h-[min(45vh,420px)] divide-y divide-border overflow-y-auto rounded-lg border border-border bg-surface">
                {filtered.length === 0 ? (
                  <FilterEmptyState query={query} onClear={() => setQuery('')} />
                ) : (
                  filtered.map((att) => {
                    const selected = pickedSet.has(att.id);
                    return (
                      <ListRow
                        key={att.id}
                        label={att.display_name}
                        meta={att.bar_number ? `Bar #${att.bar_number}` : undefined}
                        selected={selected}
                        disabled={disabled}
                        onClick={() => toggle(att.id)}
                        role="checkbox"
                      />
                    );
                  })
                )}
              </div>
            </div>
            <div className="md:col-span-2">
              <DetailPane
                envelope={envelope}
                variableName={variableName}
                selectedLabel={
                  picked.length === 0
                    ? null
                    : picked.length === 1
                      ? labelForAttorneyId(envelope.options, picked[0])
                      : `${picked.length} attorneys selected`
                }
                selectedList={
                  picked.length > 1
                    ? picked.map((id) => labelForAttorneyId(envelope.options, id))
                    : null
                }
                rawContext={null}
              />
            </div>
          </div>
        )}
      </div>
    );
  }

  // Single-select
  const value = (pick && 'value' in pick) ? pick.value : '';
  return (
    <div className="space-y-3">
      <FieldHeading
        label={envelope.label || variableName}
        helperText="Pick one attorney from the firm's roster."
      />
      {envelope.options.length === 0 ? (
        <EmptyRosterState />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
          <div className="md:col-span-3">
            <ListSearch query={query} onQuery={setQuery} count={envelope.options.length} disabled={disabled} placeholder="Search attorneys…" />
            <div className="mt-2 max-h-[min(45vh,420px)] divide-y divide-border overflow-y-auto rounded-lg border border-border bg-surface">
              {filtered.length === 0 ? (
                <FilterEmptyState query={query} onClear={() => setQuery('')} />
              ) : (
                filtered.map((att) => {
                  const selected = value === att.id;
                  return (
                    <ListRow
                      key={att.id}
                      label={att.display_name}
                      meta={att.bar_number ? `Bar #${att.bar_number}` : undefined}
                      selected={selected}
                      disabled={disabled}
                      onClick={() => onChange({ value: att.id })}
                      role="radio"
                    />
                  );
                })
              )}
            </div>
          </div>
          <div className="md:col-span-2">
            <DetailPane
              envelope={envelope}
              variableName={variableName}
              selectedLabel={value ? labelForAttorneyId(envelope.options, value) : null}
              rawContext={null}
            />
          </div>
        </div>
      )}
    </div>
  );
};

// ─── chip (single-pane, smart suggestion chips + custom input) ──────

const ChipBody = ({
  envelope, variableName, pick, onChange, disabled,
}: BodyProps & { envelope: PendingChipV2 }) => {
  const value = (pick && 'value' in pick) ? pick.value : '';
  return (
    <div className="mx-auto max-w-2xl">
      <FieldHeading
        label={envelope.label || variableName}
        helperText="Pick one of the AI's smart suggestions or type your own."
      />
      <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap gap-1.5">
          {envelope.chips.map((chip) => {
            const selected = value === chip;
            return (
              <button
                key={chip}
                type="button"
                disabled={disabled}
                onClick={() => onChange({ value: chip })}
                className={cn(
                  'cursor-pointer rounded-full border px-3 py-1.5 text-xs font-medium motion-safe:transition-colors',
                  selected
                    ? 'border-app-accent bg-app-accent text-white'
                    : 'border-border bg-surface text-text-secondary hover:bg-surface-muted',
                  disabled && 'pointer-events-none opacity-60',
                )}
              >
                {chip}
              </button>
            );
          })}
        </div>
        <div className="border-t border-border pt-3">
          <label className="block text-xs font-medium text-muted">
            Or type your own
          </label>
          <input
            type="text"
            value={value}
            disabled={disabled}
            onChange={(e) => onChange({ value: e.target.value })}
            placeholder="Your custom value…"
            className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-50"
          />
        </div>
      </div>
      <KindBadge envelope={envelope} variableName={variableName} />
    </div>
  );
};

// ─── author_text (single-pane, textarea with example hint) ──────────

const AuthorTextBody = ({
  envelope, variableName, pick, onChange, disabled,
}: BodyProps & { envelope: PendingAuthorTextV2 }) => {
  const value = (pick && 'value' in pick) ? pick.value : '';
  return (
    <div className="mx-auto max-w-2xl">
      <FieldHeading
        label={envelope.label || variableName}
        helperText="Write it the way you'd want it to appear in the document."
      />
      <div className="rounded-xl border border-border bg-surface p-4">
        <textarea
          value={value}
          disabled={disabled}
          onChange={(e) => onChange({ value: e.target.value })}
          placeholder={envelope.placeholder ?? 'Type the value…'}
          rows={5}
          className="w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-50"
        />
        <div className="mt-1 flex items-center justify-end">
          <span className="text-[10px] text-subtle">
            {value.length} chars
          </span>
        </div>
        {envelope.example_output_sentence && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="text-[11px] font-medium uppercase tracking-wider text-muted">
              Aim for
            </p>
            <p className="mt-1 border-l-2 border-app-accent/40 pl-3 text-sm italic text-muted">
              {envelope.example_output_sentence}
            </p>
          </div>
        )}
      </div>
      <KindBadge envelope={envelope} variableName={variableName} />
    </div>
  );
};

// ─── author_date (single-pane, native picker) ───────────────────────

const AuthorDateBody = ({
  envelope, variableName, pick, onChange, disabled,
}: BodyProps & { envelope: PendingAuthorDateV2 }) => {
  const value = (pick && 'value' in pick) ? pick.value : '';
  return (
    <div className="mx-auto max-w-2xl">
      <FieldHeading
        label={envelope.label || variableName}
        helperText="Pick any date — the document uses the firm's preferred format automatically."
      />
      <div className="rounded-xl border border-border bg-surface p-4">
        <label className="block text-xs font-medium text-muted">
          Date
        </label>
        <input
          type="date"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange({ value: e.target.value })}
          className="mt-1 w-60 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-50"
        />
      </div>
      <KindBadge envelope={envelope} variableName={variableName} />
    </div>
  );
};

// ─── author_docs (textarea + AI-enhanced notice + upload zone) ──────

const AuthorDocsBody = ({
  envelope, variableName, pick, onChange, disabled, caseId, onBusyChange,
}: BodyProps & { envelope: PendingAuthorDocsV2 }) => {
  const userText = (pick && 'user_text' in pick) ? pick.user_text : '';
  const fileUrls = (pick && 'file_urls' in pick) ? pick.file_urls : [];
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [nameByUrl, setNameByUrl] = useState<Record<string, string>>({});

  // Mirror local upload state up to the modal — disables Next / Finish
  // until the in-flight upload settles. Cleanup ensures unmount flips
  // it back to false (no zombie "busy" if the body is replaced mid-flight).
  useEffect(() => {
    onBusyChange(isUploading);
    return () => onBusyChange(false);
  }, [isUploading, onBusyChange]);

  const acceptAttr = useMemo(
    () => envelope.accepted_file_types.join(','),
    [envelope.accepted_file_types],
  );

  const displayName = (url: string): string => {
    const known = nameByUrl[url];
    if (known) return known;
    const tail = url.split('/').pop();
    return tail || url;
  };

  const updateText = (value: string) =>
    onChange({ user_text: value, file_urls: fileUrls });

  const handleFiles = async (files: FileList | null): Promise<void> => {
    if (!files || files.length === 0) return;
    setUploadError(null);
    if (!caseId) {
      setUploadError(
        'Pick a case before uploading files — this dry-run has no case attached yet.',
      );
      return;
    }
    const remaining = MAX_SUPPORTING_FILES - fileUrls.length;
    if (remaining <= 0) {
      setUploadError(`Maximum ${MAX_SUPPORTING_FILES} files allowed.`);
      return;
    }
    const capped = Array.from(files).slice(0, remaining);
    if (capped.length < files.length) {
      setUploadError(
        `Only ${remaining} more file${remaining === 1 ? '' : 's'} allowed — extras were skipped.`,
      );
    }
    setIsUploading(true);
    const result = await uploadSupportingDocsV2(caseId, capped);
    setIsUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (!result.data) {
      setUploadError(result.error ?? 'Upload failed');
      return;
    }
    const newUrls = result.data.map((r) => r.file_url);
    const names: Record<string, string> = {};
    for (const r of result.data) names[r.file_url] = r.filename;
    setNameByUrl((prev) => ({ ...prev, ...names }));
    onChange({ user_text: userText, file_urls: [...fileUrls, ...newUrls] });
  };

  const removeFileUrl = (idx: number): void => {
    onChange({
      user_text: userText,
      file_urls: fileUrls.filter((_, i) => i !== idx),
    });
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  };
  const onDragLeave = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };
  const onDrop = (e: DragEvent<HTMLDivElement>): void => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    void handleFiles(e.dataTransfer.files);
  };
  const onDropKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const canUploadMore = fileUrls.length < MAX_SUPPORTING_FILES;
  const dropzoneDisabled = disabled || isUploading || !canUploadMore;

  return (
    <div className="mx-auto max-w-2xl">
      <FieldHeading
        label={envelope.label || variableName}
        helperText="Describe in your own words. The AI polishes your text into the final document."
      />
      <div className="space-y-4 rounded-xl border border-border bg-surface p-4">
        <textarea
          value={userText}
          disabled={disabled}
          onChange={(e) => updateText(e.target.value)}
          placeholder="Describe in your own words…"
          rows={5}
          className="w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-50"
        />

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-text-secondary">
              Supporting documents{' '}
              <span className="font-normal text-muted">(optional)</span>
            </p>
            {fileUrls.length > 0 && (
              <span className="text-[11px] text-subtle">
                {fileUrls.length}/{MAX_SUPPORTING_FILES} attached
              </span>
            )}
          </div>

          <div className="flex items-start gap-3 rounded-lg border border-app-accent-soft bg-app-accent-soft/60 px-3 py-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface text-app-accent-text shadow-sm">
              <FiZap className="h-4 w-4" strokeWidth={2.5} />
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-app-accent-text">
                AI-enhanced
              </p>
              <p className="mt-1 text-xs leading-5 text-text-secondary">
                Attach bank statements, receipts, pay records, or anything
                that corroborates your explanation. The AI uses them
                alongside your text to pull in specific dates, amounts,
                and other details.
              </p>
            </div>
          </div>

          {fileUrls.length > 0 && (
            <ul className="space-y-1.5">
              {fileUrls.map((url, idx) => (
                <li
                  key={url}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border bg-surface px-3 py-2"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <FiFile className="h-4 w-4 shrink-0 text-app-accent-text" />
                    <span className="truncate text-xs text-text-secondary">
                      {displayName(url)}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeFileUrl(idx)}
                    disabled={disabled || isUploading}
                    aria-label={`Remove ${displayName(url)}`}
                    className="shrink-0 rounded p-1 text-subtle transition-colors hover:bg-app-danger-soft hover:text-app-danger-text disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <FiX className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          {canUploadMore && (
            <div
              onDragOver={dropzoneDisabled ? undefined : onDragOver}
              onDragLeave={dropzoneDisabled ? undefined : onDragLeave}
              onDrop={dropzoneDisabled ? undefined : onDrop}
              onClick={dropzoneDisabled ? undefined : () => fileInputRef.current?.click()}
              onKeyDown={dropzoneDisabled ? undefined : onDropKeyDown}
              role="button"
              tabIndex={dropzoneDisabled ? -1 : 0}
              aria-disabled={dropzoneDisabled}
              className={cn(
                'flex flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-5 text-center motion-safe:transition-colors',
                isDragOver
                  ? 'border-app-accent bg-app-accent-soft'
                  : 'border-border bg-surface hover:border-app-accent/60 hover:bg-app-accent-soft/40',
                dropzoneDisabled && 'pointer-events-none opacity-60',
                !dropzoneDisabled && 'cursor-pointer',
              )}
            >
              <FiUploadCloud className="h-7 w-7 text-subtle" />
              <p className="text-sm font-medium text-text-secondary">
                {isUploading ? 'Uploading…' : 'Click to browse or drag and drop'}
              </p>
              <p className="text-xs text-muted">
                {envelope.accepted_file_types
                  .map((e) => e.replace(/^\./, '').toUpperCase())
                  .join(', ')}
              </p>
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={acceptAttr}
            onChange={(e) => void handleFiles(e.target.files)}
            disabled={dropzoneDisabled}
            className="hidden"
          />

          {uploadError && (
            <p className="rounded border border-app-danger-soft bg-app-danger-soft px-2 py-1.5 text-[11px] text-app-danger-text">
              {uploadError}
            </p>
          )}
        </div>
      </div>
      <KindBadge envelope={envelope} variableName={variableName} />
    </div>
  );
};

// ─── shared building blocks ──────────────────────────────────────────

const ListSearch = ({
  query, onQuery, count, disabled, placeholder = 'Search candidates…',
}: {
  query: string;
  onQuery: (q: string) => void;
  count: number;
  disabled: boolean;
  placeholder?: string;
}) => (
  <div className="sticky top-0 z-10 rounded-lg border border-border bg-surface/95 backdrop-blur">
    <div className="relative">
      <FiSearch className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
      <input
        type="text"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        disabled={disabled}
        placeholder={count > 0 ? `${placeholder.replace('candidates', `${count} candidates`)}` : placeholder}
        className="block w-full rounded-lg border-0 bg-transparent py-2.5 pl-9 pr-9 text-sm text-text-secondary placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-50"
      />
      {query && (
        <button
          type="button"
          onClick={() => onQuery('')}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-subtle hover:bg-surface-muted hover:text-text-secondary"
        >
          <FiX className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  </div>
);

const ListRow = ({
  label, meta, selected, disabled, onClick, role,
}: {
  label: string;
  meta?: string;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
  role: 'radio' | 'checkbox';
}) => {
  const parsed = parseListOption(label);
  return (
    <button
      type="button"
      role={role}
      aria-checked={selected}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-3 px-4 py-3 text-left motion-safe:transition-colors',
        selected
          ? 'border-l-2 border-l-app-accent bg-app-accent-soft/40'
          : 'border-l-2 border-l-transparent hover:bg-surface-muted/60',
        disabled && 'pointer-events-none opacity-60',
      )}
    >
      {parsed.index !== null ? (
        <span
          className={cn(
            'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold',
            selected
              ? 'bg-app-accent text-white'
              : 'bg-surface-muted text-muted',
          )}
        >
          {parsed.index}
        </span>
      ) : (
        <span
          className={cn(
            'inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full ring-1',
            selected
              ? 'bg-app-accent ring-app-accent'
              : 'ring-border',
          )}
        >
          {selected && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className={cn(
          'truncate text-sm',
          selected ? 'font-semibold text-app-accent-text' : 'text-text-secondary',
        )}>
          {parsed.name ?? label}
        </p>
        {meta && (
          <p className="mt-0.5 truncate text-[11px] text-subtle">{meta}</p>
        )}
      </div>
      {parsed.amount && (
        <span
          className={cn(
            'shrink-0 font-mono text-sm tabular-nums',
            selected ? 'font-semibold text-app-accent-text' : 'text-text-secondary',
          )}
        >
          {parsed.amount}
        </span>
      )}
    </button>
  );
};

const DetailPane = ({
  envelope,
  variableName,
  selectedLabel,
  selectedList,
  rawContext,
}: {
  envelope: PendingUserInputV2;
  variableName: string;
  selectedLabel: string | null;
  selectedList?: string[] | null;
  rawContext: string | null;
}) => {
  const parsed = selectedLabel ? parseListOption(selectedLabel) : null;
  return (
    <div className="h-full rounded-lg border border-border bg-surface p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
        Your selection
      </p>
      {!selectedLabel && !selectedList?.length ? (
        <p className="mt-3 text-sm italic text-subtle">
          Nothing picked yet. Choose from the list to see details.
        </p>
      ) : selectedList && selectedList.length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {selectedList.map((s, i) => (
            <li
              key={`${s}-${i}`}
              className="flex items-center gap-2 rounded-md bg-surface-muted/50 px-2 py-1.5 text-sm text-text-secondary"
            >
              <FiCheck className="h-3 w-3 shrink-0 text-app-accent-text" />
              <span className="truncate">{s}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-3 space-y-2">
          {parsed?.index !== null && parsed?.index !== undefined && (
            <p className="font-mono text-[10px] uppercase text-subtle">
              Row #{parsed.index}
            </p>
          )}
          <p className="text-sm font-semibold text-text-secondary">
            {parsed?.name ?? selectedLabel}
          </p>
          {parsed?.amount && (
            <p className="font-mono text-sm tabular-nums text-text-secondary">
              {parsed.amount}
            </p>
          )}
        </div>
      )}
      {rawContext && (
        <div className="mt-4 border-t border-border pt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            From the source
          </p>
          <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap border-l-2 border-app-accent/40 pl-3 text-xs italic text-muted">
            {rawContext}
          </p>
        </div>
      )}
      <div className="mt-4 border-t border-border pt-3">
        <KindBadge envelope={envelope} variableName={variableName} />
      </div>
    </div>
  );
};

const EmptyExtractionState = () => (
  <div className="rounded-lg border border-dashed border-border bg-surface px-6 py-10 text-center">
    <FiList className="mx-auto h-6 w-6 text-subtle" />
    <p className="mt-2 text-sm font-medium text-text-secondary">
      No candidates extracted
    </p>
    <p className="mt-1 text-xs text-muted">
      Try editing the field's extraction prompt or re-running the
      dry-run with a different source.
    </p>
  </div>
);

const EmptyRosterState = () => (
  <div className="rounded-lg border border-dashed border-border bg-surface px-6 py-10 text-center">
    <FiUser className="mx-auto h-6 w-6 text-subtle" />
    <p className="mt-2 text-sm font-medium text-text-secondary">
      Roster is empty
    </p>
    <p className="mt-1 text-xs text-muted">
      Add attorneys in firm settings, then re-run the dry-run.
    </p>
  </div>
);

const FilterEmptyState = ({ query, onClear }: { query: string; onClear: () => void }) => (
  <div className="px-6 py-10 text-center">
    <FiFilter className="mx-auto h-5 w-5 text-subtle" />
    <p className="mt-2 text-sm text-text-secondary">
      No matches for <span className="font-semibold">“{query}”</span>
    </p>
    <button
      type="button"
      onClick={onClear}
      className="mt-2 cursor-pointer text-xs font-semibold text-app-accent-text hover:underline"
    >
      Clear filter
    </button>
  </div>
);

// ─── helpers ─────────────────────────────────────────────────────────

function isPickFilled(
  envelope: PendingUserInputV2,
  pick: UserSelectionV2 | undefined,
): boolean {
  if (!pick) return false;
  if (envelope.kind === 'multi_select') {
    if (!('picked_values' in pick)) return false;
    return (
      pick.picked_values.length >= envelope.min_picks &&
      pick.picked_values.length <= envelope.max_picks
    );
  }
  if (envelope.kind === 'attorney_pick' && envelope.multi_select) {
    if (!('picked_values' in pick)) return false;
    return (
      pick.picked_values.length >= envelope.min_picks &&
      pick.picked_values.length <= envelope.max_picks
    );
  }
  if (envelope.kind === 'author_docs') {
    if (!('user_text' in pick)) return false;
    return pick.user_text.trim().length > 0;
  }
  if (!('value' in pick)) return false;
  return pick.value.trim().length > 0;
}

function kindIcon(kind: PendingUserInputV2['kind']): IconType {
  switch (kind) {
    case 'dropdown': return FiList;
    case 'multi_select': return FiSliders;
    case 'chip': return FiSliders;
    case 'author_text': return FiType;
    case 'author_date': return FiCalendar;
    case 'author_docs': return FiFileText;
    case 'attorney_pick': return FiUser;
    default: return FiList;
  }
}

function kindLabel(kind: PendingUserInputV2['kind']): string {
  switch (kind) {
    case 'dropdown': return 'Pick one';
    case 'multi_select': return 'Pick several';
    case 'chip': return 'Smart suggestions';
    case 'author_text': return 'Type it';
    case 'author_date': return 'Pick a date';
    case 'author_docs': return 'Describe + upload';
    case 'attorney_pick': return 'Attorney';
    default: return String(kind);
  }
}

function filterOptions(
  options: readonly string[],
  query: string,
): Array<{ opt: string }> {
  if (!query.trim()) return options.map((opt) => ({ opt }));
  const q = query.toLowerCase();
  return options
    .filter((opt) => opt.toLowerCase().includes(q))
    .map((opt) => ({ opt }));
}

/**
 * Parse list-style strings like:
 *   "3 - Navy Federal Credit Union - $14,413.75"
 *   "12. Quantum3 Group LLC — $510.19"
 *
 * into { index, name, amount }. Returns nulls when the pattern doesn't
 * match (caller falls back to rendering the raw label).
 */
function parseListOption(label: string): {
  index: string | null;
  name: string | null;
  amount: string | null;
} {
  const trimmed = label.trim();
  // Index: leading "N - " or "N. " or "N) "
  const idxMatch = trimmed.match(/^(\d+)\s*[-.)–—]\s*(.+)$/);
  let index: string | null = null;
  let rest = trimmed;
  if (idxMatch) {
    index = idxMatch[1];
    rest = idxMatch[2];
  }
  // Amount: trailing "- $X" or "— $X" or "$X"
  const amountMatch = rest.match(/^(.+?)\s*[-–—]\s*(\$[\d,]+(?:\.\d{1,2})?)\s*$/);
  if (amountMatch) {
    return { index, name: amountMatch[1].trim(), amount: amountMatch[2] };
  }
  return { index, name: rest || null, amount: null };
}

function labelForAttorneyId(
  options: PendingAttorneyPickV2['options'],
  id: string,
): string {
  return options.find((o) => o.id === id)?.display_name ?? id;
}
