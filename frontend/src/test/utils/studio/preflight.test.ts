import { describe, it, expect } from 'vitest';
import { preflightTemplateSpec } from '@/utils/studio/preflight';
import type { ReferenceData, TemplateVariable } from '@/types/studio';

const baseVariable = (overrides: Partial<TemplateVariable> = {}): TemplateVariable => ({
  template_variable: 'debtor_name',
  template_index: 0,
  source: null,
  source_params: null,
  template_property_marker: null,
  template_variable_string: null,
  template_identifying_text_match: null,
  description: null,
  instruction: null,
  ...overrides,
});

const referenceData: ReferenceData[] = [
  {
    id: '1',
    short_code: 'firm_address',
    display_name: 'Firm Address',
    value: '123 Main St',
    category: null,
    description: null,
  },
];

describe('preflightTemplateSpec', () => {
  it('returns no errors for a valid spec', () => {
    const spec: TemplateVariable[] = [
      baseVariable({ template_variable: 'debtor_name', source: 'case_vector' }),
      baseVariable({
        template_variable: 'firm_addr',
        source: 'constants',
        source_params: { short_code: 'firm_address' },
      }),
    ];
    expect(preflightTemplateSpec(spec, referenceData)).toEqual([]);
  });

  it('flags missing source per BE error string', () => {
    const spec = [baseVariable({ template_variable: 'foo', source: null })];
    expect(preflightTemplateSpec(spec, referenceData)).toEqual([
      "Variable 'foo' is missing source",
    ]);
  });

  it('case_vector skips the source_params check (BE auto-derives query)', () => {
    const spec = [
      baseVariable({
        template_variable: 'debtor_name',
        source: 'case_vector',
        source_params: null,
      }),
    ];
    expect(preflightTemplateSpec(spec, referenceData)).toEqual([]);
  });

  it('flags missing source_params for non-case-vector sources', () => {
    const spec = [
      baseVariable({ template_variable: 'foo', source: 'gmail', source_params: null }),
    ];
    expect(preflightTemplateSpec(spec, referenceData)).toEqual([
      "Variable 'foo' is missing source_params",
    ]);
  });

  it('flags constants without short_code', () => {
    const spec = [
      baseVariable({
        template_variable: 'foo',
        source: 'constants',
        source_params: { short_code: '' },
      }),
    ];
    expect(preflightTemplateSpec(spec, referenceData)).toEqual([
      "Variable 'foo' with source 'constants' requires short_code in source_params",
    ]);
  });

  it('flags constants pointing at unknown short_code', () => {
    const spec = [
      baseVariable({
        template_variable: 'foo',
        source: 'constants',
        source_params: { short_code: 'unknown_code' },
      }),
    ];
    expect(preflightTemplateSpec(spec, referenceData)).toEqual([
      "Variable 'foo' references unknown constant 'unknown_code'",
    ]);
  });

  it('flags law_practice_vector with empty text_query', () => {
    const spec = [
      baseVariable({
        template_variable: 'rule',
        source: 'law_practice_vector',
        source_params: { text_query: '   ' },
      }),
    ];
    expect(preflightTemplateSpec(spec, referenceData)).toEqual([
      "Variable 'rule' with source 'law_practice_vector' requires a non-empty text_query",
    ]);
  });

  it('collects multiple errors across the spec', () => {
    const spec: TemplateVariable[] = [
      baseVariable({ template_variable: 'a', source: null }),
      baseVariable({
        template_variable: 'b',
        source: 'constants',
        source_params: { short_code: '' },
      }),
    ];
    const errors = preflightTemplateSpec(spec, referenceData);
    expect(errors).toHaveLength(2);
    expect(errors[0]).toContain("'a' is missing source");
    expect(errors[1]).toContain("'b'");
  });
});
