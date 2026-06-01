// FE-side types for the bundling layer — mirror src/core/agents/types/bundling.py.
// Keep field names + literal-discriminator values in sync with the BE.

export type TemplateBundleRole = 'standalone' | 'parent' | 'child_only';

// ─── Slot configuration (parent's per-slot filling strategy) ──────────

export interface ParentVariableSlotConfig {
  kind: 'parent_variable';
  parent_variable: string;
}

export interface ExtractFromDraftSlotConfig {
  kind: 'extract_from_draft';
  extract_instruction: string;
}

export interface LiteralSlotConfig {
  kind: 'literal';
  literal_value: string;
}

export type SlotConfig =
  | ParentVariableSlotConfig
  | ExtractFromDraftSlotConfig
  | LiteralSlotConfig;

// ─── Companion entry on a parent's bundling spec ──────────────────────

export interface BranchOption {
  label: string;
  child_template_id: string;
  slot_configurations: Record<string, SlotConfig>;
}

export interface FixedBundleCompanion {
  kind: 'fixed';
  label: string;
  child_template_id: string;
  slot_configurations: Record<string, SlotConfig>;
}

export interface BranchBundleCompanion {
  kind: 'branch';
  label: string;
  question: string;
  options: BranchOption[];
}

export type BundleCompanion = FixedBundleCompanion | BranchBundleCompanion;

// ─── Slot-completeness helpers ────────────────────────────────────────
// Mirror the BE's `_is_slot_config_complete` rule in
// src/core/components/engines/template/crud.py — kept in sync so the FE
// can gate Save before the BE has to reject with 400. `literal` is the
// only variant that permits an empty payload (an intentional blank is a
// valid template choice).

export const isSlotConfigComplete = (
  config: SlotConfig | undefined,
): boolean => {
  if (!config) return false;
  switch (config.kind) {
    case 'parent_variable':
      return config.parent_variable.trim().length > 0;
    case 'extract_from_draft':
      return config.extract_instruction.trim().length > 0;
    case 'literal':
      return true;
  }
};

/**
 * Count of slots across every companion (Fixed + each BranchOption) that
 * still need configuration. Pass `requiredSlotsByChild(childId)` so the
 * caller controls how child template specs are loaded (avoids coupling
 * the type module to a specific data source).
 */
export const countIncompleteSlots = (
  companions: BundleCompanion[],
  requiredSlotsByChild: (childTemplateId: string) => string[],
): number => {
  let n = 0;
  const visit = (
    childId: string,
    slots: Record<string, SlotConfig>,
  ): void => {
    for (const slot of requiredSlotsByChild(childId)) {
      if (!isSlotConfigComplete(slots[slot])) n += 1;
    }
  };
  for (const companion of companions) {
    if (companion.kind === 'fixed') {
      visit(companion.child_template_id, companion.slot_configurations);
    } else {
      for (const option of companion.options) {
        visit(option.child_template_id, option.slot_configurations);
      }
    }
  }
  return n;
};

// ─── Child-side "Inherit from Parent" source params ───────────────────

export interface InheritFromParentSourceParams {
  fallback_value?: string | null;
}
