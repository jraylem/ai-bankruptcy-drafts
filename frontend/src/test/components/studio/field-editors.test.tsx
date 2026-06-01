import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { useStudioStore } from '@/stores/useStudioStore';
import { AutoDeriveExampleFormatEditor } from '@/components/studio/field-editors/AutoDeriveExampleFormatEditor';
import { CaseVectorQueriesEditor } from '@/components/studio/field-editors/CaseVectorQueriesEditor';
import { DateFormatField } from '@/components/studio/field-editors/DateFormatField';
import { DependentChipVariablesPicker } from '@/components/studio/field-editors/DependentChipVariablesPicker';
import { DependentVariablesPicker } from '@/components/studio/field-editors/DependentVariablesPicker';
import { MultiSelectEditor } from '@/components/studio/field-editors/MultiSelectEditor';
import { MultiSelectGmailEditor } from '@/components/studio/field-editors/MultiSelectGmailEditor';
import { VariableReferenceInput } from '@/components/studio/field-editors/VariableReferenceInput';
import {
  isEligibleForReference,
  rootParentIsUnbound,
  rootParentSource,
} from '@/components/studio/field-editors/_referenceability';
import type {
  MultiSelectFromCaseVectorSourceParams,
  MultiSelectFromGmailSourceParams,
  TemplateVariable,
} from '@/types/studio';

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

const baseVariable = (overrides: Partial<TemplateVariable> = {}): TemplateVariable => ({
  template_variable: 'foo',
  template_index: 0,
  source: 'case_vector',
  source_params: null,
  template_property_marker: '[[foo]]',
  template_variable_string: '{{foo}}',
  template_identifying_text_match: null,
  description: null,
  instruction: null,
  ...overrides,
});

const baseStoreState = {
  selectedCaseId: null,
  selectedTemplateId: null,
  cases: [],
  templates: [],
  connectors: [],
  referenceData: [],
  templateSpec: [],
  agentConfig: null,
  dryRunResult: null,
  dryRunAwaiting: null,
  draftResult: null,
  draftAwaiting: null,
  flowState: 'new' as const,
  isDirty: false,
  actionError: null,
  error: null,
  templateDocUrl: null,
  originalDocUrl: null,
};

beforeEach(() => useStudioStore.setState(baseStoreState));
afterEach(() => useStudioStore.setState(baseStoreState));

describe('<DateFormatField />', () => {
  it('renders the date-picker hint and label input', () => {
    render(<DateFormatField params={null} onChange={() => {}} />);
    expect(screen.getByText(/Date picker/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Label/)).toBeInTheDocument();
  });

  it('emits with the typed label', () => {
    const onChange = vi.fn();
    render(<DateFormatField params={null} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/Label/), { target: { value: 'Date filed' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ label: 'Date filed' }),
    );
  });

  it('shows existing label + placeholder values', () => {
    render(
      <DateFormatField
        params={{ label: 'Filed on', placeholder: 'mm/dd/yyyy', format: '%Y-%m-%d' }}
        onChange={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('Filed on')).toBeInTheDocument();
  });
});

describe('<MultiSelectEditor />', () => {
  const value = (overrides: Partial<MultiSelectFromCaseVectorSourceParams> = {}): MultiSelectFromCaseVectorSourceParams => ({
    label: '',
    instruction: '',
    text_query: '',
    example_formats: [],
    min_picks: 1,
    max_picks: null,
    list_joiner: ', ',
    oxford: true,
    ...overrides,
  });

  it('renders empty-formats hint when example_formats is empty', () => {
    render(<MultiSelectEditor value={value()} onChange={() => {}} />);
    expect(screen.getByText(/No example formats/)).toBeInTheDocument();
  });

  it('clicking + Add format appends an empty entry', () => {
    const onChange = vi.fn();
    render(<MultiSelectEditor value={value()} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Add format/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ example_formats: [''] }),
    );
  });

  it('renders an input per existing example_format', () => {
    render(
      <MultiSelectEditor
        value={value({ example_formats: ['A', 'B', 'C'] })}
        onChange={() => {}}
      />,
    );
    expect(screen.getByDisplayValue('A')).toBeInTheDocument();
    expect(screen.getByDisplayValue('B')).toBeInTheDocument();
    expect(screen.getByDisplayValue('C')).toBeInTheDocument();
  });

  it('Remove button drops the matching entry', () => {
    const onChange = vi.fn();
    render(
      <MultiSelectEditor
        value={value({ example_formats: ['Keep', 'Drop'] })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Remove format 2/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ example_formats: ['Keep'] }),
    );
  });

  it('Move up swaps adjacent entries', () => {
    const onChange = vi.fn();
    render(
      <MultiSelectEditor
        value={value({ example_formats: ['A', 'B'] })}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Move format 2 up/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ example_formats: ['B', 'A'] }),
    );
  });

  it('typing a number into max_picks emits the parsed integer', () => {
    const onChange = vi.fn();
    render(<MultiSelectEditor value={value()} onChange={onChange} />);
    const maxPicks = screen.getAllByRole('spinbutton')[1]!;
    fireEvent.change(maxPicks, { target: { value: '5' } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ max_picks: 5 }));
  });

  it('clearing max_picks emits null (unbounded)', () => {
    const onChange = vi.fn();
    render(<MultiSelectEditor value={value({ max_picks: 5 })} onChange={onChange} />);
    const maxPicks = screen.getAllByRole('spinbutton')[1]!;
    fireEvent.change(maxPicks, { target: { value: '' } });
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ max_picks: null }));
  });
});

describe('<VariableReferenceInput />', () => {
  it('renders an input with the current value', () => {
    render(
      <VariableReferenceInput
        value="hello"
        onChange={() => {}}
        ariaLabel="Test"
      />,
    );
    expect(screen.getByLabelText('Test')).toHaveValue('hello');
  });

  it('typing fires onChange with the new value', () => {
    const onChange = vi.fn();
    render(
      <VariableReferenceInput value="" onChange={onChange} ariaLabel="Test" />,
    );
    fireEvent.change(screen.getByLabelText('Test'), { target: { value: 'x' } });
    expect(onChange).toHaveBeenCalledWith('x');
  });

  it('renders the placeholder', () => {
    render(
      <VariableReferenceInput
        value=""
        onChange={() => {}}
        placeholder="type {{ to reference"
        ariaLabel="Test"
      />,
    );
    expect(screen.getByPlaceholderText(/type/)).toBeInTheDocument();
  });
});

describe('<DependentVariablesPicker />', () => {
  const others = [
    baseVariable({ template_variable: 'date_filed', template_index: 1, source: 'case_vector' }),
    baseVariable({ template_variable: 'creditor_name', template_index: 2, source: 'gmail', source_params: { subject_query: 'foo' } as never }),
  ];

  it('renders without crashing for an empty value array', () => {
    useStudioStore.setState({ templateSpec: others });
    const { container } = render(
      <DependentVariablesPicker value={[]} onChange={() => {}} />,
    );
    expect(container.firstChild).not.toBeNull();
  });

  it('shows already-selected variables as chips', () => {
    useStudioStore.setState({ templateSpec: others });
    render(<DependentVariablesPicker value={['date_filed']} onChange={() => {}} />);
    expect(screen.getByText('date_filed')).toBeInTheDocument();
  });
});

describe('<DependentChipVariablesPicker />', () => {
  it('renders the empty-state hint when value array is empty', () => {
    useStudioStore.setState({ templateSpec: [] });
    render(
      <DependentChipVariablesPicker
        selfVariableName="self"
        value={[]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/No sibling chip dependencies/i)).toBeInTheDocument();
  });
});

describe('<CaseVectorQueriesEditor />', () => {
  it('renders the empty-state when no queries exist', () => {
    render(<CaseVectorQueriesEditor value={[]} onChange={() => {}} />);
    expect(screen.getByRole('button', { name: /Add/i })).toBeInTheDocument();
  });

  it('clicking Add appends a blank entry', () => {
    const onChange = vi.fn();
    render(<CaseVectorQueriesEditor value={[]} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Add/i }));
    expect(onChange).toHaveBeenCalledWith([{ label: '', text_query: '' }]);
  });
});

describe('<AutoDeriveExampleFormatEditor />', () => {
  const child = (name: string, marker: string): TemplateVariable =>
    baseVariable({
      template_variable: name,
      template_property_marker: marker,
      template_variable_string: `{{${name}}}`,
    });

  it('renders one pill per child', () => {
    render(
      <AutoDeriveExampleFormatEditor
        children={[child('a', '[[a]]'), child('b', '[[b]]')]}
        value=""
        onChange={() => {}}
      />,
    );
    expect(screen.getByTestId('format-pill-a')).toBeInTheDocument();
    expect(screen.getByTestId('format-pill-b')).toBeInTheDocument();
  });

  it('shows the missing-marker warning when a child has no sample', () => {
    render(
      <AutoDeriveExampleFormatEditor
        children={[child('a', '')]}
        value=""
        onChange={() => {}}
      />,
    );
    expect(screen.getByText(/no sample value/)).toBeInTheDocument();
  });

  it('emits composed format on first render when value differs', async () => {
    const onChange = vi.fn();
    render(
      <AutoDeriveExampleFormatEditor
        children={[child('a', '[[a]]'), child('b', '[[b]]')]}
        value=""
        onChange={onChange}
      />,
    );
    expect(onChange).toHaveBeenCalledWith('[[a]] - [[b]]');
  });
});

describe('<MultiSelectGmailEditor />', () => {
  const value = (overrides: Partial<MultiSelectFromGmailSourceParams> = {}): MultiSelectFromGmailSourceParams => ({
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
    ...overrides,
  });

  it('renders the at-least-one-query warning when both queries are blank', () => {
    render(<MultiSelectGmailEditor value={value()} onChange={() => {}} />);
    expect(screen.getByText(/At least one query is required/i)).toBeInTheDocument();
  });

  it('hides the warning once a subject query is provided', () => {
    render(
      <MultiSelectGmailEditor
        value={value({ subject_query: 'Proof of Claim' })}
        onChange={() => {}}
      />,
    );
    expect(screen.queryByText(/At least one query is required/i)).toBeNull();
  });

  it('toggling scope_to_current_case fires onChange', () => {
    const onChange = vi.fn();
    render(
      <MultiSelectGmailEditor value={value()} onChange={onChange} />,
    );
    const checkbox = screen.getByLabelText(/Scope to current case/i);
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ scope_to_current_case: false }),
    );
  });

  it('renders MultiSelectSharedFields (label/example_formats/picks/joiner block)', () => {
    render(<MultiSelectGmailEditor value={value()} onChange={() => {}} />);
    expect(screen.getByText(/searches Gmail/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Label/).length).toBeGreaterThan(0);
  });
});

describe('isEligibleForReference (transitive auto_derived eligibility)', () => {
  const make = (overrides: Partial<TemplateVariable>): TemplateVariable =>
    baseVariable(overrides);

  const mapOf = (...vars: TemplateVariable[]): Map<string, TemplateVariable> =>
    new Map(vars.map((v) => [v.template_variable, v]));

  it('eligible: direct case_vector source', () => {
    const v = make({ template_variable: 'case_no', source: 'case_vector' });
    expect(isEligibleForReference(v, mapOf(v))).toBe(true);
  });

  it('eligible: auto_derived with case_vector root parent', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: 'case_vector',
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'vehicle_name',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child))).toBe(true);
  });

  it('ineligible: auto_derived with dropdown_from_gmail (USER_INPUT) root', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: 'dropdown_from_gmail',
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'vehicle_name',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child))).toBe(false);
  });

  it('eligible: chain depth 2 ending at case_vector root', () => {
    const root = make({
      template_variable: 'vehicle_record',
      source: 'case_vector',
      template_variable_string: null,
    });
    const mid = make({
      template_variable: 'vehicle_name',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    const leaf = make({
      template_variable: 'vehicle_name_truncated',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_name' } as never,
    });
    expect(isEligibleForReference(leaf, mapOf(root, mid, leaf))).toBe(true);
  });

  it('ineligible: cycle in auto_derived chain returns false without infinite loop', () => {
    const a = make({
      template_variable: 'a',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'b' } as never,
    });
    const b = make({
      template_variable: 'b',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'a' } as never,
    });
    expect(isEligibleForReference(a, mapOf(a, b))).toBe(false);
    expect(rootParentSource(a, mapOf(a, b))).toBeNull();
  });

  it('ineligible: auto_derived chain with missing parent in map', () => {
    const orphan = make({
      template_variable: 'orphan',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'ghost' } as never,
    });
    expect(isEligibleForReference(orphan, mapOf(orphan))).toBe(false);
  });

  it('ineligible: variable with no source bound', () => {
    const unbound = make({ template_variable: 'unbound', source: null });
    expect(isEligibleForReference(unbound, mapOf(unbound))).toBe(false);
  });

  // ─── Path B — contextual referencer-stage eligibility ──────────────

  it('Path B — LLM_DRAFT referencer eligible for auto_derived of dropdown_from_case_vector', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: 'dropdown_from_case_vector',
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'car_model',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child), 'case_vector')).toBe(true);
    expect(isEligibleForReference(child, mapOf(parent, child), 'gmail')).toBe(true);
    expect(isEligibleForReference(child, mapOf(parent, child), 'court_drive')).toBe(true);
  });

  it('Path B — USER_INPUT referencer NOT eligible for auto_derived of dropdown_from_case_vector (circular)', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: 'dropdown_from_case_vector',
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'car_model',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child), 'dropdown_from_case_vector')).toBe(false);
    expect(isEligibleForReference(child, mapOf(parent, child), 'reco_chips_from_dependent_variables')).toBe(false);
    expect(isEligibleForReference(child, mapOf(parent, child), 'multi_select_from_gmail')).toBe(false);
  });

  it('Path B — referencerSource=null preserves strict default (Path A behavior)', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: 'dropdown_from_case_vector',
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'car_model',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child), null)).toBe(false);
    expect(isEligibleForReference(child, mapOf(parent, child))).toBe(false);
  });

  it('Path B — LLM_DRAFT referencer can target a USER_INPUT variable directly (not just via auto_derived)', () => {
    const userPick = make({
      template_variable: 'user_pick',
      source: 'dropdown_from_gmail',
    });
    expect(isEligibleForReference(userPick, mapOf(userPick), 'case_vector')).toBe(true);
    expect(isEligibleForReference(userPick, mapOf(userPick), 'dropdown_from_gmail')).toBe(false);
  });

  // ─── Placeholder rule — unbound-root auto_derived from LLM_DRAFT referencers ──

  it('placeholder — LLM_DRAFT referencer eligible for auto_derived of unbound virtual parent', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: null,
      source_params: null,
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'car_model',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child), 'case_vector')).toBe(true);
    expect(isEligibleForReference(child, mapOf(parent, child), 'gmail')).toBe(true);
    expect(isEligibleForReference(child, mapOf(parent, child), 'court_drive')).toBe(true);
    expect(isEligibleForReference(child, mapOf(parent, child), 'law_practice_vector')).toBe(true);
    expect(isEligibleForReference(child, mapOf(parent, child), 'constants')).toBe(true);
    expect(isEligibleForReference(child, mapOf(parent, child), 'system_generated')).toBe(true);
  });

  it('placeholder — USER_INPUT referencer NOT eligible for auto_derived of unbound parent', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: null,
      source_params: null,
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'car_model',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child), 'dropdown_from_case_vector')).toBe(false);
    expect(isEligibleForReference(child, mapOf(parent, child), 'reco_chips_from_dependent_variables')).toBe(false);
    expect(isEligibleForReference(child, mapOf(parent, child), 'multi_select_from_gmail')).toBe(false);
  });

  it('placeholder — referencerSource=null preserves strict default for unbound-root auto_derived', () => {
    const parent = make({
      template_variable: 'vehicle_record',
      source: null,
      source_params: null,
      template_variable_string: null,
    });
    const child = make({
      template_variable: 'car_model',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    expect(isEligibleForReference(child, mapOf(parent, child), null)).toBe(false);
    expect(isEligibleForReference(child, mapOf(parent, child))).toBe(false);
  });

  it('placeholder — cycle is still rejected (broken chain ≠ unbound)', () => {
    const a = make({
      template_variable: 'a',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'b' } as never,
    });
    const b = make({
      template_variable: 'b',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'a' } as never,
    });
    expect(isEligibleForReference(a, mapOf(a, b), 'case_vector')).toBe(false);
    expect(rootParentIsUnbound(a, mapOf(a, b))).toBe(false);
  });

  it('placeholder — missing parent is still rejected (broken chain ≠ unbound)', () => {
    const orphan = make({
      template_variable: 'orphan',
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'ghost' } as never,
    });
    expect(isEligibleForReference(orphan, mapOf(orphan), 'case_vector')).toBe(false);
    expect(rootParentIsUnbound(orphan, mapOf(orphan))).toBe(false);
  });

  it('placeholder — direct unbound non-auto_derived target still rejected from LLM_DRAFT referencer', () => {
    const unbound = make({
      template_variable: 'vehicle_record',
      source: null,
      template_variable_string: null,
    });
    // rootParentIsUnbound returns true (trivial case), but isEligibleForReference
    // restricts placeholder acceptance to auto_derived targets only — the author
    // must add an auto_derived child as the actual referenced variable.
    expect(rootParentIsUnbound(unbound, mapOf(unbound))).toBe(true);
    expect(isEligibleForReference(unbound, mapOf(unbound), 'case_vector')).toBe(false);
  });
});

describe('<DependentVariablesPicker /> with auto_derived eligibility', () => {
  it('shows an auto_derived child of a case_vector parent as eligible', () => {
    const parent = baseVariable({
      template_variable: 'vehicle_record',
      template_index: 1,
      source: 'case_vector',
      template_variable_string: null,
    });
    const child = baseVariable({
      template_variable: 'vehicle_name',
      template_index: 2,
      source: 'auto_derived_from_variable',
      source_params: { dependent_variable: 'vehicle_record' } as never,
    });
    useStudioStore.setState({ templateSpec: [parent, child] });
    render(<DependentVariablesPicker value={['vehicle_name']} onChange={() => {}} />);
    // The chip renders with the variable name; the tone is not the warning tone.
    expect(screen.getByText('vehicle_name')).toBeInTheDocument();
  });
});
