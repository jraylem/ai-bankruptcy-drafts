
import type { TemplateVariable } from './spec';

export interface ResolvedTemplateValue {
  property_name: string;
  value: string;
  reasoning: string;
  confidence: 'high' | 'medium' | 'low';
}

export interface PipelineValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface BundleChildDoc {
  template_id: string;
  template_name: string;
  companion_label: string;
  generated_doc_url: string;
  resolved_values: ResolvedTemplateValue[];
  warnings: string[];
}

export interface DryRunResult {
  status: 'completed';
  template_id: string;
  resolved_values: ResolvedTemplateValue[];
  generated_doc_url: string;
  validation: PipelineValidation;
  can_generate: boolean;
  children?: BundleChildDoc[];
}

export interface DraftResult {
  status: 'completed';
  template_id: string;
  case_id: string;
  resolved_values: ResolvedTemplateValue[];
  generated_doc_url: string;
  validation: PipelineValidation;
  children?: BundleChildDoc[];
}

export interface DropdownOption {
  left: string;
  right: string;
  display_value?: string | null;
}

export interface PendingGroupDropdown {
  kind: 'group_dropdown';
  group_label: string;
  left_variable: string;
  left_label: string;
  right_variable: string;
  right_label: string;
  options: DropdownOption[];
}

export interface PendingRecoChips {
  kind: 'reco_chips';
  label: string;
  chips: string[];
}

export interface PendingDropdown {
  kind: 'dropdown';
  label: string;
  options: string[];
}

export interface PendingUserInputWithDocs {
  kind: 'user_input_with_docs';
  label: string;
  accepted_file_types: string[];
}

export interface PendingDropdownFromConstants {
  kind: 'dropdown_from_constants';
  label: string;
  options: string[];
}

export interface PendingUserInputDate {
  kind: 'user_input_date';
  label: string;
  placeholder?: string | null;
  format: string;
}

export interface PendingUserInputPlainText {
  kind: 'user_input_plain_text';
  label: string;
  placeholder?: string | null;
  example_output_sentence: string;
}

export interface PendingMultiSelect {
  kind: 'multi_select';
  label: string;
  instruction?: string | null;
  options: string[];
  min_picks: number;
  max_picks?: number | null;
}

export type PendingUserInput =
  | PendingGroupDropdown
  | PendingRecoChips
  | PendingDropdown
  | PendingUserInputWithDocs
  | PendingDropdownFromConstants
  | PendingUserInputPlainText
  | PendingUserInputDate
  | PendingMultiSelect;

export interface AwaitingInputResult {
  status: 'awaiting_input';
  run_id: string;
  template_id: string;
  case_id: string;
  template_spec: TemplateVariable[] | null;
  resolved_values: ResolvedTemplateValue[];
  pending_inputs: Record<string, PendingUserInput>;
  bundle_picks?: Record<string, string> | null;
}

export interface GroupDropdownPick {
  left: string;
  right: string;
}

export interface SingleValuePick {
  value: string;
}

export interface SupportingDocsPick {
  user_text: string;
  file_urls?: string[];
}

export interface MultiSelectPick {
  picked_values: string[];
}

export type UserSelection =
  | GroupDropdownPick
  | SingleValuePick
  | SupportingDocsPick
  | MultiSelectPick;

export type DryRunOrAwaiting = DryRunResult | AwaitingInputResult;
export type DraftOrAwaiting = DraftResult | AwaitingInputResult;

export interface CaseResponse {
  id: string;
  case_name: string;
  case_number: string;
  case_number_original: string | null;
  court_district: string | null;
  chapter: number | null;
  petition_pdf_url: string | null;
  case_file_collection: string;
  gmail_collection: string;
  courtdrive_collection: string;
}

export interface CreateCaseResult {
  case: CaseResponse;
  case_file_chunks_indexed: number;
  gmail_emails_indexed: number;
  courtdrive_emails_indexed: number;
}

export interface SupportingDocUploadResponse {
  file_url: string;
  presigned_url: string;
  filename: string;
}

export interface ReferenceData {
  id: string;
  short_code: string;
  display_name: string;
  value: string;
  category: string | null;
  description: string | null;
}

export interface ReferenceDataCreate {
  name: string;
  value: string;
  description?: string | null;
}

export interface ReferenceDataUpdate {
  value?: string;
  description?: string | null;
}

// Attorney roster — backed by /core/attorneys CRUD. The roster is
// persisted server-side as a reserved reference_data row with
// short_code "ATTORNEYS"; the dedicated endpoints below give the FE a
// structured interface instead of editing the JSON value by hand.
export const ATTORNEYS_SHORT_CODE = 'ATTORNEYS' as const;

export interface Attorney {
  id: string;
  full_name: string;
}

export interface AttorneyCreate {
  full_name: string;
}

export interface AttorneyUpdate {
  full_name: string;
}
