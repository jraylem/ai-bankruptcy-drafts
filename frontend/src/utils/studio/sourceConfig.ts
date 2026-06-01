import type {
  Connector,
  ConnectorParam,
  DependentOnVariableSourceParams,
  FieldSource,
  MultiSelectFromCaseVectorSourceParams,
  MultiSelectFromGmailSourceParams,
  SourceParams,
  UserInputDateSourceParams,
} from '@/types/studio';

export type SourceCategoryKey =
  | 'bundling'
  | 'lookup'
  | 'static'
  | 'derived'
  | 'interactive';

// Bundling first when visible — child-only templates' authoring workflow
// is "mark this slot to inherit from parent first; the rest of the picker
// is rarely needed for these templates." Hidden entirely on standalone /
// parent templates (filtered by SourcePicker via bundleRole).
export const SOURCE_CATEGORY_ORDER: SourceCategoryKey[] = [
  'bundling',
  'lookup',
  'static',
  'derived',
  'interactive',
];

export const SOURCE_CATEGORY_LABELS: Record<SourceCategoryKey, string> = {
  bundling: 'Bundling — inherit from parent',
  lookup: 'Automated lookup',
  static: 'Static & system',
  derived: 'Derived from another variable',
  interactive: 'Author picks at draft time',
};

export const SOURCE_CATEGORY: Record<FieldSource, SourceCategoryKey> = {
  gmail: 'lookup',
  court_drive: 'lookup',
  case_vector: 'lookup',
  law_practice_vector: 'lookup',
  constants: 'static',
  system_generated: 'static',
  dependent_on_variable: 'derived',
  auto_derived_from_variable: 'derived',
  group_dropdown_from_gmail: 'interactive',
  group_dropdown_from_court_drive: 'interactive',
  reco_chips_from_gmail: 'interactive',
  reco_chips_from_court_drive: 'interactive',
  reco_chips_from_case_vector: 'interactive',
  dropdown_from_gmail: 'interactive',
  dropdown_from_court_drive: 'interactive',
  dropdown_from_case_vector: 'interactive',
  dropdown_from_constants: 'interactive',
  user_input_with_supporting_docs: 'interactive',
  user_input_plain_text: 'interactive',
  user_input_date: 'interactive',
  reco_chips_from_dependent_variables: 'interactive',
  multi_select_from_case_vector: 'lookup',
  multi_select_from_gmail: 'lookup',
  inherit_from_parent: 'bundling',
};

export const SOURCES_WITH_CUSTOM_UI: ReadonlySet<FieldSource> = new Set<FieldSource>([
  'gmail',
  'court_drive',
  'case_vector',
  'law_practice_vector',
  'constants',
  'dependent_on_variable',
  'system_generated',
  'multi_select_from_case_vector',
  'multi_select_from_gmail',
  'user_input_date',
  'inherit_from_parent',
]);

export type SourceFamilyKey =
  | 'gmail'
  | 'court_drive'
  | 'case_documents'
  | 'law_practice'
  | 'constants'
  | 'system'
  | 'author_form'
  | 'derived'
  | 'bundling';

export interface SourceFamilyPattern {
  key: string;
  label: string;
  description: string;
  source: FieldSource;
}

export interface SourceFamily {
  key: SourceFamilyKey;
  displayName: string;
  description: string;
  category: SourceCategoryKey;
  patterns: SourceFamilyPattern[];
}

export const SOURCE_FAMILIES: SourceFamily[] = [
  {
    key: 'gmail',
    displayName: 'Gmail',
    description: 'Search emails from Gmail.',
    category: 'lookup',
    patterns: [
      { key: 'raw', label: 'Raw lookup', description: 'No author UI · LLM extracts the value during the draft pass.', source: 'gmail' },
      { key: 'dropdown', label: 'Dropdown', description: 'Up to 20 options · author picks one at draft time.', source: 'dropdown_from_gmail' },
      { key: 'reco_chips', label: 'Reco chips', description: '3–5 LLM suggestions · author picks one or types own.', source: 'reco_chips_from_gmail' },
      { key: 'multi_select', label: 'Multi-select', description: 'Pre-fetched list of options from Gmail · author picks one or more at draft time.', source: 'multi_select_from_gmail' },
      { key: 'group', label: 'Group dropdown', description: 'One pick → two correlated values.', source: 'group_dropdown_from_gmail' },
    ],
  },
  {
    key: 'court_drive',
    displayName: 'Court Drive',
    description: 'Search court drive documents.',
    category: 'lookup',
    patterns: [
      { key: 'raw', label: 'Raw lookup', description: 'No author UI · LLM extracts the value during the draft pass.', source: 'court_drive' },
      { key: 'dropdown', label: 'Dropdown', description: 'Up to 20 options · author picks one at draft time.', source: 'dropdown_from_court_drive' },
      { key: 'reco_chips', label: 'Reco chips', description: '3–5 LLM suggestions · author picks one or types own.', source: 'reco_chips_from_court_drive' },
      { key: 'group', label: 'Group dropdown', description: 'One pick → two correlated values.', source: 'group_dropdown_from_court_drive' },
    ],
  },
  {
    key: 'case_documents',
    displayName: 'Case Vector',
    description: 'Semantic search across the case PDFs.',
    category: 'lookup',
    patterns: [
      { key: 'raw', label: 'Raw lookup', description: 'No author UI · LLM extracts the value from case PDFs.', source: 'case_vector' },
      { key: 'dropdown', label: 'Dropdown', description: 'Up to 20 options · author picks one at draft time.', source: 'dropdown_from_case_vector' },
      { key: 'reco_chips', label: 'Reco chips', description: '3–5 LLM suggestions · author picks or types own.', source: 'reco_chips_from_case_vector' },
      { key: 'multi_select', label: 'Multi-select', description: 'Pre-fetched list of options · author picks one or more at draft time.', source: 'multi_select_from_case_vector' },
    ],
  },
  {
    key: 'law_practice',
    displayName: 'Law Practice',
    description: 'Firm-wide knowledge base — boilerplate, district rules, judge preferences.',
    category: 'lookup',
    patterns: [
      { key: 'raw', label: 'Raw lookup', description: 'No author UI · LLM extracts the value from the firm KB.', source: 'law_practice_vector' },
    ],
  },
  {
    key: 'constants',
    displayName: 'Constants',
    description: 'Fetch a fixed value from reference data.',
    category: 'static',
    patterns: [
      { key: 'raw', label: 'Fixed value (by short_code)', description: 'Fetch one short_code → one value (e.g. firm address).', source: 'constants' },
      { key: 'dropdown', label: 'Dropdown of constants', description: 'Author picks from a curated list of reference data rows.', source: 'dropdown_from_constants' },
    ],
  },
  {
    key: 'system',
    displayName: 'System Generated',
    description: 'Deterministic value produced sync, IO-free.',
    category: 'static',
    patterns: [
      { key: 'raw', label: 'System generated', description: 'Resolved before any LLM call (e.g. user email, today’s date).', source: 'system_generated' },
    ],
  },
  {
    key: 'author_form',
    displayName: 'Author Form',
    description: 'Free-form input from the author at draft time.',
    category: 'interactive',
    patterns: [
      { key: 'plain_text', label: 'Plain text', description: 'Lightweight prose form · healed against the example sentence.', source: 'user_input_plain_text' },
      { key: 'date', label: 'Date picker', description: 'Author picks a date from a calendar · output formatted as text in the chosen format.', source: 'user_input_date' },
      { key: 'with_docs', label: 'With supporting docs', description: 'Form with file uploads · multimodal LLM enhances tone and corroborates from uploaded docs.', source: 'user_input_with_supporting_docs' },
      { key: 'reco_from_deps', label: 'Reco chips from variables', description: 'Suggestion chips composed from already-resolved variables.', source: 'reco_chips_from_dependent_variables' },
    ],
  },
  {
    key: 'derived',
    displayName: 'Derived',
    description: 'Computed from another variable.',
    category: 'derived',
    patterns: [
      { key: 'rule', label: 'Apply rule to variable', description: 'Transform another variable’s value (e.g. DateFiled + 14 days, format as currency).', source: 'dependent_on_variable' },
      { key: 'auto', label: 'Auto-derive from variable', description: 'Extract a sub-value from another variable. Used in tabular rows. Read-only.', source: 'auto_derived_from_variable' },
    ],
  },
  {
    key: 'bundling',
    displayName: 'Inherit from Parent',
    description: 'Mark as a slot — filled by whichever parent template attaches this child.',
    category: 'bundling',
    patterns: [
      { key: 'slot', label: 'Slot', description: 'Each parent fills the slot via its own Bundle Settings; the same child can be paired with many parents and have its slots filled differently for each pairing.', source: 'inherit_from_parent' },
    ],
  },
];

const FAMILY_OF: Map<FieldSource, SourceFamilyKey> = new Map();
const PATTERN_OF: Map<FieldSource, string> = new Map();
for (const family of SOURCE_FAMILIES) {
  for (const pattern of family.patterns) {
    FAMILY_OF.set(pattern.source, family.key);
    PATTERN_OF.set(pattern.source, pattern.key);
  }
}

export const familyOf = (source: FieldSource | null): SourceFamilyKey | null =>
  source ? FAMILY_OF.get(source) ?? null : null;

export const patternOf = (source: FieldSource | null): string | null => {
  if (!source) return null;
  return PATTERN_OF.get(source) ?? null;
};

export const findFamily = (key: SourceFamilyKey | null): SourceFamily | null => {
  if (!key) return null;
  return SOURCE_FAMILIES.find((f) => f.key === key) ?? null;
};

export const composeSource = (
  familyKey: SourceFamilyKey,
  patternKey: string,
): FieldSource | null => {
  const family = findFamily(familyKey);
  if (!family) return null;
  return family.patterns.find((p) => p.key === patternKey)?.source ?? null;
};

export const defaultPatternFor = (family: SourceFamily): SourceFamilyPattern => {
  // Prefer `raw` over any other pattern. For lookup families (gmail,
  // court_drive, case_documents, constants) raw lookup is the lowest-
  // friction author choice — no per-author dropdown to curate, no
  // reco-chip generation. Authors who want a richer pattern explicitly
  // pick it; raw is the sensible no-config default.
  const raw = family.patterns.find((p) => p.key === 'raw');
  if (raw) return raw;
  return family.patterns[0]!;
};

export const defaultParamsFor = (source: FieldSource): SourceParams | null => {
  switch (source) {
    case 'gmail':
      return {
        subject_query: '',
        body_query: '',
        scope_to_current_case: true,
        enable_web_search: false,
        web_search_instruction: '',
      };
    case 'court_drive':
      return { subject_query: '', body_query: '', scope_to_current_case: true };
    case 'case_vector':
      return { text_query: '', enable_web_search: false, web_search_instruction: '' };
    case 'law_practice_vector':
      return { text_query: '' };
    case 'constants':
      return { short_code: '' };
    case 'dependent_on_variable':
      return {
        dependent_variable: '',
        derived_value_type: 'date',
        format: '%B %-d, %Y',
        rule_effect: 'format_only',
        rule_effect_value: null,
      };
    case 'system_generated':
      return { type: 'current_date', format: '%B %-d, %Y' };
    case 'group_dropdown_from_gmail':
    case 'group_dropdown_from_court_drive':
      return {
        subject_query: '',
        body_query: '',
        group_label: '',
        left_label: '',
        right_label: '',
        right_partner_variable: '',
        scope_to_current_case: true,
      };
    case 'reco_chips_from_gmail':
    case 'reco_chips_from_court_drive':
      return {
        subject_query: '',
        body_query: '',
        label: '',
        example_sentence: '',
        scope_to_current_case: true,
      };
    case 'reco_chips_from_case_vector':
      return { text_query: '', label: '', example_sentence: '' };
    case 'dropdown_from_gmail':
    case 'dropdown_from_court_drive':
      return {
        subject_query: '',
        body_query: '',
        label: '',
        example_format: '',
        scope_to_current_case: true,
      };
    case 'dropdown_from_case_vector':
      return { text_query: '', label: '', example_format: '' };
    case 'dropdown_from_constants':
      return { reference_short_code: '', label: '' };
    case 'user_input_with_supporting_docs':
      
      return {
        label: '',
        accepted_file_types: ['pdf', 'docx', 'txt', 'md', 'png', 'jpg', 'jpeg'],
      };
    case 'user_input_plain_text':
      return { label: '', placeholder: '', example_output_sentence: '' };
    case 'user_input_date':
      return { label: '', placeholder: null, format: '%B %-d, %Y' };
    case 'auto_derived_from_variable':
      return { dependent_variable: '' };
    case 'reco_chips_from_dependent_variables':
      return {
        label: '',
        example_sentence: '',
        dependent_variables: [],
        case_vector_queries: [],
        dependent_chip_variables: [],
        instruction: '',
      };
    case 'multi_select_from_case_vector':
      return {
        label: '',
        instruction: '',
        text_query: '',
        example_formats: [],
        min_picks: 1,
        max_picks: null,
        list_joiner: ', ',
        oxford: true,
      };
    case 'multi_select_from_gmail':
      return {
        label: '',
        instruction: '',
        subject_query: '',
        body_query: '',
        scope_to_current_case: true,
        example_formats: [],
        min_picks: 1,
        max_picks: null,
        list_joiner: ', ',
        oxford: true,
      };
    case 'inherit_from_parent':
      return { fallback_value: null };
    default:
      return null;
  }
};

// Full valid keyspace per source. Mirrors the BE Pydantic source-params
// classes registered in `validate_template_spec_source_map`'s `expected_params`
// dict (bkdrafts-be/src/core/components/engines/template/validators.py).
//
// NOT derived from `defaultParamsFor` — that emits the seed/minimal shape for
// newly-created variables, which omits optional keys (e.g. `auto_derived`'s
// `rule_effect`, `singular_value`, `plural_value`). Using the minimal shape
// for shape detection would falsely flag persisted variables with optional
// keys populated as "stale" and wipe their values.
//
// Used to detect stale source_params that survived a source switch — e.g. a
// variable flipped to `inherit_from_parent` while keeping
// `{subject_query, body_query, scope_to_current_case}` from a previous
// `gmail` shape. The BE's `validate_template_spec_source_map` rejects those
// mismatches at dry-run / draft entry, so we normalize on the FE first.
const FULL_PARAM_KEYS: Record<FieldSource, ReadonlySet<string>> = {
  gmail: new Set([
    'subject_query',
    'body_query',
    'scope_to_current_case',
    'enable_web_search',
    'web_search_instruction',
  ]),
  court_drive: new Set(['subject_query', 'body_query', 'scope_to_current_case']),
  case_vector: new Set(['text_query', 'enable_web_search', 'web_search_instruction']),
  law_practice_vector: new Set(['text_query']),
  constants: new Set(['short_code']),
  dependent_on_variable: new Set([
    'dependent_variable',
    'derived_value_type',
    'format',
    'rule_effect',
    'rule_effect_value',
  ]),
  system_generated: new Set(['type', 'format']),
  group_dropdown_from_gmail: new Set([
    'subject_query',
    'body_query',
    'group_label',
    'left_label',
    'right_label',
    'right_partner_variable',
    'scope_to_current_case',
  ]),
  group_dropdown_from_court_drive: new Set([
    'subject_query',
    'body_query',
    'group_label',
    'left_label',
    'right_label',
    'right_partner_variable',
    'scope_to_current_case',
  ]),
  reco_chips_from_gmail: new Set([
    'subject_query',
    'body_query',
    'label',
    'example_sentence',
    'scope_to_current_case',
  ]),
  reco_chips_from_court_drive: new Set([
    'subject_query',
    'body_query',
    'label',
    'example_sentence',
    'scope_to_current_case',
  ]),
  reco_chips_from_case_vector: new Set(['text_query', 'label', 'example_sentence']),
  reco_chips_from_dependent_variables: new Set([
    'label',
    'example_sentence',
    'dependent_variables',
    'case_vector_queries',
    'dependent_chip_variables',
    'instruction',
  ]),
  dropdown_from_gmail: new Set([
    'subject_query',
    'body_query',
    'label',
    'example_format',
    'scope_to_current_case',
  ]),
  dropdown_from_court_drive: new Set([
    'subject_query',
    'body_query',
    'label',
    'example_format',
    'scope_to_current_case',
  ]),
  dropdown_from_case_vector: new Set(['text_query', 'label', 'example_format']),
  dropdown_from_constants: new Set(['reference_short_code', 'label']),
  user_input_with_supporting_docs: new Set(['label', 'accepted_file_types']),
  user_input_plain_text: new Set(['label', 'placeholder', 'example_output_sentence']),
  user_input_date: new Set(['label', 'placeholder', 'format']),
  // AutoDerivedSourceParams has 3 optional keys beyond the FE seed default.
  // This is the one source where `defaultParamsFor` underspecifies the keyspace.
  auto_derived_from_variable: new Set([
    'dependent_variable',
    'rule_effect',
    'singular_value',
    'plural_value',
  ]),
  multi_select_from_case_vector: new Set([
    'label',
    'instruction',
    'text_query',
    'example_formats',
    'min_picks',
    'max_picks',
    'list_joiner',
    'oxford',
  ]),
  multi_select_from_gmail: new Set([
    'label',
    'instruction',
    'subject_query',
    'body_query',
    'scope_to_current_case',
    'example_formats',
    'min_picks',
    'max_picks',
    'list_joiner',
    'oxford',
  ]),
  inherit_from_parent: new Set(['fallback_value']),
};

// Sources where `source_params: null` is a legitimate "no params" state.
const NULL_PARAMS_OK: ReadonlySet<FieldSource> = new Set<FieldSource>([
  'case_vector',
  'inherit_from_parent',
]);

export const isSourceParamsShapeValid = (
  source: FieldSource,
  params: SourceParams | null,
): boolean => {
  if (params === null || params === undefined) return NULL_PARAMS_OK.has(source);
  const expected = FULL_PARAM_KEYS[source];
  if (!expected) return true;
  for (const key of Object.keys(params)) {
    if (!expected.has(key)) return false;
  }
  return true;
};

/**
 * Returns `params` unchanged when its shape is consistent with `source`.
 * Otherwise returns the default params for `source` — discarding stale keys
 * that survived a source switch. Used both at load time (after fetching a
 * spec) and on save (defensive) so the BE never sees mismatched shapes.
 */
export const normalizeSourceParams = (
  source: FieldSource,
  params: SourceParams | null,
): SourceParams | null => {
  if (isSourceParamsShapeValid(source, params)) return params;
  return defaultParamsFor(source);
};

const evaluateCondition = (
  cond: ConnectorParam['visible_when'],
  params: Record<string, unknown>,
): boolean => {
  if (!cond) return true;
  const current = params[cond.field];
  if (cond.equals !== undefined && cond.equals !== null) {
    return current === cond.equals;
  }
  if (cond.not_in && cond.not_in.length > 0) {
    return !cond.not_in.includes(String(current ?? ''));
  }
  return true;
};

export const isParamVisible = (
  param: ConnectorParam,
  params: Record<string, unknown>,
): boolean => evaluateCondition(param.visible_when ?? null, params);

export const isParamRequired = (
  param: ConnectorParam,
  params: Record<string, unknown>,
): boolean => {
  if (param.required_when) return evaluateCondition(param.required_when, params);
  return param.required;
};

export const isSourceParamsValid = (
  source: FieldSource | null,
  params: SourceParams | null,
  connector: Connector | undefined,
): boolean => firstMissingField(source, params, connector) === null;

export const firstMissingField = (
  source: FieldSource | null,
  params: SourceParams | null,
  connector: Connector | undefined,
): string | null => {
  if (!source) return 'Source';
  if (source === 'case_vector') return null;
  // inherit_from_parent has no required fields — fallback_value is optional.
  // Phase 1B: the slot's filling configuration lives on each parent's bundling
  // tab, not on the child's source_params, so the child-side form is complete
  // by default.
  if (source === 'inherit_from_parent') return null;
  if (!params) return 'Parameters';

  switch (source) {
    case 'gmail':
    case 'court_drive': {
      const p = params as { subject_query?: string | null; body_query?: string | null };
      const hasSubject = !!p.subject_query && p.subject_query.trim().length > 0;
      const hasBody = !!p.body_query && p.body_query.trim().length > 0;
      return hasSubject || hasBody ? null : 'Subject query or Body query';
    }
    case 'law_practice_vector':
      return 'text_query' in params && !!params.text_query && params.text_query.trim().length > 0
        ? null
        : 'Text query';
    case 'constants':
      return 'short_code' in params && params.short_code.trim().length > 0
        ? null
        : 'Reference short code';
    case 'dependent_on_variable': {
      const p = params as DependentOnVariableSourceParams;
      if (!p.dependent_variable?.trim()) return 'Parent variable';
      if (!p.derived_value_type) return 'Derived value type';
      if (!p.rule_effect) return 'Rule effect';
      if (
        p.rule_effect !== 'format_only' &&
        !String(p.rule_effect_value ?? '').trim()
      ) {
        return 'Rule effect value';
      }
      return null;
    }
    case 'system_generated': {
      if (!('type' in params)) return 'Type';
      if (!params.type) return 'Type';
      return null;
    }
    case 'user_input_date': {
      const p = params as UserInputDateSourceParams;
      if (!p.label?.trim()) return 'Label';
      if (!p.format?.trim()) return 'Format';
      return null;
    }
    case 'multi_select_from_case_vector': {
      const p = params as MultiSelectFromCaseVectorSourceParams;
      if (!p.label?.trim()) return 'Label';
      if (!p.text_query?.trim()) return 'Text query';
      if (!p.example_formats || p.example_formats.length === 0) {
        return 'Example formats (need at least 1)';
      }
      for (const fmt of p.example_formats) {
        if (typeof fmt !== 'string' || !fmt.trim()) {
          return 'Example formats (entries cannot be blank)';
        }
      }
      if (
        p.max_picks !== null &&
        p.max_picks !== undefined &&
        typeof p.max_picks === 'number' &&
        typeof p.min_picks === 'number' &&
        p.max_picks < p.min_picks
      ) {
        return 'Max picks (must be >= min picks)';
      }
      return null;
    }
    case 'multi_select_from_gmail': {
      const p = params as MultiSelectFromGmailSourceParams;
      if (!p.label?.trim()) return 'Label';
      const hasSubject = !!p.subject_query?.trim();
      const hasBody = !!p.body_query?.trim();
      if (!hasSubject && !hasBody) return 'Subject query or Body query';
      if (!p.example_formats || p.example_formats.length === 0) {
        return 'Example formats (need at least 1)';
      }
      for (const fmt of p.example_formats) {
        if (typeof fmt !== 'string' || !fmt.trim()) {
          return 'Example formats (entries cannot be blank)';
        }
      }
      if (
        p.max_picks !== null &&
        p.max_picks !== undefined &&
        typeof p.max_picks === 'number' &&
        typeof p.min_picks === 'number' &&
        p.max_picks < p.min_picks
      ) {
        return 'Max picks (must be >= min picks)';
      }
      return null;
    }
  }

  if (!connector) return 'Connector schema';
  const record = params as Record<string, unknown>;
  for (const p of connector.params) {
    if (!isParamVisible(p, record)) continue;
    if (!isParamRequired(p, record)) continue;
    const v = record[p.name];
    const filled = typeof v === 'string' ? v.trim().length > 0 : v !== null && v !== undefined;
    if (!filled) return humanizeForMissing(p.name);
  }
  return null;
};

const humanizeForMissing = (name: string): string =>
  name
    .split('_')
    .map((part) => (part.length > 0 ? part[0]!.toUpperCase() + part.slice(1) : part))
    .join(' ');
