/**
 * TypeScript shapes mirroring the BE Pydantic models under
 * `bkdrafts-be/src/core/studio_v2/`. Wire shapes — what flows over
 * the HTTP boundary; the mock types in
 * `src/components/studio-v2/types.ts` stay around as the in-memory
 * scratchpad shape (most fields overlap, but the wire shapes are the
 * source of truth for what hits the network).
 */

import type {
  SourceKind,
  WizardSourceParams,
  TemplateConfig,
} from '@/components/studio-v2/types';

// Re-export the source-side types so consumers can import everything
// from `@/types/studio-v2`.
export type { SourceKind, WizardSourceParams, TemplateConfig };

// ─── Composer ──────────────────────────────────────────────────────────

export interface DocumentParseResponseV2 {
  document_id: string;
  parsed: boolean;
  content: string;
  metadata: Record<string, unknown>;
}

export interface MergeOperationV2 {
  new_variable_name: string;
  source_variables: string[];
  description?: string | null;
}

export interface RegenerateTemplateRequest {
  ignored_texts?: string[] | null;
  merges?: MergeOperationV2[] | null;
  regeneration_instruction?: string | null;
}

export interface TemplateFieldV2Extract {
  template_variable: string;
  template_index: number;
  template_property_marker: string | null;
  template_property_marker_aliases: string[];
  template_variable_string: string | null;
  template_identifying_text_match: string | null;
  description: string | null;
  params: WizardSourceParams | null;
}

export interface TemplateGenerateResponseV2 {
  template_id: string;
  name: string;
  template_spec: TemplateFieldV2Extract[];
  original_doc_url: string;
  template_doc_url: string;
}

export interface TemplateRegenerateDiffV2 {
  template_id: string;
  inserted: string[];
  updated: string[];
  deleted: string[];
  preserved_params: string[];
  template_doc_url: string;
}

// ─── Templates CRUD (wire shapes from /api/v3/studio/templates) ───────

export interface TemplateFieldV2Response {
  id: string;
  template_id: string;
  template_variable: string;
  template_property_marker: string | null;
  template_property_marker_aliases: string[];
  template_identifying_text_match: string | null;
  description: string | null;
  template_index: number;
  params: WizardSourceParams | null;
  created_at: string;
  updated_at: string | null;
}

export interface TemplateV2Response {
  id: string;
  firm_id: string | null;
  name: string;
  config: TemplateConfig;
  original_doc_url: string | null;
  template_doc_url: string | null;
  published_at: string | null;
  has_unpublished_changes: boolean;
  // Populated on both list + single-row endpoints so the rail pill
  // can render configuration progress without fetching every
  // template's full spec.
  total_fields: number;
  configured_fields: number;
  created_at: string;
  updated_at: string | null;
  fields: TemplateFieldV2Response[];
}

export interface FieldPatchRequest {
  params: WizardSourceParams | null;
}

export interface BundlingConfigRequest {
  config: TemplateConfig;
}

export interface DeleteTemplateResponseV2 {
  template_id: string;
  deleted: boolean;
}

// ─── Dry-run (Phase 2) ────────────────────────────────────────────────

export interface ResolvedTemplateValueV2 {
  template_variable: string;
  value: string;
  raw_context: string;
  confidence: 'high' | 'medium' | 'low' | 'none';
  note: string;
}

// Pending envelope kinds — every pending field that needs a paralegal
// pick at draft time. Discriminated by `kind`.

export interface PendingDropdownV2 {
  kind: 'dropdown';
  label: string;
  options: string[];
  raw_contexts: string[];
  instruction?: string | null;
}

export interface PendingChipV2 {
  kind: 'chip';
  label: string;
  chips: string[];
  raw_contexts: string[];
  instruction?: string | null;
}

export interface PendingMultiSelectV2 {
  kind: 'multi_select';
  label: string;
  options: string[];
  raw_contexts: string[];
  min_picks: number;
  max_picks: number;
  instruction?: string | null;
}

export interface PendingAuthorTextV2 {
  kind: 'author_text';
  label: string;
  placeholder?: string | null;
  example_output_sentence?: string | null;
}

export interface PendingAuthorDateV2 {
  kind: 'author_date';
  label: string;
  placeholder?: string | null;
}

export interface PendingAuthorDocsV2 {
  kind: 'author_docs';
  label: string;
  accepted_file_types: string[];
}

export interface AttorneyRowV2 {
  id: string;
  display_name: string;
  bar_number?: string | null;
}

export interface PendingAttorneyPickV2 {
  kind: 'attorney_pick';
  label: string;
  options: AttorneyRowV2[];
  multi_select: boolean;
  min_picks: number;
  max_picks: number;
}

export type PendingUserInputV2 =
  | PendingDropdownV2
  | PendingChipV2
  | PendingMultiSelectV2
  | PendingAuthorTextV2
  | PendingAuthorDateV2
  | PendingAuthorDocsV2
  | PendingAttorneyPickV2;

// User pick wire shapes — discriminated by SHAPE (one value / many /
// text+files) not source. The server reads the field's source from the
// spec to interpret the pick correctly.

export interface SingleValuePickV2 {
  value: string;
}

export interface MultiSelectPickV2 {
  picked_values: string[];
}

export interface SupportingDocsPickV2 {
  user_text: string;
  file_urls: string[];
}

export type UserSelectionV2 =
  | SingleValuePickV2
  | MultiSelectPickV2
  | SupportingDocsPickV2;

// Dry-run request/response

/**
 * Field shape inside `TemplateSpecV2Wire`. Matches the BE's
 * `TemplateFieldV2` Pydantic model (extra=forbid) — distinct from
 * `TemplateFieldV2Extract` (composer's reduced shape, has
 * template_variable_string) and `TemplateFieldV2Response` (API
 * response shape, has created_at + updated_at).
 */
export interface TemplateFieldV2Spec {
  id: string;
  template_id: string;
  template_variable: string;
  template_property_marker: string | null;
  template_property_marker_aliases: string[];
  template_identifying_text_match: string | null;
  description: string | null;
  template_index: number;
  params: WizardSourceParams | null;
}

export interface TemplateSpecV2Wire {
  template_id: string;
  fields: TemplateFieldV2Spec[];
}

export interface DryRunRequestV2 {
  template_id: string;
  case_id: string;
  template_spec: TemplateSpecV2Wire;
  bundle_picks?: Record<string, string> | null;
  bundle_role?: string | null;
  bundle_companions?: Array<Record<string, unknown>> | null;
}

export interface DryRunResumeRequestV2 {
  template_id: string;
  case_id: string;
  template_spec: TemplateSpecV2Wire;
  resolved_values: ResolvedTemplateValueV2[];
  pending_inputs?: Record<string, PendingUserInputV2> | null;
  user_picks: Record<string, UserSelectionV2>;
  bundle_picks?: Record<string, string> | null;
  bundle_role?: string | null;
  bundle_companions?: Array<Record<string, unknown>> | null;
}

/** One agreement-word swap the Tier 2 grammar fixer applied to the
 * rendered docx. Mirror of BE `GrammarRepairV2`. Surfaced in the
 * Resolution Log so paralegals can see exactly what the autofixer
 * touched ("at paragraph 7 we changed 'Debtors' → 'Debtor' because
 * the case has a single debtor").
 */
export interface GrammarRepairV2 {
  paragraph_index: number;
  original_word: string;
  replacement_word: string;
  occurrences: number;
  paragraph_preview: string;
  reason: string;
}

export interface BundleChildRunV2 {
  template_id: string;
  template_name: string;
  companion_label: string;
  finalized: {
    resolved_values: ResolvedTemplateValueV2[];
    generated_doc_url: string;
    r2_object_key: string;
    unresolved: string[];
    warnings: string[];
    grammar_repairs: GrammarRepairV2[];
  };
}

export interface DryRunResponseV2 {
  status: 'completed';
  run_id: string;
  template_id: string;
  case_id: string;
  resolved_values: ResolvedTemplateValueV2[];
  generated_doc_url: string;
  r2_object_key: string;
  unresolved: string[];
  warnings: string[];
  grammar_repairs: GrammarRepairV2[];
  children: BundleChildRunV2[];
}

export interface AwaitingInputResponseV2 {
  status: 'awaiting_input';
  run_id: string;
  template_id: string;
  case_id: string;
  template_spec?: TemplateSpecV2Wire | null;
  resolved_values: ResolvedTemplateValueV2[];
  pending_inputs: Record<string, PendingUserInputV2>;
  bundle_picks?: Record<string, string> | null;
}

// Union the route returns — discriminate on `status`.
export type DryRunResultV2 = DryRunResponseV2 | AwaitingInputResponseV2;
