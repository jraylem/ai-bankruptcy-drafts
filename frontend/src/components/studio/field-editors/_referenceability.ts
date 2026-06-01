/**
 * Eligibility predicates for variable-reference pickers.
 *
 * A template variable can be referenced as `{{name}}` inside another
 * variable's text_query / dependent-variable picker based on the
 * referencer's stage:
 *
 * - **Any referencer** can target variables whose effective stage is
 *   LLM_DRAFT or SYSTEM_GENERATED (resolved before user-input pause).
 * - **LLM_DRAFT referencers** (case_vector, gmail, court_drive,
 *   law_practice_vector, constants, system_generated) can ALSO target
 *   USER_INPUT-rooted variables — the BE's Path B pipeline defers
 *   those fetches to Pass 3 in `run_resume_stages`, after the user
 *   pick + late auto-derive populate the picked value's descendants.
 * - **USER_INPUT referencers** (dropdowns, reco_chips, etc.) cannot
 *   target other USER_INPUT-rooted variables — same-pause circular
 *   dependency, no ordering possible.
 *
 * For `auto_derived_from_variable` targets, the effective source is
 * the source of the ROOT parent at the bottom of the auto_derived
 * chain. Mirror of the BE helper `root_parent_stage` in
 * bkdrafts-be/src/core/agents/types/spec.py — keep these in sync.
 */

import type { FieldSource, TemplateVariable } from '@/types/studio';

const LLM_DRAFT_SOURCES: ReadonlySet<FieldSource> = new Set<FieldSource>([
  'gmail',
  'court_drive',
  'case_vector',
  'law_practice_vector',
  'constants',
  'system_generated',
]);

const USER_INPUT_SOURCES: ReadonlySet<FieldSource> = new Set<FieldSource>([
  'group_dropdown_from_gmail',
  'group_dropdown_from_court_drive',
  'reco_chips_from_gmail',
  'reco_chips_from_court_drive',
  'reco_chips_from_case_vector',
  'reco_chips_from_dependent_variables',
  'dropdown_from_gmail',
  'dropdown_from_court_drive',
  'dropdown_from_case_vector',
  'dropdown_from_constants',
  'user_input_with_supporting_docs',
  'user_input_plain_text',
  'user_input_date',
  'multi_select_from_case_vector',
  'multi_select_from_gmail',
]);

/** Sources eligible for reference from ANY referencer — resolved pre-pause. */
export const REFERENCEABLE_SOURCES: ReadonlySet<FieldSource> = LLM_DRAFT_SOURCES;

/** Sources that, when reached transitively via auto_derived, are eligible
 *  ONLY from a LLM_DRAFT referencer (Path B wave-B reach). */
const LLM_DRAFT_REFERENCER_EXTRA_SOURCES: ReadonlySet<FieldSource> = USER_INPUT_SOURCES;

/**
 * Walk the auto_derived chain to the root parent and return that parent's source.
 *
 * Returns `null` when:
 *   - the variable's source is `null` (unbound)
 *   - a cycle is detected (cycle validator surfaces the real error elsewhere;
 *     here we just refuse to infinite-loop)
 *   - a parent in the chain is missing from `byName`
 *
 * Non-auto_derived variables short-circuit and return their own source.
 */
export const rootParentSource = (
  v: TemplateVariable,
  byName: Map<string, TemplateVariable>,
): FieldSource | null => {
  const seen = new Set<string>();
  let cur: TemplateVariable = v;
  while (cur.source === 'auto_derived_from_variable') {
    if (seen.has(cur.template_variable)) return null;
    seen.add(cur.template_variable);
    const params = cur.source_params as { dependent_variable?: string } | null;
    const parentName = params?.dependent_variable;
    if (!parentName) return null;
    const parent = byName.get(parentName);
    if (!parent) return null;
    cur = parent;
  }
  return cur.source;
};

/**
 * Walks the same chain as rootParentSource but returns true ONLY when
 * the chain is well-formed (no cycle, all parents present) AND the
 * terminal parent has `source === null`. Distinguishes "unbound at
 * the root" (placeholder, will be bound later) from "broken chain"
 * (cycle, missing parent) — both of which make rootParentSource
 * return null. Mirrors BE `root_parent_is_unbound` in
 * bkdrafts-be/src/core/agents/types/spec.py.
 */
export const rootParentIsUnbound = (
  v: TemplateVariable,
  byName: Map<string, TemplateVariable>,
): boolean => {
  const seen = new Set<string>();
  let cur: TemplateVariable = v;
  while (cur.source === 'auto_derived_from_variable') {
    if (seen.has(cur.template_variable)) return false;
    seen.add(cur.template_variable);
    const params = cur.source_params as { dependent_variable?: string } | null;
    const parentName = params?.dependent_variable;
    if (!parentName) return false;
    const parent = byName.get(parentName);
    if (!parent) return false;
    cur = parent;
  }
  return cur.source === null;
};

/**
 * Set of root-parent sources a target can have AND still be eligible
 * when referenced from a variable bound to `referencerSource`.
 * Mirrors the BE `_allowed_target_stages_for` helper in validators.py.
 */
const allowedRootSourcesFor = (
  referencerSource: FieldSource | null,
): ReadonlySet<FieldSource> => {
  if (referencerSource && LLM_DRAFT_SOURCES.has(referencerSource)) {
    // LLM_DRAFT referencer: pre-pause sources PLUS USER_INPUT-rooted
    // (Path B wave-B picks them up post-pause in run_resume_stages).
    return new Set<FieldSource>([
      ...LLM_DRAFT_SOURCES,
      ...LLM_DRAFT_REFERENCER_EXTRA_SOURCES,
    ]);
  }
  // USER_INPUT (or unknown) referencer: only pre-pause sources.
  return REFERENCEABLE_SOURCES;
};

/**
 * True iff `v` can be referenced as `{{name}}` from a variable whose
 * source is `referencerSource`. The referencer's stage gates which
 * effective root-parent sources are permitted on the target.
 *
 * Pass `referencerSource = null` (the default) for the conservative
 * read — i.e. "would this variable be eligible from ANY referencer".
 * Equivalent to LLM_DRAFT/SYSTEM_GENERATED-only.
 */
export const isEligibleForReference = (
  v: TemplateVariable,
  byName: Map<string, TemplateVariable>,
  referencerSource: FieldSource | null = null,
): boolean => {
  // Placeholder rule: auto_derived targets whose root parent isn't bound
  // yet are referenceable from LLM_DRAFT-class referencers at compose
  // time. Lets the author wire references before deciding on a source
  // for the virtual parent. Mirrors the BE validator carve-out.
  if (
    v.source === 'auto_derived_from_variable' &&
    rootParentIsUnbound(v, byName) &&
    referencerSource !== null &&
    LLM_DRAFT_SOURCES.has(referencerSource)
  ) {
    return true;
  }
  const effective = rootParentSource(v, byName);
  if (effective === null) return false;
  return allowedRootSourcesFor(referencerSource).has(effective);
};
