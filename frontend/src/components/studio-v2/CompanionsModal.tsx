import { useEffect, useMemo, useRef, useState } from 'react';
import {
  FiArrowLeft,
  FiCheck,
  FiChevronRight,
  FiLayers,
  FiPlus,
  FiTrash2,
  FiX,
} from 'react-icons/fi';
import { Modal } from '@/components/common';
import { cn } from '@/utils';
import {
  newBranchCompanion,
  newBranchOption,
  newFixedCompanion,
  newSlotConfig,
  type BranchCompanion,
  type BranchOption,
  type BundleCompanion,
  type CompanionKind,
  type FixedCompanion,
  type StudioTemplate,
  type StudioVariable,
  type SlotConfig,
  type SlotConfigKind,
} from './types';

const KIND_HINT: Record<CompanionKind, string> = {
  fixed: 'Runs every time. No question asked.',
  branch:
    "You'll answer a question when drafting — your answer picks which template runs.",
};

const SLOT_KIND_LABEL: Record<SlotConfigKind, string> = {
  parent_variable: 'From a field',
  extract_from_draft: 'From the document',
  literal: 'Fixed text',
};

const SLOT_KIND_HINT: Record<SlotConfigKind, string> = {
  parent_variable: 'Use the value of a field in this filing.',
  extract_from_draft:
    "Find this value in the filing's rendered document, using a short description.",
  literal: 'Use the same value every time.',
};

// A "slot" is any variable on a child template whose source is
// `value_from_parent_bundle` — the lead has to provide a value for it.
const findSlotVariables = (
  childTemplate: StudioTemplate | undefined,
): StudioVariable[] => {
  if (!childTemplate) return [];
  return childTemplate.variables.filter(
    (v) => v.params?.source === 'value_from_parent_bundle',
  );
};

interface CompanionsModalProps {
  isOpen: boolean;
  templateName: string;
  companions: BundleCompanion[];
  availableChildTemplates: StudioTemplate[];
  currentTemplateId: string;
  leadVariables: StudioVariable[];
  onChange: (companions: BundleCompanion[]) => void;
  onCreateTemplate: (name: string) => string;
  onClose: () => void;
}

const inputClass =
  'w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent/20';

const KIND_PILL_STYLES: Record<CompanionKind, string> = {
  fixed: 'bg-app-accent-soft text-app-accent-text',
  branch: 'bg-amber-100 text-amber-900',
};

const KIND_PILL_LABEL: Record<CompanionKind, string> = {
  fixed: 'Always',
  branch: 'Branch',
};

const isSlotConfigComplete = (config: SlotConfig | undefined): boolean => {
  if (!config) return false;
  if (config.kind === 'parent_variable') return config.parent_variable.trim().length > 0;
  if (config.kind === 'extract_from_draft') return config.extract_instruction.trim().length > 0;
  return true; // literal — empty string is a valid intentional blank
};

const areSlotsReady = (
  childId: string | null,
  slotConfigurations: Record<string, SlotConfig>,
  templateLookup: Map<string, StudioTemplate>,
): boolean => {
  if (!childId) return false;
  const child = templateLookup.get(childId);
  if (!child) return false;
  const slots = findSlotVariables(child);
  return slots.every((slot) =>
    isSlotConfigComplete(slotConfigurations[slot.template_variable]),
  );
};

const isReady = (
  companion: BundleCompanion,
  templateLookup: Map<string, StudioTemplate>,
): boolean => {
  if (companion.kind === 'fixed') {
    if (!companion.child_template_id) return false;
    if (!templateLookup.has(companion.child_template_id)) return false;
    return areSlotsReady(
      companion.child_template_id,
      companion.slot_configurations,
      templateLookup,
    );
  }
  if (!companion.question.trim()) return false;
  if (companion.options.length === 0) return false;
  return companion.options.every(
    (o) =>
      o.option_label.trim().length > 0 &&
      o.child_template_id !== null &&
      templateLookup.has(o.child_template_id) &&
      areSlotsReady(o.child_template_id, o.slot_configurations, templateLookup),
  );
};

const summarizeCompanion = (
  companion: BundleCompanion,
  templateLookup: Map<string, StudioTemplate>,
): string => {
  if (companion.kind === 'fixed') {
    const child = companion.child_template_id
      ? templateLookup.get(companion.child_template_id)
      : null;
    return child ? `→ ${child.name}` : '→ template not picked';
  }
  if (!companion.question.trim()) return 'No question set';
  const optCount = companion.options.length;
  return `"${companion.question}" · ${optCount} option${optCount === 1 ? '' : 's'}`;
};

export const CompanionsModal = ({
  isOpen,
  templateName,
  companions,
  availableChildTemplates,
  currentTemplateId,
  leadVariables,
  onChange,
  onCreateTemplate,
  onClose,
}: CompanionsModalProps) => {
  const [mode, setMode] = useState<{ view: 'list' } | { view: 'detail'; id: string }>({
    view: 'list',
  });

  // Local draft of the companions array. All edits go HERE — they
  // commit to the parent's `onChange` only when the paralegal clicks
  // "Save changes". This solves two problems at once:
  //   1. The previous architecture fired `onChange` on every keystroke
  //      → debounced BE save → parent prop lagged ~500ms behind →
  //      "empty flash" when adding a branch companion (setMode jumped
  //      to detail before `companions` prop had the new entry).
  //   2. Paralegals expect saving a companion to be EXPLICIT — not
  //      every typed character.
  const [draft, setDraft] = useState<BundleCompanion[]>(companions);
  const [isDirty, setIsDirty] = useState(false);

  // Re-sync the draft when the modal opens. We track the open edge so
  // a later parent re-render (e.g. unrelated config change) while the
  // modal is open doesn't blow away the paralegal's in-progress edits.
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      setDraft(companions);
      setIsDirty(false);
      setMode({ view: 'list' });
    }
    wasOpenRef.current = isOpen;
  }, [isOpen, companions]);

  // Only `part_of_packet` templates may be picked as companions —
  // matches the BE invariant assert_part_of_packet_has_no_user_input_v2.
  // We still show the current template's already-picked OTHER companions
  // exclude the current template itself (a template can't be its own companion).
  const childOptions = useMemo(
    () =>
      availableChildTemplates.filter(
        (t) =>
          t.id !== currentTemplateId &&
          t.config.role === 'part_of_packet',
      ),
    [availableChildTemplates, currentTemplateId],
  );
  // Lookup includes EVERY template (regardless of role) so already-picked
  // companions with mismatched roles still resolve to their name when
  // rendered — avoids "Unknown template" labels if a template's role was
  // changed after being added as a companion.
  const templateLookup = useMemo(
    () => new Map(availableChildTemplates.map((t) => [t.id, t])),
    [availableChildTemplates],
  );

  const activeCompanion =
    mode.view === 'detail'
      ? draft.find((c) => c.id === mode.id) ?? null
      : null;

  const incompleteCount = draft.filter(
    (c) => !isReady(c, templateLookup),
  ).length;

  const handleSave = (): void => {
    onChange(draft);
    setIsDirty(false);
    setMode({ view: 'list' });
    onClose();
  };

  const handleClose = (): void => {
    if (isDirty) {
       
      const confirmed = window.confirm(
        'Discard unsaved companion changes?',
      );
      if (!confirmed) return;
    }
    setDraft(companions);
    setIsDirty(false);
    setMode({ view: 'list' });
    onClose();
  };

  const handleAdd = (kind: CompanionKind): void => {
    const fresh = kind === 'fixed' ? newFixedCompanion() : newBranchCompanion();
    setDraft((prev) => [...prev, fresh]);
    setIsDirty(true);
    setMode({ view: 'detail', id: fresh.id });
  };

  const handleUpdate = (
    id: string,
    updater: (c: BundleCompanion) => BundleCompanion,
  ): void => {
    setDraft((prev) => prev.map((c) => (c.id === id ? updater(c) : c)));
    setIsDirty(true);
  };

  const handleRemove = (id: string): void => {
    setDraft((prev) => prev.filter((c) => c.id !== id));
    setIsDirty(true);
    if (mode.view === 'detail' && mode.id === id) setMode({ view: 'list' });
  };

  const handleSetKind = (id: string, kind: CompanionKind): void => {
    setDraft((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c;
        if (c.kind === kind) return c;
        const fresh = kind === 'fixed' ? newFixedCompanion() : newBranchCompanion();
        return { ...fresh, id: c.id, label: c.label };
      }),
    );
    setIsDirty(true);
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} size="3xl" closeOnBackdropClick={false}>
      <div className="flex max-h-[min(85vh,780px)] flex-col">
        <header className="shrink-0 border-b border-border px-6 py-4 pr-12">
          <div className="flex items-center gap-2">
            {mode.view === 'detail' && (
              <button
                type="button"
                onClick={() => setMode({ view: 'list' })}
                className="inline-flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-subtle hover:bg-surface-muted hover:text-text-secondary"
              >
                <FiArrowLeft className="h-3.5 w-3.5" />
                Back to list
              </button>
            )}
            <p className="text-xs font-semibold uppercase tracking-wider text-app-accent-text">
              {mode.view === 'list' ? 'Companions' : 'Editing companion'}
            </p>
          </div>
          <h2 className="mt-1 text-lg font-semibold text-text">
            {templateName}{' '}
            <span className="font-normal text-subtle">— companion templates</span>
          </h2>
          {mode.view === 'list' && (
            <p className="mt-1 text-sm text-text-secondary">
              Other templates that run alongside this filing.
            </p>
          )}
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {mode.view === 'list' ? (
            <ListView
              companions={draft}
              templateLookup={templateLookup}
              onOpenCompanion={(id) => setMode({ view: 'detail', id })}
              onRemoveCompanion={handleRemove}
              onAdd={handleAdd}
            />
          ) : activeCompanion ? (
            <DetailView
              companion={activeCompanion}
              childOptions={childOptions}
              templateLookup={templateLookup}
              leadVariables={leadVariables}
              onUpdate={(updater) => handleUpdate(activeCompanion.id, updater)}
              onSetKind={(kind) => handleSetKind(activeCompanion.id, kind)}
              onRemove={() => handleRemove(activeCompanion.id)}
              onCreateTemplate={onCreateTemplate}
            />
          ) : null}
        </div>

        <footer className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-surface px-6 py-4">
          <div className="flex flex-col gap-0.5 text-xs">
            <p className="text-subtle">
              {draft.length === 0
                ? 'No companions yet.'
                : incompleteCount === 0
                  ? `${draft.length} companion${draft.length === 1 ? '' : 's'} ready.`
                  : `${incompleteCount} companion${incompleteCount === 1 ? '' : 's'} still need${incompleteCount === 1 ? 's' : ''} setup.`}
            </p>
            {isDirty && (
              <p className="text-[10px] font-medium text-amber-700">
                You have unsaved changes.
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleClose}
              className="cursor-pointer rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-semibold text-text-secondary hover:bg-surface-muted"
            >
              {isDirty ? 'Discard & close' : 'Cancel'}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!isDirty}
              className={cn(
                'rounded-lg px-4 py-2 text-sm font-semibold motion-safe:transition-opacity',
                isDirty
                  ? 'cursor-pointer bg-app-accent text-white hover:opacity-90'
                  : 'cursor-not-allowed bg-surface-muted text-subtle',
              )}
            >
              Save changes
            </button>
          </div>
        </footer>
      </div>
    </Modal>
  );
};

interface ListViewProps {
  companions: BundleCompanion[];
  templateLookup: Map<string, StudioTemplate>;
  onOpenCompanion: (id: string) => void;
  onRemoveCompanion: (id: string) => void;
  onAdd: (kind: CompanionKind) => void;
}

const ListView = ({
  companions,
  templateLookup,
  onOpenCompanion,
  onRemoveCompanion,
  onAdd,
}: ListViewProps) => {
  if (companions.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-10 text-center">
        <span className="grid h-16 w-16 place-items-center rounded-full bg-app-accent-soft text-app-accent-text">
          <FiLayers className="h-8 w-8" />
        </span>
        <div className="max-w-md space-y-1.5">
          <h3 className="text-lg font-semibold text-text">
            No companions yet
          </h3>
          <p className="text-sm text-text-secondary">
            Add another template to run alongside this filing. Pick{' '}
            <span className="font-semibold">Always runs</span> to include it
            every time, or <span className="font-semibold">Choose at draft
            time</span> to pick one of several templates based on a question.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onAdd('fixed')}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-app-accent px-4 py-2 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          >
            <FiPlus className="h-4 w-4" />
            Always runs
          </button>
          <button
            type="button"
            onClick={() => onAdd('branch')}
            className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-app-accent bg-surface px-4 py-2 text-sm font-semibold text-app-accent-text transition-colors hover:bg-app-accent-soft"
          >
            <FiPlus className="h-4 w-4" />
            Choose at draft time
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        {companions.map((companion) => {
          const ready = isReady(companion, templateLookup);
          return (
            <button
              key={companion.id}
              type="button"
              onClick={() => onOpenCompanion(companion.id)}
              className="group flex w-full cursor-pointer items-start gap-3 rounded-lg border border-border bg-surface px-4 py-3 text-left transition-all hover:border-app-accent hover:shadow-sm"
            >
              <span
                className={cn(
                  'mt-0.5 inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                  KIND_PILL_STYLES[companion.kind],
                )}
              >
                {KIND_PILL_LABEL[companion.kind]}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-text">
                  {companion.label || 'Untitled companion'}
                </p>
                <p className="mt-0.5 truncate text-xs italic text-subtle">
                  {summarizeCompanion(companion, templateLookup)}
                </p>
              </div>
              <span
                className={cn(
                  'mt-0.5 inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                  ready
                    ? 'bg-app-accent-soft text-app-accent-text'
                    : 'bg-amber-100 text-amber-900',
                )}
              >
                {ready ? 'Ready' : 'Needs setup'}
              </span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRemoveCompanion(companion.id);
                }}
                className="cursor-pointer rounded p-1 text-subtle opacity-0 transition-opacity hover:bg-app-danger-soft hover:text-app-danger-text group-hover:opacity-100"
                aria-label={`Remove ${companion.label}`}
              >
                <FiTrash2 className="h-3.5 w-3.5" />
              </button>
              <FiChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-subtle" />
            </button>
          );
        })}
      </div>
      <div className="flex gap-2 border-t border-border pt-3">
        <button
          type="button"
          onClick={() => onAdd('fixed')}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-dashed border-border bg-surface px-3 py-1.5 text-xs font-medium text-subtle hover:border-app-accent/40 hover:text-text-secondary"
        >
          <FiPlus className="h-3 w-3" />
          Always runs
        </button>
        <button
          type="button"
          onClick={() => onAdd('branch')}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-dashed border-border bg-surface px-3 py-1.5 text-xs font-medium text-subtle hover:border-app-accent/40 hover:text-text-secondary"
        >
          <FiPlus className="h-3 w-3" />
          Choose at draft time
        </button>
      </div>
    </div>
  );
};

interface DetailViewProps {
  companion: BundleCompanion;
  childOptions: StudioTemplate[];
  templateLookup: Map<string, StudioTemplate>;
  leadVariables: StudioVariable[];
  onUpdate: (updater: (c: BundleCompanion) => BundleCompanion) => void;
  onSetKind: (kind: CompanionKind) => void;
  onRemove: () => void;
  onCreateTemplate: (name: string) => string;
}

const DetailView = ({
  companion,
  childOptions,
  templateLookup,
  leadVariables,
  onUpdate,
  onSetKind,
  onRemove,
  onCreateTemplate,
}: DetailViewProps) => (
  <div className="space-y-5">
    <Field label="Companion name" required>
      <input
        type="text"
        value={companion.label}
        onChange={(e) =>
          onUpdate((c) => ({ ...c, label: e.target.value }))
        }
        placeholder="e.g. Creditor cover letter"
        className={inputClass}
      />
    </Field>

    <Field label="Type" hint={KIND_HINT[companion.kind]}>
      <div className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-surface-muted p-1">
        {(['fixed', 'branch'] as const).map((kind) => {
          const isSelected = companion.kind === kind;
          return (
            <button
              key={kind}
              type="button"
              onClick={() => onSetKind(kind)}
              className={cn(
                'cursor-pointer rounded-md px-3 py-2 text-xs font-semibold transition-all',
                isSelected
                  ? 'bg-surface text-app-accent-text shadow-sm ring-1 ring-app-accent/30'
                  : 'text-subtle hover:bg-surface/60 hover:text-text-secondary',
              )}
            >
              {kind === 'fixed' ? 'Always runs' : 'Choose at draft time'}
            </button>
          );
        })}
      </div>
    </Field>

    {companion.kind === 'fixed' ? (
      <FixedDetailBody
        companion={companion}
        childOptions={childOptions}
        templateLookup={templateLookup}
        leadVariables={leadVariables}
        onUpdate={(updater) =>
          onUpdate((c) => (c.kind === 'fixed' ? updater(c) : c))
        }
        onCreateTemplate={onCreateTemplate}
      />
    ) : (
      <BranchDetailBody
        companion={companion}
        childOptions={childOptions}
        templateLookup={templateLookup}
        leadVariables={leadVariables}
        onUpdate={(updater) =>
          onUpdate((c) => (c.kind === 'branch' ? updater(c) : c))
        }
        onCreateTemplate={onCreateTemplate}
      />
    )}

    <div className="flex items-center justify-end border-t border-border pt-4">
      <button
        type="button"
        onClick={onRemove}
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-app-danger-text hover:bg-app-danger-soft"
      >
        <FiTrash2 className="h-3 w-3" />
        Remove this companion
      </button>
    </div>
  </div>
);

const Field = ({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) => (
  <div className="space-y-1.5">
    <label className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
      {label}
      {required && (
        <span className="ml-1 text-app-danger-text" aria-label="required">
          *
        </span>
      )}
    </label>
    {children}
    {hint && <p className="text-[11px] text-subtle">{hint}</p>}
  </div>
);

interface TemplatePickerProps {
  value: string | null;
  options: StudioTemplate[];
  onChange: (id: string | null) => void;
  onCreateTemplate: (name: string) => string;
  compact?: boolean;
}

const TemplatePicker = ({
  value,
  options,
  onChange,
  onCreateTemplate,
  compact = false,
}: TemplatePickerProps) => {
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');

  const sizing = compact
    ? 'rounded border border-border bg-surface px-2 py-1.5 text-xs'
    : inputClass;

  const handleCreate = (): void => {
    const trimmed = newName.trim();
    if (!trimmed) return;
    const newId = onCreateTemplate(trimmed);
    onChange(newId);
    setIsCreating(false);
    setNewName('');
  };

  if (isCreating) {
    return (
      <div className="flex items-center gap-1">
        <input
          autoFocus
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              handleCreate();
            }
            if (e.key === 'Escape') {
              setIsCreating(false);
              setNewName('');
            }
          }}
          placeholder="New template name…"
          className={`${sizing} flex-1`}
        />
        <button
          type="button"
          onClick={handleCreate}
          disabled={!newName.trim()}
          className={cn(
            'inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-md px-2 py-1.5 text-xs font-semibold transition-opacity',
            newName.trim()
              ? 'bg-app-accent text-white hover:opacity-90'
              : 'cursor-not-allowed bg-surface-muted text-subtle',
          )}
        >
          <FiCheck className="h-3 w-3" />
          Create
        </button>
        <button
          type="button"
          onClick={() => {
            setIsCreating(false);
            setNewName('');
          }}
          className="cursor-pointer rounded-md p-1.5 text-subtle hover:bg-surface-muted hover:text-text-secondary"
          aria-label="Cancel"
        >
          <FiX className="h-3 w-3" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <select
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        className={`${sizing} flex-1`}
      >
        <option value="">— select a template —</option>
        {options.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => setIsCreating(true)}
        className="inline-flex shrink-0 cursor-pointer items-center gap-1 rounded-md border border-dashed border-border bg-surface px-2 py-1.5 text-xs font-medium text-subtle hover:border-app-accent/40 hover:text-text-secondary"
      >
        <FiPlus className="h-3 w-3" />
        New
      </button>
    </div>
  );
};

const FixedDetailBody = ({
  companion,
  childOptions,
  templateLookup,
  leadVariables,
  onUpdate,
  onCreateTemplate,
}: {
  companion: FixedCompanion;
  childOptions: StudioTemplate[];
  templateLookup: Map<string, StudioTemplate>;
  leadVariables: StudioVariable[];
  onUpdate: (updater: (c: FixedCompanion) => FixedCompanion) => void;
  onCreateTemplate: (name: string) => string;
}) => {
  const childTemplate = companion.child_template_id
    ? templateLookup.get(companion.child_template_id)
    : undefined;

  const handleSlotChange = (slotName: string, config: SlotConfig): void => {
    onUpdate((c) => ({
      ...c,
      slot_configurations: { ...c.slot_configurations, [slotName]: config },
    }));
  };

  return (
    <>
      <Field
        label="Which template runs"
        required
        hint={companion.child_template_id ? undefined : 'Pick the template to run.'}
      >
        <TemplatePicker
          value={companion.child_template_id}
          options={childOptions}
          onChange={(id) =>
            onUpdate((c) => ({ ...c, child_template_id: id }))
          }
          onCreateTemplate={onCreateTemplate}
        />
      </Field>

      {companion.child_template_id && (
        <SlotConfigSection
          childTemplate={childTemplate}
          slotConfigurations={companion.slot_configurations}
          leadVariables={leadVariables}
          onChange={handleSlotChange}
        />
      )}
    </>
  );
};

const BranchDetailBody = ({
  companion,
  childOptions,
  templateLookup,
  leadVariables,
  onUpdate,
  onCreateTemplate,
}: {
  companion: BranchCompanion;
  childOptions: StudioTemplate[];
  templateLookup: Map<string, StudioTemplate>;
  leadVariables: StudioVariable[];
  onUpdate: (updater: (c: BranchCompanion) => BranchCompanion) => void;
  onCreateTemplate: (name: string) => string;
}) => {
  const updateOption = (optionId: string, patch: Partial<BranchOption>): void => {
    onUpdate((c) => ({
      ...c,
      options: c.options.map((o) =>
        o.id === optionId ? { ...o, ...patch } : o,
      ),
    }));
  };

  const removeOption = (optionId: string): void => {
    onUpdate((c) => ({
      ...c,
      options: c.options.filter((o) => o.id !== optionId),
    }));
  };

  const addOption = (): void => {
    onUpdate((c) => ({ ...c, options: [...c.options, newBranchOption()] }));
  };

  return (
    <>
      <Field
        label="Question you'll be asked"
        required
        hint="When drafting this packet, you'll see this question and pick an answer below."
      >
        <input
          type="text"
          value={companion.question}
          onChange={(e) =>
            onUpdate((c) => ({ ...c, question: e.target.value }))
          }
          placeholder="e.g. Is the debtor filing Chapter 7 or Chapter 13?"
          className={inputClass}
        />
      </Field>

      <Field
        label="Possible answers"
        hint="Each answer picks one template to run."
      >
        <div className="space-y-2">
          {companion.options.map((opt) => {
            const optChild = opt.child_template_id
              ? templateLookup.get(opt.child_template_id)
              : undefined;
            const handleSlotChange = (
              slotName: string,
              config: SlotConfig,
            ): void => {
              updateOption(opt.id, {
                slot_configurations: {
                  ...opt.slot_configurations,
                  [slotName]: config,
                },
              });
            };
            return (
              <div
                key={opt.id}
                className="space-y-2 rounded-md border border-border bg-surface-muted/40 p-2"
              >
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={opt.option_label}
                    onChange={(e) =>
                      updateOption(opt.id, { option_label: e.target.value })
                    }
                    placeholder="Answer label"
                    className="w-32 shrink-0 rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-1 focus:ring-app-accent/20"
                  />
                  <span className="shrink-0 text-[11px] text-subtle">→</span>
                  <div className="min-w-0 flex-1">
                    <TemplatePicker
                      value={opt.child_template_id}
                      options={childOptions}
                      onChange={(id) =>
                        updateOption(opt.id, { child_template_id: id })
                      }
                      onCreateTemplate={onCreateTemplate}
                      compact
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => removeOption(opt.id)}
                    className="shrink-0 cursor-pointer rounded p-1 text-subtle hover:bg-app-danger-soft hover:text-app-danger-text"
                    aria-label="Remove option"
                  >
                    <FiX className="h-3 w-3" />
                  </button>
                </div>
                {opt.child_template_id && (
                  <SlotConfigSection
                    childTemplate={optChild}
                    slotConfigurations={opt.slot_configurations}
                    leadVariables={leadVariables}
                    onChange={handleSlotChange}
                  />
                )}
              </div>
            );
          })}
        </div>
        <button
          type="button"
          onClick={addOption}
          className="mt-2 inline-flex cursor-pointer items-center gap-1 rounded-md border border-dashed border-border bg-surface px-2 py-1 text-[11px] font-medium text-subtle hover:border-app-accent/40 hover:text-text-secondary"
        >
          <FiPlus className="h-3 w-3" />
          Add another answer
        </button>
      </Field>
    </>
  );
};

// ─── Slot configuration ──────────────────────────────────────────────
// Renders one editor per child template variable whose source is
// `value_from_parent_bundle`. Each slot lets the paralegal choose how the
// lead fills it: copy a field, extract from the rendered draft, or use a
// fixed value.

interface SlotConfigSectionProps {
  childTemplate: StudioTemplate | undefined;
  slotConfigurations: Record<string, SlotConfig>;
  leadVariables: StudioVariable[];
  onChange: (slotName: string, config: SlotConfig) => void;
}

const SlotConfigSection = ({
  childTemplate,
  slotConfigurations,
  leadVariables,
  onChange,
}: SlotConfigSectionProps) => {
  const slots = findSlotVariables(childTemplate);

  if (!childTemplate) return null;
  if (slots.length === 0) {
    return (
      <p className="text-[11px] italic text-subtle">
        {childTemplate.name} doesn't need anything from this filing.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-text-secondary">
        What {childTemplate.name} needs from this filing
      </p>
      <div className="space-y-2">
        {slots.map((slot) => (
          <SlotConfigEditor
            key={slot.template_variable}
            slotName={slot.template_variable}
            slotDescription={slot.description}
            config={slotConfigurations[slot.template_variable]}
            leadVariables={leadVariables}
            onChange={(config) => onChange(slot.template_variable, config)}
          />
        ))}
      </div>
    </div>
  );
};

interface SlotConfigEditorProps {
  slotName: string;
  slotDescription: string;
  config: SlotConfig | undefined;
  leadVariables: StudioVariable[];
  onChange: (config: SlotConfig) => void;
}

const SlotConfigEditor = ({
  slotName,
  slotDescription,
  config,
  leadVariables,
  onChange,
}: SlotConfigEditorProps) => {
  const kind: SlotConfigKind = config?.kind ?? 'parent_variable';

  const handleKindChange = (newKind: SlotConfigKind): void => {
    onChange(newSlotConfig(newKind));
  };

  return (
    <div className="space-y-2 rounded-md border border-border bg-surface p-2.5">
      <div>
        <p className="font-mono text-[11px] font-semibold text-text-secondary">
          {slotName}
        </p>
        {slotDescription && (
          <p className="text-[10px] text-subtle">{slotDescription}</p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-1 rounded-md border border-border bg-surface-muted p-0.5">
        {(['parent_variable', 'extract_from_draft', 'literal'] as const).map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => handleKindChange(k)}
            className={cn(
              'cursor-pointer rounded px-1.5 py-1 text-[10px] font-semibold transition-all',
              kind === k
                ? 'bg-surface text-app-accent-text shadow-sm ring-1 ring-app-accent/30'
                : 'text-subtle hover:bg-surface/60 hover:text-text-secondary',
            )}
          >
            {SLOT_KIND_LABEL[k]}
          </button>
        ))}
      </div>
      <p className="text-[10px] italic text-subtle">{SLOT_KIND_HINT[kind]}</p>

      {config?.kind === 'parent_variable' && (
        <select
          value={config.parent_variable}
          onChange={(e) =>
            onChange({ kind: 'parent_variable', parent_variable: e.target.value })
          }
          className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-secondary focus:border-app-accent focus:outline-none focus:ring-1 focus:ring-app-accent/20"
        >
          <option value="">— pick a field —</option>
          {leadVariables.map((v) => (
            <option key={v.template_variable} value={v.template_variable}>
              {v.template_variable}
            </option>
          ))}
        </select>
      )}

      {config?.kind === 'extract_from_draft' && (
        <textarea
          value={config.extract_instruction}
          onChange={(e) =>
            onChange({
              kind: 'extract_from_draft',
              extract_instruction: e.target.value,
            })
          }
          placeholder="e.g. the full name of the creditor mentioned in paragraph 2"
          rows={2}
          className="w-full resize-none rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-1 focus:ring-app-accent/20"
        />
      )}

      {config?.kind === 'literal' && (
        <input
          type="text"
          value={config.literal_value}
          onChange={(e) =>
            onChange({ kind: 'literal', literal_value: e.target.value })
          }
          placeholder="e.g. TBD"
          className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-1 focus:ring-app-accent/20"
        />
      )}
    </div>
  );
};
