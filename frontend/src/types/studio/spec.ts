
import type { BundleCompanion, TemplateBundleRole } from './bundling';
import type { FieldSource, SourceParams } from './sources';

export type VariableKind = 'physical' | 'virtual';

export interface TemplateVariable {
  template_variable: string;
  template_index: number;
  source: FieldSource | null;
  source_params: SourceParams | null;
  template_property_marker: string | null;
  template_variable_string: string | null;
  template_identifying_text_match: string | null;
  description: string | null;
  
  instruction: string | null;
  
  output_instruction?: string | null;
  read_only?: boolean;
  kind?: VariableKind;
}

export interface TemplateField {
  property_name: string;
  source: FieldSource;
  source_params: SourceParams | null;
  instruction: string | null;
  output_instruction?: string | null;
  kind?: VariableKind;
}

export interface AgentConfig {
  template_id: string;
  template_fields: TemplateField[];
  bundle_role?: TemplateBundleRole;
}

export interface MergeOperation {
  source_variables: string[];
  description?: string | null;
}

export interface DocumentParseResult {
  document_id: string;
  parsed: boolean;
  content: string;
  metadata: {
    format: string;
    filename: string;
    content_length: number;
    paragraph_count: number;
    [key: string]: unknown;
  };
}

// Diff summary returned on the regenerate response so the FE can show
// authors what changed since the previous baseline. None on the initial
// generate path (no baseline exists yet).
export type RemovedReason = 'merged' | 'ignored' | 'unexpected';

export interface RemovedEntry {
  name: string;
  reason: RemovedReason;
  merged_into?: string | null;
}

export interface RegenerateDiff {
  added: string[];
  removed: RemovedEntry[];
  preserved: string[];
}

export interface GenerateTemplateResult {
  template_id: string;
  template_name: string;
  template_spec: TemplateVariable[];
  generated: boolean;
  original_doc_url: string;
  template_doc_url: string;
  diff?: RegenerateDiff | null;
}

export type TemplateStatus = 'draft' | 'published' | 'archived';

export interface DraftTemplateListItem {
  id: string;
  name: string;
  original_doc_url: string | null;
  template_doc_url: string | null;
  template_spec: TemplateVariable[] | null;
  agent_config: AgentConfig | null;
  bundle_role: TemplateBundleRole;
  bundle_companions: BundleCompanion[] | null;
  created_at: string | null;
  is_active: boolean;

  status?: TemplateStatus;
  doc_type?: string | null;
  published_at?: string | null;
  published_by?: string | null;
}

export type DraftTemplateDetail = DraftTemplateListItem;

export type StudioFlowState =
  | 'new'
  | 'generated'
  | 'configuring'
  | 'verified'
  | 'persisted';
