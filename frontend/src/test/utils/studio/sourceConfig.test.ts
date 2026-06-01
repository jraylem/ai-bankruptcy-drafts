import { describe, it, expect } from 'vitest';
import {
  composeSource,
  defaultParamsFor,
  defaultPatternFor,
  familyOf,
  findFamily,
  firstMissingField,
  isSourceParamsValid,
  patternOf,
  SOURCE_FAMILIES,
} from '@/utils/studio/sourceConfig';
import type {
  Connector,
  DependentOnVariableSourceParams,
  GmailSourceParams,
  MultiSelectFromCaseVectorSourceParams,
} from '@/types/studio';

describe('familyOf / patternOf', () => {
  it('round-trips a concrete source through (family, pattern)', () => {
    expect(familyOf('dropdown_from_gmail')).toBe('gmail');
    expect(patternOf('dropdown_from_gmail')).toBe('dropdown');
    expect(composeSource('gmail', 'dropdown')).toBe('dropdown_from_gmail');
  });

  it('returns null for null input on familyOf/patternOf', () => {
    expect(familyOf(null)).toBeNull();
    expect(patternOf(null)).toBeNull();
  });

  it('familyOf is null for an unmapped source', () => {
    // @ts-expect-error: deliberately invalid
    expect(familyOf('not_a_real_source')).toBeNull();
  });
});

describe('SOURCE_FAMILIES coverage', () => {
  it('every (family, pattern.source) is unique — no two patterns share a FieldSource', () => {
    const seen = new Set<string>();
    for (const family of SOURCE_FAMILIES) {
      for (const pattern of family.patterns) {
        expect(seen.has(pattern.source), `duplicate source: ${pattern.source}`).toBe(false);
        seen.add(pattern.source);
      }
    }
  });

  it('case_documents family includes the multi_select pattern (added 2026-05)', () => {
    const family = findFamily('case_documents');
    expect(family).not.toBeNull();
    const keys = family!.patterns.map((p) => p.key);
    expect(keys).toContain('multi_select');
  });
});

describe('defaultPatternFor', () => {
  it('prefers raw over dropdown when both exist', () => {
    // Updated 2026 — raw is now the lowest-friction default for lookup
    // families. Previously this preferred dropdown; that was a bug
    // (authors who wanted plain raw lookup had to manually re-pick it
    // every time, and the default obscured the simpler option).
    const family = findFamily('gmail')!;
    expect(defaultPatternFor(family).key).toBe('raw');
  });

  it('falls back to raw when no dropdown exists', () => {
    const family = findFamily('law_practice')!;
    expect(defaultPatternFor(family).key).toBe('raw');
  });
});

describe('defaultParamsFor', () => {
  it('returns a complete shape for every FieldSource (pydantic disambiguation)', () => {
    
    const recoCv = defaultParamsFor('reco_chips_from_case_vector') as { example_sentence: string };
    expect(recoCv).toHaveProperty('example_sentence');

    const dropdownGmail = defaultParamsFor('dropdown_from_gmail') as { example_format: string };
    expect(dropdownGmail).toHaveProperty('example_format');

    const groupGmail = defaultParamsFor('group_dropdown_from_gmail') as {
      group_label: string;
      left_label: string;
      right_label: string;
    };
    expect(groupGmail.group_label).toBe('');
    expect(groupGmail.left_label).toBe('');
    expect(groupGmail.right_label).toBe('');
  });

  it('seeds user_input_with_supporting_docs with the BE default extension list', () => {
    const params = defaultParamsFor('user_input_with_supporting_docs') as {
      accepted_file_types: string[];
    };
    expect(params.accepted_file_types).toEqual([
      'pdf', 'docx', 'txt', 'md', 'png', 'jpg', 'jpeg',
    ]);
  });

  it('case_vector defaults include web_search_instruction (string, blank)', () => {
    const params = defaultParamsFor('case_vector') as {
      text_query: string;
      enable_web_search: boolean;
      web_search_instruction: string;
    };
    expect(params.text_query).toBe('');
    expect(params.enable_web_search).toBe(false);
    expect(params.web_search_instruction).toBe('');
  });

  it('gmail defaults include the web-search enhancement fields (off by default)', () => {
    const params = defaultParamsFor('gmail') as {
      subject_query: string;
      body_query: string;
      scope_to_current_case: boolean;
      enable_web_search: boolean;
      web_search_instruction: string;
    };
    expect(params.subject_query).toBe('');
    expect(params.body_query).toBe('');
    expect(params.scope_to_current_case).toBe(true);
    expect(params.enable_web_search).toBe(false);
    expect(params.web_search_instruction).toBe('');
  });

  it('court_drive defaults stay narrow — no web-search fields', () => {
    const params = defaultParamsFor('court_drive') as Record<string, unknown>;
    expect(params).not.toHaveProperty('enable_web_search');
    expect(params).not.toHaveProperty('web_search_instruction');
  });
});

describe('firstMissingField', () => {
  const noConnector: Connector | undefined = undefined;

  it('asks for Source when source is null', () => {
    expect(firstMissingField(null, null, noConnector)).toBe('Source');
  });

  it('returns null for case_vector regardless of params (BE auto-derives query)', () => {
    expect(firstMissingField('case_vector', null, noConnector)).toBeNull();
  });

  it('asks for Parameters when params are null for non-case-vector', () => {
    expect(firstMissingField('gmail', null, noConnector)).toBe('Parameters');
  });

  it('gmail: requires either subject or body query', () => {
    const empty: GmailSourceParams = { subject_query: '', body_query: '' };
    expect(firstMissingField('gmail', empty, noConnector)).toBe('Subject query or Body query');

    const subjectOnly: GmailSourceParams = { subject_query: 'invoice', body_query: '' };
    expect(firstMissingField('gmail', subjectOnly, noConnector)).toBeNull();

    const bodyOnly: GmailSourceParams = { subject_query: '', body_query: 'attached' };
    expect(firstMissingField('gmail', bodyOnly, noConnector)).toBeNull();
  });

  it('dependent_on_variable: walks the required chain in order', () => {
    const blank: DependentOnVariableSourceParams = {
      dependent_variable: '',
      derived_value_type: 'date',
      rule_effect: 'format_only',
    };
    expect(firstMissingField('dependent_on_variable', blank, noConnector)).toBe('Parent variable');

    const offsetMissingValue: DependentOnVariableSourceParams = {
      dependent_variable: 'date_filed',
      derived_value_type: 'date',
      rule_effect: 'increment_by_days',
      rule_effect_value: '',
    };
    expect(firstMissingField('dependent_on_variable', offsetMissingValue, noConnector)).toBe(
      'Rule effect value',
    );

    const formatOnlyOk: DependentOnVariableSourceParams = {
      dependent_variable: 'date_filed',
      derived_value_type: 'date',
      rule_effect: 'format_only',
    };
    expect(firstMissingField('dependent_on_variable', formatOnlyOk, noConnector)).toBeNull();
  });

  it('multi_select_from_case_vector: enforces example_formats and pick bounds', () => {
    const noFormats: MultiSelectFromCaseVectorSourceParams = {
      label: 'Creditors',
      text_query: 'creditors',
      example_formats: [],
    };
    expect(firstMissingField('multi_select_from_case_vector', noFormats, noConnector)).toBe(
      'Example formats (need at least 1)',
    );

    const blankFormat: MultiSelectFromCaseVectorSourceParams = {
      label: 'Creditors',
      text_query: 'creditors',
      example_formats: ['', 'second'],
    };
    expect(firstMissingField('multi_select_from_case_vector', blankFormat, noConnector)).toBe(
      'Example formats (entries cannot be blank)',
    );

    const inverted: MultiSelectFromCaseVectorSourceParams = {
      label: 'Creditors',
      text_query: 'creditors',
      example_formats: ['Acme Bank'],
      min_picks: 3,
      max_picks: 1,
    };
    expect(firstMissingField('multi_select_from_case_vector', inverted, noConnector)).toBe(
      'Max picks (must be >= min picks)',
    );

    const ok: MultiSelectFromCaseVectorSourceParams = {
      label: 'Creditors',
      text_query: 'creditors',
      example_formats: ['Acme Bank'],
      min_picks: 1,
      max_picks: 5,
    };
    expect(firstMissingField('multi_select_from_case_vector', ok, noConnector)).toBeNull();
  });
});

describe('isSourceParamsValid', () => {
  it('mirrors firstMissingField === null', () => {
    const ok: GmailSourceParams = { subject_query: 'invoice', body_query: '' };
    expect(isSourceParamsValid('gmail', ok, undefined)).toBe(true);

    const bad: GmailSourceParams = { subject_query: '', body_query: '' };
    expect(isSourceParamsValid('gmail', bad, undefined)).toBe(false);
  });
});
