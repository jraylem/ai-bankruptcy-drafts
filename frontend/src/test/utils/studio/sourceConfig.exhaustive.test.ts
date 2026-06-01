import { describe, it, expect } from 'vitest';
import {
  SOURCE_CATEGORY,
  SOURCE_CATEGORY_LABELS,
  SOURCE_CATEGORY_ORDER,
  SOURCES_WITH_CUSTOM_UI,
  composeSource,
  defaultParamsFor,
  defaultPatternFor,
  findFamily,
  firstMissingField,
  isParamRequired,
  isParamVisible,
  isSourceParamsShapeValid,
  isSourceParamsValid,
  normalizeSourceParams,
  SOURCE_FAMILIES,
} from '@/utils/studio/sourceConfig';
import type { Connector, ConnectorParam, FieldSource, SourceParams } from '@/types/studio';

const ALL_SOURCES: FieldSource[] = [
  'gmail', 'court_drive', 'case_vector', 'law_practice_vector',
  'constants', 'dependent_on_variable', 'system_generated',
  'group_dropdown_from_gmail', 'group_dropdown_from_court_drive',
  'reco_chips_from_gmail', 'reco_chips_from_court_drive', 'reco_chips_from_case_vector',
  'dropdown_from_gmail', 'dropdown_from_court_drive', 'dropdown_from_case_vector', 'dropdown_from_constants',
  'auto_derived_from_variable',
  'user_input_with_supporting_docs', 'user_input_plain_text', 'user_input_date',
  'reco_chips_from_dependent_variables', 'multi_select_from_case_vector', 'multi_select_from_gmail',
  'inherit_from_parent',
];

describe('SOURCE_CATEGORY tables', () => {
  it('has a category for every FieldSource', () => {
    for (const s of ALL_SOURCES) {
      expect(SOURCE_CATEGORY[s]).toBeDefined();
      expect(SOURCE_CATEGORY_ORDER).toContain(SOURCE_CATEGORY[s]);
    }
  });

  it('has labels covering every category in SOURCE_CATEGORY_ORDER', () => {
    for (const cat of SOURCE_CATEGORY_ORDER) {
      expect(SOURCE_CATEGORY_LABELS[cat]).toBeTruthy();
    }
  });

  it('SOURCES_WITH_CUSTOM_UI is a subset of all sources', () => {
    for (const s of SOURCES_WITH_CUSTOM_UI) {
      expect(ALL_SOURCES).toContain(s as FieldSource);
    }
  });
});

describe('SOURCE_FAMILIES coverage', () => {
  it('every family pattern composes back to its source', () => {
    for (const family of SOURCE_FAMILIES) {
      for (const pattern of family.patterns) {
        expect(composeSource(family.key, pattern.key)).toBe(pattern.source);
      }
    }
  });

  it('composeSource returns null for unknown family or pattern', () => {
    expect(composeSource('case_documents', 'no_such_pattern')).toBeNull();
    expect(composeSource('not_a_family' as never, 'raw')).toBeNull();
  });

  it('findFamily returns null for null input', () => {
    expect(findFamily(null)).toBeNull();
  });
});

describe('defaultPatternFor', () => {
  it('falls back to first pattern when neither dropdown nor raw exists', () => {
    const family = {
      key: 'custom' as never,
      displayName: 'Custom',
      description: '',
      category: 'lookup' as const,
      patterns: [
        { key: 'only_one', label: 'Only', description: '', source: 'gmail' as FieldSource },
      ],
    };
    expect(defaultPatternFor(family).key).toBe('only_one');
  });

  it.each([
    ['gmail', 'gmail'],
    ['court_drive', 'court_drive'],
    ['case_documents', 'case_vector'],
    ['constants', 'constants'],
  ] as const)(
    'prefers raw over dropdown for %s family',
    (familyKey, expectedSource) => {
      const family = SOURCE_FAMILIES.find((f) => f.key === familyKey)!;
      const picked = defaultPatternFor(family);
      expect(picked.key).toBe('raw');
      expect(picked.source).toBe(expectedSource);
    },
  );
});

describe('defaultParamsFor — every FieldSource', () => {
  it.each(ALL_SOURCES)('returns a non-null shape for %s', (source) => {
    const params = defaultParamsFor(source);
    expect(params).not.toBeNull();
  });

  it('returns null for an unknown source', () => {
    expect(defaultParamsFor('unknown' as never)).toBeNull();
  });

  it('emits the BE-disambiguating sentinel keys', () => {
    expect(defaultParamsFor('reco_chips_from_gmail')).toHaveProperty('example_sentence');
    expect(defaultParamsFor('reco_chips_from_court_drive')).toHaveProperty('example_sentence');
    expect(defaultParamsFor('dropdown_from_court_drive')).toHaveProperty('example_format');
    expect(defaultParamsFor('group_dropdown_from_court_drive')).toHaveProperty('group_label');
    expect(defaultParamsFor('user_input_plain_text')).toHaveProperty('example_output_sentence');
    expect(defaultParamsFor('reco_chips_from_dependent_variables')).toHaveProperty('dependent_variables');
    expect(defaultParamsFor('multi_select_from_case_vector')).toHaveProperty('example_formats');
    expect(defaultParamsFor('auto_derived_from_variable')).toHaveProperty('dependent_variable');
    expect(defaultParamsFor('dropdown_from_constants')).toHaveProperty('reference_short_code');
  });
});

describe('isParamVisible / isParamRequired — visible_when / required_when', () => {
  const param = (overrides: Partial<ConnectorParam> = {}): ConnectorParam => ({
    name: 'foo',
    type: 'string',
    required: false,
    description: '',
    ...overrides,
  });

  it('visible by default when no condition', () => {
    expect(isParamVisible(param(), {})).toBe(true);
  });

  it('visible_when equals matches', () => {
    const p = param({ visible_when: { field: 'mode', equals: 'advanced' } });
    expect(isParamVisible(p, { mode: 'advanced' })).toBe(true);
    expect(isParamVisible(p, { mode: 'simple' })).toBe(false);
  });

  it('visible_when not_in matches everything except listed values', () => {
    const p = param({ visible_when: { field: 'mode', not_in: ['hidden', 'gone'] } });
    expect(isParamVisible(p, { mode: 'shown' })).toBe(true);
    expect(isParamVisible(p, { mode: 'hidden' })).toBe(false);
  });

  it('isParamRequired falls back to .required when no required_when', () => {
    expect(isParamRequired(param({ required: true }), {})).toBe(true);
    expect(isParamRequired(param({ required: false }), {})).toBe(false);
  });

  it('isParamRequired follows required_when override', () => {
    const p = param({
      required: false,
      required_when: { field: 'mode', equals: 'advanced' },
    });
    expect(isParamRequired(p, { mode: 'advanced' })).toBe(true);
    expect(isParamRequired(p, { mode: 'simple' })).toBe(false);
  });
});

describe('firstMissingField — every source branch', () => {
  it('user_input_date: requires label then format', () => {
    expect(firstMissingField('user_input_date', { label: '', format: 'x' } as never, undefined)).toBe('Label');
    expect(firstMissingField('user_input_date', { label: 'D', format: '' } as never, undefined)).toBe('Format');
    expect(firstMissingField('user_input_date', { label: 'D', format: '%Y' } as never, undefined)).toBeNull();
  });

  it('system_generated: requires type field', () => {
    expect(firstMissingField('system_generated', { foo: 'bar' } as never, undefined)).toBe('Type');
    expect(firstMissingField('system_generated', { type: '' } as never, undefined)).toBe('Type');
    expect(firstMissingField('system_generated', { type: 'current_date' } as never, undefined)).toBeNull();
  });

  it('dependent_on_variable: walks all 4 required gates', () => {
    const base = {
      dependent_variable: 'p',
      derived_value_type: 'date',
      rule_effect: 'increment_by_days',
      rule_effect_value: '7',
    } as const;
    expect(firstMissingField('dependent_on_variable', { ...base, dependent_variable: '' } as never, undefined)).toBe('Parent variable');
    expect(firstMissingField('dependent_on_variable', { ...base, derived_value_type: '' } as never, undefined)).toBe('Derived value type');
    expect(firstMissingField('dependent_on_variable', { ...base, rule_effect: '' } as never, undefined)).toBe('Rule effect');
    expect(firstMissingField('dependent_on_variable', { ...base, rule_effect_value: '' } as never, undefined)).toBe('Rule effect value');
    expect(firstMissingField('dependent_on_variable', base as never, undefined)).toBeNull();
  });

  it('falls through to connector schema for sources without a custom branch', () => {
    const connector: Connector = {
      source: 'reco_chips_from_gmail',
      display_name: 'X',
      description: '',
      params: [
        { name: 'label', type: 'string', required: true, description: 'Label' },
      ],
    };
    expect(firstMissingField('reco_chips_from_gmail', { label: '' } as never, connector)).toBe('Label');
    expect(firstMissingField('reco_chips_from_gmail', { label: 'ok' } as never, connector)).toBeNull();
  });

  it('returns "Connector schema" when no custom branch and no connector', () => {
    expect(firstMissingField('reco_chips_from_gmail', { label: 'x' } as never, undefined)).toBe('Connector schema');
  });

  it('isSourceParamsValid is the negation of firstMissingField', () => {
    expect(isSourceParamsValid('case_vector', null, undefined)).toBe(true);
    expect(isSourceParamsValid('gmail', null, undefined)).toBe(false);
  });
});

describe('isSourceParamsShapeValid + normalizeSourceParams', () => {
  // Full-keyspace examples per source — every optional key populated. Mirrors
  // the BE Pydantic source-params classes. If a new optional key is added to
  // any class on the BE, update this map AND the corresponding entry in
  // `FULL_PARAM_KEYS` (sourceConfig.ts) so the round-trip test stays green.
  const FULL_PARAMS_EXAMPLES: Record<FieldSource, SourceParams> = {
    gmail: { subject_query: 's', body_query: 'b', scope_to_current_case: true } as SourceParams,
    court_drive: { subject_query: 's', body_query: 'b', scope_to_current_case: true } as SourceParams,
    case_vector: { text_query: 't', enable_web_search: true, web_search_instruction: 'i' } as SourceParams,
    law_practice_vector: { text_query: 't' } as SourceParams,
    constants: { short_code: 'FIRM_NAME' } as SourceParams,
    dependent_on_variable: {
      dependent_variable: 'p',
      derived_value_type: 'date',
      format: '%Y',
      rule_effect: 'increment_by_days',
      rule_effect_value: '7',
    } as SourceParams,
    system_generated: { type: 'current_date', format: '%Y' } as SourceParams,
    group_dropdown_from_gmail: {
      subject_query: 's',
      body_query: 'b',
      group_label: 'g',
      left_label: 'l',
      right_label: 'r',
      right_partner_variable: 'rp',
      scope_to_current_case: true,
    } as SourceParams,
    group_dropdown_from_court_drive: {
      subject_query: 's',
      body_query: 'b',
      group_label: 'g',
      left_label: 'l',
      right_label: 'r',
      right_partner_variable: 'rp',
      scope_to_current_case: true,
    } as SourceParams,
    reco_chips_from_gmail: {
      subject_query: 's',
      body_query: 'b',
      label: 'L',
      example_sentence: 'es',
      scope_to_current_case: true,
    } as SourceParams,
    reco_chips_from_court_drive: {
      subject_query: 's',
      body_query: 'b',
      label: 'L',
      example_sentence: 'es',
      scope_to_current_case: true,
    } as SourceParams,
    reco_chips_from_case_vector: { text_query: 't', label: 'L', example_sentence: 'es' } as SourceParams,
    reco_chips_from_dependent_variables: {
      label: 'L',
      example_sentence: 'es',
      dependent_variables: [],
      case_vector_queries: [],
      dependent_chip_variables: [],
      instruction: 'i',
    } as SourceParams,
    dropdown_from_gmail: {
      subject_query: 's',
      body_query: 'b',
      label: 'L',
      example_format: 'ef',
      scope_to_current_case: true,
    } as SourceParams,
    dropdown_from_court_drive: {
      subject_query: 's',
      body_query: 'b',
      label: 'L',
      example_format: 'ef',
      scope_to_current_case: true,
    } as SourceParams,
    dropdown_from_case_vector: { text_query: 't', label: 'L', example_format: 'ef' } as SourceParams,
    dropdown_from_constants: { reference_short_code: 'ATTORNEYS', label: 'L' } as SourceParams,
    user_input_with_supporting_docs: { label: 'L', accepted_file_types: ['pdf'] } as SourceParams,
    user_input_plain_text: { label: 'L', placeholder: 'p', example_output_sentence: 'es' } as SourceParams,
    user_input_date: { label: 'L', placeholder: null, format: '%Y' } as SourceParams,
    // The one that just broke — `defaultParamsFor` only emits `dependent_variable`
    // but the persisted shape carries 3 more optional keys.
    auto_derived_from_variable: {
      dependent_variable: 'trustee_name',
      rule_effect: 'extract_substring',
      singular_value: null,
      plural_value: null,
    } as SourceParams,
    multi_select_from_case_vector: {
      label: 'L',
      instruction: 'i',
      text_query: 't',
      example_formats: [],
      min_picks: 1,
      max_picks: null,
      list_joiner: ', ',
      oxford: true,
    } as SourceParams,
    multi_select_from_gmail: {
      label: 'L',
      instruction: 'i',
      subject_query: 's',
      body_query: 'b',
      scope_to_current_case: true,
      example_formats: [],
      min_picks: 1,
      max_picks: null,
      list_joiner: ', ',
      oxford: true,
    } as SourceParams,
    inherit_from_parent: { fallback_value: '[no parent attached]' } as SourceParams,
  };

  it.each(ALL_SOURCES)(
    "defaultParamsFor(%s) round-trips through normalizeSourceParams unchanged",
    (source) => {
      const defaults = defaultParamsFor(source);
      if (defaults === null) return;
      expect(isSourceParamsShapeValid(source, defaults)).toBe(true);
      expect(normalizeSourceParams(source, defaults)).toBe(defaults);
    },
  );

  it.each(ALL_SOURCES)(
    "full-keyspace example for %s round-trips unchanged",
    (source) => {
      const example = FULL_PARAMS_EXAMPLES[source];
      expect(example).toBeDefined();
      expect(isSourceParamsShapeValid(source, example)).toBe(true);
      // Reference-equal: normalizer must return the input unchanged when valid.
      expect(normalizeSourceParams(source, example)).toBe(example);
    },
  );

  it('rejects a foreign-keyed shape and replaces it with defaultParamsFor', () => {
    const stale = { subject_query: null, body_query: null, scope_to_current_case: true } as SourceParams;
    expect(isSourceParamsShapeValid('inherit_from_parent', stale)).toBe(false);
    expect(normalizeSourceParams('inherit_from_parent', stale)).toEqual({ fallback_value: null });
  });

  it('auto_derived_from_variable preserves rule_effect / singular_value / plural_value (regression guard)', () => {
    const populated = {
      dependent_variable: 'trustee_name',
      rule_effect: 'extract_substring',
      singular_value: null,
      plural_value: null,
    } as SourceParams;
    expect(isSourceParamsShapeValid('auto_derived_from_variable', populated)).toBe(true);
    expect(normalizeSourceParams('auto_derived_from_variable', populated)).toBe(populated);
  });

  it.each(ALL_SOURCES)('null params are valid only for case_vector and inherit_from_parent — %s', (source) => {
    const expected = source === 'case_vector' || source === 'inherit_from_parent';
    expect(isSourceParamsShapeValid(source, null)).toBe(expected);
  });
});
