import { useMemo, useState, type ReactElement } from 'react';
import { LuTriangleAlert } from 'react-icons/lu';
import { useStudioStore } from '@/stores/useStudioStore';
import {
  countIncompleteSlots,
  isSlotConfigComplete,
  type BranchBundleCompanion,
  type BranchOption,
  type BundleCompanion,
  type DraftTemplateListItem,
  type FixedBundleCompanion,
  type SlotConfig,
} from '@/types/studio';

// Phase 1B Bundle Companions editor.
// Bound to useStudioStore.bundleCompanions / setBundleCompanions. Reads
// the live list of child-only templates from the studio's templates list
// (filtered by bundle_role === 'child_only') instead of a hardcoded mock
// catalog. Slots are derived from the selected child's template_spec —
// every variable whose source is 'inherit_from_parent' is a slot the
// parent must configure here.

const newCompanionId = (): string =>
  `companion-${Math.random().toString(36).slice(2, 8)}`;

const buildBranchCompanion = (firstChildId: string): BranchBundleCompanion => ({
  kind: 'branch',
  label: '',
  question: '',
  options: [
    {
      label: 'Yes',
      child_template_id: firstChildId,
      slot_configurations: {},
    },
    {
      label: 'No',
      child_template_id: firstChildId,
      slot_configurations: {},
    },
  ],
});

const buildFixedCompanion = (firstChildId: string): FixedBundleCompanion => ({
  kind: 'fixed',
  label: 'New Companion',
  child_template_id: firstChildId,
  slot_configurations: {},
});

// `BundleCompanion` from the BE doesn't carry an id, but the editor needs
// stable React keys for ordering. We attach an ephemeral id locally and
// strip it on save (the persisted shape doesn't need it — companion order
// in the array IS the identity).
type WithId<T> = T & { _editorId: string };

const ensureEditorIds = (companions: BundleCompanion[]): WithId<BundleCompanion>[] =>
  companions.map((c) => ({ ...c, _editorId: newCompanionId() }));

const stripEditorIds = (companions: WithId<BundleCompanion>[]): BundleCompanion[] =>
  companions.map(({ _editorId, ...rest }) => {
    void _editorId;
    return rest as BundleCompanion;
  });

const slotsForChild = (child: DraftTemplateListItem | undefined): string[] => {
  if (!child?.template_spec) return [];
  return child.template_spec
    .filter((v) => v.source === 'inherit_from_parent')
    .map((v) => v.template_variable);
};

const collectParentVariables = (
  spec: ReturnType<typeof useStudioStore.getState>['templateSpec'],
): string[] => spec.map((v) => v.template_variable).filter(Boolean);

const defaultSlotConfig = (slotName: string): SlotConfig => {
  // Hint at the natural shape for *_title slots (LLM extraction is usually
  // the right move) but never pre-fill the actual value — the author MUST
  // explicitly configure each slot. Pre-filling a parent_variable was the
  // old behavior; it silently shipped wrong defaults.
  if (slotName === 'docket_title' || slotName.endsWith('_title')) {
    return { kind: 'extract_from_draft', extract_instruction: '' };
  }
  return { kind: 'parent_variable', parent_variable: '' };
};

const initSlotConfigs = (
  child: DraftTemplateListItem | undefined,
): Record<string, SlotConfig> => {
  const out: Record<string, SlotConfig> = {};
  for (const slot of slotsForChild(child)) {
    out[slot] = defaultSlotConfig(slot);
  }
  return out;
};

export const BundleCompanionsEditor = (): ReactElement => {
  const bundleCompanions = useStudioStore((s) => s.bundleCompanions);
  const setBundleCompanions = useStudioStore((s) => s.setBundleCompanions);
  const templates = useStudioStore((s) => s.templates);
  const templateSpec = useStudioStore((s) => s.templateSpec);

  const childTemplates = useMemo(
    () => templates.filter((t) => t.bundle_role === 'child_only'),
    [templates],
  );
  const parentVariables = useMemo(() => collectParentVariables(templateSpec), [templateSpec]);
  const childTemplateById = useMemo(
    () => new Map(childTemplates.map((t) => [t.id, t])),
    [childTemplates],
  );

  // Local editor copy so each row gets a stable React key. Sync back to
  // store whenever the user edits.
  const [editorCompanions, setEditorCompanions] = useState<WithId<BundleCompanion>[]>(() =>
    ensureEditorIds(bundleCompanions),
  );

  const incompleteSlotCount = useMemo(
    () => countIncompleteSlots(
      editorCompanions,
      (childId) => slotsForChild(childTemplateById.get(childId)),
    ),
    [editorCompanions, childTemplateById],
  );

  const commit = (next: WithId<BundleCompanion>[]): void => {
    setEditorCompanions(next);
    setBundleCompanions(stripEditorIds(next));
  };

  const firstChildId = childTemplates[0]?.id ?? '';

  const addBranch = (): void => {
    const next = buildBranchCompanion(firstChildId);
    next.options.forEach((opt) => {
      opt.slot_configurations = initSlotConfigs(
        childTemplateById.get(opt.child_template_id),
      );
    });
    commit([...editorCompanions, { ...next, _editorId: newCompanionId() }]);
  };

  const addFixed = (): void => {
    const next = buildFixedCompanion(firstChildId);
    next.slot_configurations = initSlotConfigs(
      childTemplateById.get(next.child_template_id),
    );
    commit([...editorCompanions, { ...next, _editorId: newCompanionId() }]);
  };

  const removeCompanion = (id: string): void =>
    commit(editorCompanions.filter((c) => c._editorId !== id));

  const updateCompanion = (id: string, patch: Partial<BundleCompanion>): void => {
    commit(
      editorCompanions.map((c) =>
        c._editorId === id ? ({ ...c, ...patch } as WithId<BundleCompanion>) : c,
      ),
    );
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-subtle">
            Bundle Companions
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-muted">
            Children that ship alongside this parent at draft time. Each
            companion is either <strong className="font-semibold">fixed</strong>{' '}
            (always include this child) or{' '}
            <strong className="font-semibold">branched</strong> (a yes/no
            question routes to one of N children). For each attached child,
            configure how to fill its slots.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={addBranch}
            disabled={childTemplates.length === 0}
            className="rounded-lg border border-app-accent-soft bg-surface px-2.5 py-1.5 text-xs font-semibold text-app-accent-text hover:bg-app-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            + Branch companion
          </button>
          <button
            type="button"
            onClick={addFixed}
            disabled={childTemplates.length === 0}
            className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-semibold text-text-secondary hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
          >
            + Fixed companion
          </button>
        </div>
      </div>

      {childTemplates.length === 0 && (
        <div className="mb-3 rounded-lg border border-dashed border-amber-300 bg-app-warning-soft px-3 py-3 text-xs text-amber-800">
          No child-only templates available. Mark a template as{' '}
          <strong className="font-semibold">Child only</strong> on its Bundling
          tab first, then come back here to attach it.
        </div>
      )}

      {editorCompanions.length === 0 && childTemplates.length > 0 && (
        <div className="rounded-lg border border-dashed border-border bg-surface-muted px-3 py-6 text-center">
          <p className="text-xs text-muted">
            No companions yet. Add a fixed companion for &ldquo;always include
            this child&rdquo;, or a branch for a yes/no question that picks
            between children.
          </p>
        </div>
      )}

      {incompleteSlotCount > 0 && (
        <div
          className="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800"
          role="status"
        >
          <LuTriangleAlert
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600"
            aria-hidden="true"
          />
          <p>
            <strong className="font-semibold">{incompleteSlotCount}</strong>{' '}
            slot{incompleteSlotCount === 1 ? '' : 's'} need configuration
            before this template can be saved.
          </p>
        </div>
      )}

      <div className="space-y-3">
        {editorCompanions.map((companion) => (
          <CompanionCard
            key={companion._editorId}
            companion={companion}
            childTemplates={childTemplates}
            childTemplateById={childTemplateById}
            parentVariables={parentVariables}
            onChange={(patch) => updateCompanion(companion._editorId, patch)}
            onDelete={() => removeCompanion(companion._editorId)}
          />
        ))}
      </div>
    </div>
  );
};

interface CompanionCardProps {
  companion: WithId<BundleCompanion>;
  childTemplates: DraftTemplateListItem[];
  childTemplateById: Map<string, DraftTemplateListItem>;
  parentVariables: string[];
  onChange: (patch: Partial<BundleCompanion>) => void;
  onDelete: () => void;
}

const CompanionCard = ({
  companion,
  childTemplates,
  childTemplateById,
  parentVariables,
  onChange,
  onDelete,
}: CompanionCardProps): ReactElement => {
  const isBranch = companion.kind === 'branch';

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={`grid h-7 w-7 shrink-0 place-items-center rounded-md ${
              isBranch
                ? 'bg-app-accent-soft text-app-accent-text'
                : 'bg-emerald-100 text-emerald-700'
            }`}
          >
            {isBranch ? '🔀' : '📌'}
          </span>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wider text-subtle">
              {isBranch ? 'Branch companion' : 'Fixed companion'}
            </p>
            <p className="text-sm font-semibold text-text-secondary">
              {companion.label || <em className="italic text-subtle">Untitled</em>}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onDelete}
          className="rounded-lg border border-app-danger-soft bg-surface px-2 py-1 text-[11px] font-semibold text-app-danger-text hover:bg-app-danger-soft"
        >
          Delete
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary">
            Label
          </label>
          <input
            type="text"
            value={companion.label}
            onChange={(e) => onChange({ label: e.target.value })}
            placeholder="e.g. Certificate of Service"
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
        </div>

        {isBranch ? (
          <BranchEditor
            companion={companion as WithId<BranchBundleCompanion>}
            childTemplates={childTemplates}
            childTemplateById={childTemplateById}
            parentVariables={parentVariables}
            onChange={onChange}
          />
        ) : (
          <FixedEditor
            companion={companion as WithId<FixedBundleCompanion>}
            childTemplates={childTemplates}
            childTemplateById={childTemplateById}
            parentVariables={parentVariables}
            onChange={onChange}
          />
        )}
      </div>
    </div>
  );
};

const FixedEditor = ({
  companion,
  childTemplates,
  childTemplateById,
  parentVariables,
  onChange,
}: {
  companion: WithId<FixedBundleCompanion>;
  childTemplates: DraftTemplateListItem[];
  childTemplateById: Map<string, DraftTemplateListItem>;
  parentVariables: string[];
  onChange: (patch: Partial<BundleCompanion>) => void;
}): ReactElement => {
  const child = childTemplateById.get(companion.child_template_id);
  return (
    <>
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Child template
        </label>
        <ChildTemplatePicker
          value={companion.child_template_id}
          options={childTemplates}
          onChange={(childId) =>
            onChange({
              child_template_id: childId,
              slot_configurations: initSlotConfigs(
                childTemplateById.get(childId),
              ),
            } as Partial<FixedBundleCompanion>)
          }
        />
      </div>

      <SlotConfigList
        slotNames={slotsForChild(child)}
        slotConfigurations={companion.slot_configurations}
        parentVariables={parentVariables}
        onChangeSlot={(slotName, slotConfig) =>
          onChange({
            slot_configurations: {
              ...companion.slot_configurations,
              [slotName]: slotConfig,
            },
          } as Partial<FixedBundleCompanion>)
        }
      />
    </>
  );
};

const BranchEditor = ({
  companion,
  childTemplates,
  childTemplateById,
  parentVariables,
  onChange,
}: {
  companion: WithId<BranchBundleCompanion>;
  childTemplates: DraftTemplateListItem[];
  childTemplateById: Map<string, DraftTemplateListItem>;
  parentVariables: string[];
  onChange: (patch: Partial<BundleCompanion>) => void;
}): ReactElement => {
  const updateOption = (idx: number, patch: Partial<BranchOption>): void => {
    const nextOptions = companion.options.map((o, i) => (i === idx ? { ...o, ...patch } : o));
    onChange({ options: nextOptions } as Partial<BranchBundleCompanion>);
  };

  const addOption = (): void => {
    const childId = childTemplates[0]?.id ?? '';
    const opt: BranchOption = {
      label: `Option ${companion.options.length + 1}`,
      child_template_id: childId,
      slot_configurations: initSlotConfigs(childTemplateById.get(childId)),
    };
    onChange({ options: [...companion.options, opt] } as Partial<BranchBundleCompanion>);
  };

  const removeOption = (idx: number): void => {
    const nextOptions = companion.options.filter((_, i) => i !== idx);
    onChange({ options: nextOptions } as Partial<BranchBundleCompanion>);
  };

  return (
    <>
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Question
        </label>
        <input
          type="text"
          value={companion.question}
          onChange={(e) => onChange({ question: e.target.value } as Partial<BranchBundleCompanion>)}
          placeholder="e.g. Includes a Notice of Hearing?"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        />
      </div>

      <div>
        <div className="mb-1 flex items-baseline justify-between gap-2">
          <label className="block text-xs font-semibold uppercase tracking-wider text-text-secondary">
            Options
          </label>
          <button
            type="button"
            onClick={addOption}
            disabled={childTemplates.length === 0}
            className="text-[11px] font-semibold text-app-accent-text hover:underline disabled:cursor-not-allowed disabled:opacity-50"
          >
            + Add option
          </button>
        </div>
        <p className="mb-2 text-[11px] text-subtle">
          Each option pairs an answer label with the child template that gets
          included when the user picks it. Configure each option&rsquo;s slots
          below.
        </p>
        <div className="space-y-3">
          {companion.options.map((option, idx) => {
            const child = childTemplateById.get(option.child_template_id);
            return (
              <div
                key={`option-${idx}`}
                className="rounded-lg border border-border bg-surface-muted p-3"
              >
                <div className="flex flex-wrap items-end gap-2">
                  <div className="min-w-[160px] flex-1">
                    <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-subtle">
                      Answer label
                    </label>
                    <input
                      type="text"
                      value={option.label}
                      onChange={(e) => updateOption(idx, { label: e.target.value })}
                      placeholder="Yes / No"
                      className="w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none"
                    />
                  </div>
                  <span className="self-center pb-1.5 text-sm text-subtle">→</span>
                  <div className="min-w-[200px] flex-[2]">
                    <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-subtle">
                      Child template
                    </label>
                    <ChildTemplatePicker
                      value={option.child_template_id}
                      options={childTemplates}
                      onChange={(childId) =>
                        updateOption(idx, {
                          child_template_id: childId,
                          slot_configurations: initSlotConfigs(
                            childTemplateById.get(childId),
                          ),
                        })
                      }
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => removeOption(idx)}
                    aria-label="Remove option"
                    className="self-end rounded border border-app-danger-soft bg-surface px-2 py-1.5 text-[11px] font-semibold text-app-danger-text hover:bg-app-danger-soft"
                  >
                    ×
                  </button>
                </div>

                <SlotConfigList
                  slotNames={slotsForChild(child)}
                  slotConfigurations={option.slot_configurations}
                  parentVariables={parentVariables}
                  compact
                  onChangeSlot={(slotName, slotConfig) =>
                    updateOption(idx, {
                      slot_configurations: {
                        ...option.slot_configurations,
                        [slotName]: slotConfig,
                      },
                    })
                  }
                />
              </div>
            );
          })}
          {companion.options.length === 0 && (
            <div className="rounded border border-dashed border-border bg-surface-muted px-3 py-3 text-center text-[11px] text-muted">
              No options. A branch needs at least two — typically Yes and No.
            </div>
          )}
        </div>
      </div>

      <div className="rounded-lg bg-surface-muted px-3 py-2 text-[11px] leading-snug text-muted">
        <span className="font-semibold text-text-secondary">Runtime:</span> when
        this parent finishes resolving, the engine pauses and asks the question
        above. The user&rsquo;s pick includes the matching child; both finalize
        together so the user gets two docxes. (Branch resolution + child run
        ship in Phase 2.)
      </div>
    </>
  );
};

const SlotConfigList = ({
  slotNames,
  slotConfigurations,
  parentVariables,
  onChangeSlot,
  compact = false,
}: {
  slotNames: string[];
  slotConfigurations: Record<string, SlotConfig>;
  parentVariables: string[];
  onChangeSlot: (slotName: string, config: SlotConfig) => void;
  compact?: boolean;
}): ReactElement | null => {
  // Always default-expanded so slot configuration is visible the moment a
  // companion is added — incomplete slots that need a value MUST be obvious
  // without an extra click. User can still collapse manually.
  const [isExpanded, setIsExpanded] = useState<boolean>(true);

  if (slotNames.length === 0) {
    return (
      <div className="mt-3 rounded-lg border border-dashed border-border bg-surface-muted px-3 py-3 text-[11px] text-muted">
        This child template has no <code className="font-mono">inherit_from_parent</code>{' '}
        slots — nothing to configure here.
      </div>
    );
  }

  return (
    <div className={compact ? 'mt-3' : 'mt-4'}>
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between rounded-lg bg-indigo-50/40 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-indigo-700 hover:bg-indigo-100/40"
      >
        <span>
          Slot configurations · {slotNames.length} slot{slotNames.length === 1 ? '' : 's'}
        </span>
        <svg
          aria-hidden="true"
          className={`h-3.5 w-3.5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          viewBox="0 0 24 24"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isExpanded && (
        <div className="mt-2 space-y-2">
          {slotNames.map((slotName) => {
            // `initSlotConfigs` populates every required slot with an EMPTY
            // payload (e.g. `parent_variable: ''`); the row uses
            // `isSlotConfigComplete` to flag those as "Needs configuration"
            // rather than silently auto-filling with `parentVariables[0]`.
            const config: SlotConfig = slotConfigurations[slotName] ?? {
              kind: 'parent_variable',
              parent_variable: '',
            };
            const isComplete = isSlotConfigComplete(config);
            return (
              <SlotConfigRow
                key={slotName}
                slotName={slotName}
                config={config}
                isComplete={isComplete}
                parentVariables={parentVariables}
                onChange={(next) => onChangeSlot(slotName, next)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};

const SLOT_KIND_OPTIONS: ReadonlyArray<{ value: SlotConfig['kind']; label: string }> = [
  { value: 'parent_variable', label: 'Parent variable' },
  { value: 'extract_from_draft', label: 'Extract from draft' },
  { value: 'literal', label: 'Literal value' },
];

const SlotConfigRow = ({
  slotName,
  config,
  isComplete,
  parentVariables,
  onChange,
}: {
  slotName: string;
  config: SlotConfig;
  isComplete: boolean;
  parentVariables: string[];
  onChange: (config: SlotConfig) => void;
}): ReactElement => {
  const switchKind = (kind: SlotConfig['kind']): void => {
    if (kind === config.kind) return;
    // No auto-fill on kind switch either — the author must explicitly pick
    // a parent variable / write an extraction instruction. `literal` is the
    // single exception (empty literal is a deliberate, valid choice).
    if (kind === 'parent_variable') {
      onChange({ kind: 'parent_variable', parent_variable: '' });
    } else if (kind === 'extract_from_draft') {
      onChange({ kind: 'extract_from_draft', extract_instruction: '' });
    } else {
      onChange({ kind: 'literal', literal_value: '' });
    }
  };

  const rowClass = isComplete
    ? 'rounded-lg border border-border bg-surface p-3'
    : 'rounded-lg border border-amber-300 bg-amber-50/60 p-3';

  return (
    <div className={rowClass}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <p className="font-mono text-xs font-semibold text-text-secondary">{slotName}</p>
          {!isComplete && (
            <span
              title="This slot needs a value before the template can be saved."
              className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700"
            >
              <LuTriangleAlert className="h-3 w-3" aria-hidden="true" />
              Needs configuration
            </span>
          )}
        </div>
        <div className="inline-flex rounded-lg border border-border bg-surface-muted p-0.5 text-[11px]">
          {SLOT_KIND_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => switchKind(opt.value)}
              className={`rounded-md px-2 py-1 font-semibold transition-colors ${
                config.kind === opt.value
                  ? 'bg-surface text-app-accent-text shadow-sm'
                  : 'text-muted hover:text-text-secondary'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2">
        {config.kind === 'parent_variable' && (
          <div>
            <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-subtle">
              Pull from parent variable
            </label>
            <select
              value={config.parent_variable}
              onChange={(e) =>
                onChange({ kind: 'parent_variable', parent_variable: e.target.value })
              }
              className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-secondary focus:border-app-accent focus:outline-none"
            >
              {parentVariables.length === 0 && (
                <option value="">— no parent variables —</option>
              )}
              {parentVariables.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        )}
        {config.kind === 'extract_from_draft' && (
          <div>
            <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-subtle">
              Extraction instruction
            </label>
            <textarea
              rows={3}
              value={config.extract_instruction}
              onChange={(e) =>
                onChange({ kind: 'extract_from_draft', extract_instruction: e.target.value })
              }
              placeholder="e.g. The bold heading line after the case caption — the FULL filed motion title."
              className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none"
            />
            <p className="mt-1 text-[10px] text-subtle">
              Phase 2 wires this up — Phase 1B accepts the configuration but the
              resolver returns a placeholder until the bundling engine threads
              parent draft text into the child&rsquo;s context.
            </p>
          </div>
        )}
        {config.kind === 'literal' && (
          <div>
            <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-subtle">
              Literal value
            </label>
            <input
              type="text"
              value={config.literal_value}
              onChange={(e) =>
                onChange({ kind: 'literal', literal_value: e.target.value })
              }
              placeholder="e.g. PDR"
              className="w-full rounded border border-border bg-surface px-2 py-1.5 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none"
            />
          </div>
        )}
      </div>
    </div>
  );
};

const ChildTemplatePicker = ({
  value,
  options,
  onChange,
}: {
  value: string;
  options: DraftTemplateListItem[];
  onChange: (id: string) => void;
}): ReactElement => (
  <select
    value={value}
    onChange={(e) => onChange(e.target.value)}
    className="w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-text-secondary focus:border-app-accent focus:outline-none"
  >
    <option value="">— pick a child template —</option>
    {options.map((tpl) => (
      <option key={tpl.id} value={tpl.id}>
        {tpl.name} ({tpl.id})
      </option>
    ))}
  </select>
);

export default BundleCompanionsEditor;
