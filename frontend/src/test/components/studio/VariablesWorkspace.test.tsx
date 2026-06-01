
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { VariablesWorkspace } from '@/components/studio/workspace/VariablesWorkspace';
import { useStudioStore } from '@/stores/useStudioStore';
import type { TemplateVariable } from '@/types/studio';

vi.mock('@/services/studio.service', () => ({
  studioApi: new Proxy({}, { get: () => vi.fn().mockResolvedValue({ data: null }) }),
}));

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

beforeEach(() => {
  useStudioStore.setState({
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
    flowState: 'new',
    isDirty: false,
    actionError: null,
    error: null,
    templateDocUrl: null,
    originalDocUrl: null,
  });
});

describe('<VariablesWorkspace />', () => {
  it('shows the empty-state hint when template_spec is empty', () => {
    render(<VariablesWorkspace />);
    expect(
      screen.getByText('Upload a legal document to see its variables.'),
    ).toBeInTheDocument();
  });

  it('renders the mapped-count header when the spec has variables', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [
        
        baseVariable({ template_variable: 'debtor_name', source: 'case_vector' }),
        
        baseVariable({ template_variable: 'firm_addr', template_index: 1, source: null }),
      ],
    });
    render(<VariablesWorkspace />);
    expect(screen.getByText('Template Variables')).toBeInTheDocument();
    expect(screen.getByText('1 of 2 variables mapped')).toBeInTheDocument();
  });

  it('counts a constants variable with source_params as mapped', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [
        baseVariable({
          template_variable: 'firm_addr',
          source: 'constants',
          source_params: { short_code: 'firm_address' },
        }),
      ],
    });
    render(<VariablesWorkspace />);
    expect(screen.getByText('1 of 1 variables mapped')).toBeInTheDocument();
  });

  it('does NOT count a non-case-vector variable that has no source_params', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [
        baseVariable({
          template_variable: 'creditor',
          source: 'gmail',
          source_params: null,
        }),
      ],
    });
    render(<VariablesWorkspace />);
    expect(screen.getByText('0 of 1 variables mapped')).toBeInTheDocument();
  });
});
