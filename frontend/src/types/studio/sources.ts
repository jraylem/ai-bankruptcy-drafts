
export type FieldSource =
  | 'gmail'
  | 'court_drive'
  | 'case_vector'
  | 'law_practice_vector'
  | 'constants'
  | 'dependent_on_variable'
  | 'system_generated'
  | 'group_dropdown_from_gmail'
  | 'group_dropdown_from_court_drive'
  | 'reco_chips_from_gmail'
  | 'reco_chips_from_court_drive'
  | 'reco_chips_from_case_vector'
  | 'dropdown_from_gmail'
  | 'dropdown_from_court_drive'
  | 'dropdown_from_case_vector'
  | 'dropdown_from_constants'
  | 'auto_derived_from_variable'
  | 'user_input_with_supporting_docs'
  | 'user_input_plain_text'
  | 'user_input_date'
  | 'reco_chips_from_dependent_variables'
  | 'multi_select_from_case_vector'
  | 'multi_select_from_gmail'
  | 'inherit_from_parent';

export interface GmailSourceParams {
  subject_query?: string | null;
  body_query?: string | null;
  scope_to_current_case?: boolean;
  enable_web_search?: boolean;
  /** Per-field directive for the WebSearchEnhanceAgent only. Ignored unless `enable_web_search=true`. */
  web_search_instruction?: string | null;
}

export interface CourtDriveSourceParams {
  subject_query?: string | null;
  body_query?: string | null;
  scope_to_current_case?: boolean;
}

export interface VectorSourceParams {
  text_query: string;
}

export interface CaseVectorSourceParams {
  text_query?: string | null;
  enable_web_search?: boolean;
  /** Per-field directive for the WebSearchEnhanceAgent only. Ignored unless `enable_web_search=true`. */
  web_search_instruction?: string | null;
}

export interface ConstantsSourceParams {
  short_code: string;
}

export type DerivedValueType = 'date';

export type DependentRuleEffect =
  | 'format_only'
  | 'increment_by_days'
  | 'decrement_by_days'
  | 'increment_by_months'
  | 'decrement_by_months'
  | 'increment_by_years'
  | 'decrement_by_years';

export interface DependentOnVariableSourceParams {
  dependent_variable: string;
  derived_value_type: DerivedValueType;
  format?: string | null;
  rule_effect: DependentRuleEffect;
  rule_effect_value?: string | null;
}

export type SystemGeneratedType = 'current_date';

export interface SystemGeneratedSourceParams {
  type: SystemGeneratedType;
  format?: string | null;
}

export interface GroupDropdownSourceParams {
  subject_query?: string | null;
  body_query?: string | null;
  group_label: string;
  left_label: string;
  right_label: string;
  right_partner_variable: string;
  scope_to_current_case?: boolean;
}

export interface RecoChipsEmailSourceParams {
  subject_query?: string | null;
  body_query?: string | null;
  label: string;
  example_sentence?: string | null;
  scope_to_current_case?: boolean;
}

export interface RecoChipsCaseVectorSourceParams {
  text_query: string;
  label: string;
  example_sentence: string;
}

export interface DropdownEmailSourceParams {
  subject_query?: string | null;
  body_query?: string | null;
  label: string;
  example_format: string;
  scope_to_current_case?: boolean;
}

export interface DropdownCaseVectorSourceParams {
  text_query: string;
  label: string;
  example_format: string;
}

export interface UserInputWithSupportingDocsSourceParams {
  label: string;
  accepted_file_types?: string[];
}

export interface UserInputPlainTextSourceParams {
  label: string;
  placeholder?: string | null;
  example_output_sentence: string;
}

export interface UserInputDateSourceParams {
  label: string;
  placeholder?: string | null;
  format: string;
}

export interface DropdownFromConstantsSourceParams {
  reference_short_code: string;
  label: string;
}

export type AutoDerivedRuleEffect = 'extract_substring' | 'pluralize_by_count';

export interface AutoDerivedSourceParams {
  dependent_variable: string;
  rule_effect?: AutoDerivedRuleEffect;
  /** Required when rule_effect='pluralize_by_count'; null/undefined otherwise. */
  singular_value?: string | null;
  /** Required when rule_effect='pluralize_by_count'; null/undefined otherwise. */
  plural_value?: string | null;
}

export interface MultiSelectFromCaseVectorSourceParams {
  label: string;
  instruction?: string | null;
  text_query: string;
  example_formats: string[];
  min_picks?: number;
  max_picks?: number | null;
  list_joiner?: string;
  oxford?: boolean;
}

export interface MultiSelectFromGmailSourceParams {
  label: string;
  instruction?: string | null;
  subject_query?: string | null;
  body_query?: string | null;
  scope_to_current_case?: boolean;
  example_formats: string[];
  min_picks?: number;
  max_picks?: number | null;
  list_joiner?: string;
  oxford?: boolean;
}

export interface CaseVectorQueryEntry {
  label: string;
  text_query: string;
}

export interface RecoChipsFromDependentVariablesSourceParams {
  label: string;
  example_sentence: string;
  dependent_variables: string[];
  case_vector_queries?: CaseVectorQueryEntry[];
  dependent_chip_variables?: string[];
  instruction?: string | null;
}

import type { InheritFromParentSourceParams } from './bundling';

export type SourceParams =
  | GmailSourceParams
  | CourtDriveSourceParams
  | VectorSourceParams
  | CaseVectorSourceParams
  | ConstantsSourceParams
  | DependentOnVariableSourceParams
  | SystemGeneratedSourceParams
  | GroupDropdownSourceParams
  | RecoChipsEmailSourceParams
  | RecoChipsCaseVectorSourceParams
  | RecoChipsFromDependentVariablesSourceParams
  | DropdownEmailSourceParams
  | DropdownCaseVectorSourceParams
  | UserInputWithSupportingDocsSourceParams
  | UserInputPlainTextSourceParams
  | UserInputDateSourceParams
  | DropdownFromConstantsSourceParams
  | AutoDerivedSourceParams
  | MultiSelectFromCaseVectorSourceParams
  | MultiSelectFromGmailSourceParams
  | InheritFromParentSourceParams;

export interface ConnectorParamOption {
  value: string;
  label: string;
  preview?: string | null;
}

export interface ConnectorParamCondition {
  field: string;
  equals?: string | null;
  not_in?: string[] | null;
}

export interface ConnectorParam {
  name: string;
  type: string;
  required: boolean;
  description: string;
  options?: ConnectorParamOption[] | null;
  allow_custom?: boolean | null;
  visible_when?: ConnectorParamCondition | null;
  required_when?: ConnectorParamCondition | null;
}

export interface Connector {
  source: FieldSource;
  display_name: string;
  description: string;
  params: ConnectorParam[];
}
