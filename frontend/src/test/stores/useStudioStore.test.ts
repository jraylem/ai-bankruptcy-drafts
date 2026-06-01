
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  AwaitingInputResult,
  DraftResult,
  DryRunResult,
  TemplateVariable,
} from '@/types/studio';

vi.mock('@/services/studio.service', () => ({
  studioApi: {
    listCases: vi.fn(),
    getCase: vi.fn(),
    createCase: vi.fn(),
    uploadSupportingDocs: vi.fn(),
    listTemplates: vi.fn(),
    renameTemplate: vi.fn(),
    deleteTemplate: vi.fn(),
    parseDocument: vi.fn(),
    generateTemplate: vi.fn(),
    regenerateTemplate: vi.fn(),
    composeAgentConfig: vi.fn(),
    dryRun: vi.fn(),
    dryRunResume: vi.fn(),
    draft: vi.fn(),
    draftResume: vi.fn(),
    listReferenceData: vi.fn(),
    getReferenceData: vi.fn(),
    createReferenceData: vi.fn(),
    updateReferenceData: vi.fn(),
    listConnectors: vi.fn(),
  },
}));

import { studioApi } from '@/services/studio.service';
import { useStudioStore } from '@/stores/useStudioStore';

const mockedApi = studioApi as unknown as Record<string, ReturnType<typeof vi.fn>>;

const baseVariable = (overrides: Partial<TemplateVariable> = {}): TemplateVariable => ({
  template_variable: 'debtor_name',
  template_index: 0,
  source: 'case_vector',
  source_params: null,
  template_property_marker: null,
  template_variable_string: null,
  template_identifying_text_match: null,
  description: null,
  instruction: null,
  ...overrides,
});

const dryRunCompleted = (overrides: Partial<DryRunResult> = {}): DryRunResult => ({
  status: 'completed',
  template_id: 't1',
  resolved_values: [],
  generated_doc_url: 'https://r2/dry_run/abc.docx',
  validation: { valid: true, errors: [], warnings: [] },
  can_generate: true,
  ...overrides,
});

const awaitingResult = (overrides: Partial<AwaitingInputResult> = {}): AwaitingInputResult => ({
  status: 'awaiting_input',
  run_id: 'run-1',
  template_id: 't1',
  case_id: 'c1',
  template_spec: null,
  resolved_values: [],
  pending_inputs: {},
  ...overrides,
});

const draftCompleted = (overrides: Partial<DraftResult> = {}): DraftResult => ({
  status: 'completed',
  template_id: 't1',
  case_id: 'c1',
  resolved_values: [],
  generated_doc_url: 'https://r2/draft/abc.docx',
  validation: { valid: true, errors: [], warnings: [] },
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
  
  localStorage.clear();
  for (const fn of Object.values(mockedApi)) fn.mockReset();
});

afterEach(() => {
  localStorage.clear();
});

describe('useStudioStore — selection', () => {
  it('selectCase sets selectedCaseId', () => {
    useStudioStore.getState().selectCase('case-42');
    expect(useStudioStore.getState().selectedCaseId).toBe('case-42');
  });

  it('selectCase(null) clears the selection', () => {
    useStudioStore.setState({ selectedCaseId: 'old' });
    useStudioStore.getState().selectCase(null);
    expect(useStudioStore.getState().selectedCaseId).toBeNull();
  });
});

describe('useStudioStore — updateVariable', () => {
  it('marks the spec dirty and transitions generated → configuring', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [baseVariable({ template_variable: 'foo' })],
      flowState: 'generated',
      isDirty: false,
    });

    useStudioStore.getState().updateVariable('foo', { description: 'updated' });

    const s = useStudioStore.getState();
    expect(s.isDirty).toBe(true);
    expect(s.flowState).toBe('configuring');
    expect(s.templateSpec[0]!.description).toBe('updated');
  });

  it('keeps the existing flowState when not in "generated"', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [baseVariable({ template_variable: 'foo' })],
      flowState: 'verified',
      isDirty: false,
    });
    useStudioStore.getState().updateVariable('foo', { description: 'x' });
    expect(useStudioStore.getState().flowState).toBe('verified');
  });
});

describe('useStudioStore — saveConfiguration', () => {
  it('rejects with an actionError when no template is selected', async () => {
    const result = await useStudioStore.getState().saveConfiguration();
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().actionError).toMatchObject({ kind: 'save' });
  });

  it('on success, sets agentConfig + flowState=persisted + isDirty=false', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [baseVariable()],
      isDirty: true,
      flowState: 'configuring',
    });

    mockedApi.composeAgentConfig.mockResolvedValue({
      data: { template_id: 't1', template_fields: [] },
    });
    
    mockedApi.listTemplates.mockResolvedValue({ data: [] });

    const result = await useStudioStore.getState().saveConfiguration();
    expect(result.success).toBe(true);

    const s = useStudioStore.getState();
    expect(s.agentConfig).toEqual({ template_id: 't1', template_fields: [] });
    expect(s.isDirty).toBe(false);
    expect(s.flowState).toBe('persisted');
  });

  it('surfaces validationErrors from the response into actionError', async () => {
    useStudioStore.setState({ selectedTemplateId: 't1', templateSpec: [baseVariable()] });

    mockedApi.composeAgentConfig.mockResolvedValue({
      error: 'Validation failed',
      validationErrors: ['Variable foo is missing source'],
    });

    const result = await useStudioStore.getState().saveConfiguration();
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().actionError).toEqual({
      kind: 'save',
      message: 'Validation failed',
      validationErrors: ['Variable foo is missing source'],
    });
  });
});

describe('useStudioStore — runDryRun', () => {
  it('rejects when template is missing', async () => {
    useStudioStore.setState({ selectedCaseId: 'c1' });
    const result = await useStudioStore.getState().runDryRun();
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().actionError?.kind).toBe('dry-run');
  });

  it('rejects when case is missing', async () => {
    useStudioStore.setState({ selectedTemplateId: 't1' });
    const result = await useStudioStore.getState().runDryRun();
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().actionError?.message).toMatch(/case selected/);
  });

  it('blocks on local preflight before hitting the BE', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      selectedCaseId: 'c1',
      templateSpec: [
        baseVariable({
          template_variable: 'firm_addr',
          source: 'constants',
          source_params: { short_code: '' },
        }),
      ],
      referenceData: [],
    });

    const result = await useStudioStore.getState().runDryRun();
    expect(result.success).toBe(false);
    expect(mockedApi.dryRun).not.toHaveBeenCalled();
    expect(useStudioStore.getState().actionError?.validationErrors?.[0]).toMatch(/firm_addr/);
  });

  it('on completed result, sets dryRunResult + flowState=verified + writes localStorage overlay', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      selectedCaseId: 'c1',
      templateSpec: [baseVariable()],
      referenceData: [],
    });
    const result = dryRunCompleted();
    mockedApi.dryRun.mockResolvedValue({ data: result });

    const action = await useStudioStore.getState().runDryRun();
    expect(action.success).toBe(true);

    const s = useStudioStore.getState();
    expect(s.dryRunResult).toEqual(result);
    expect(s.dryRunAwaiting).toBeNull();
    expect(s.flowState).toBe('verified');

    const stored = localStorage.getItem('vanhorn:studio:t1');
    expect(stored).not.toBeNull();
    const parsed = JSON.parse(stored!);
    expect(parsed.dryRunResult).toEqual(result);
    expect(parsed.flowState).toBe('verified');
  });

  it('on awaiting_input, opens the modal envelope and does NOT change flowState', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      selectedCaseId: 'c1',
      templateSpec: [baseVariable()],
      referenceData: [],
      flowState: 'configuring',
    });
    const awaiting = awaitingResult();
    mockedApi.dryRun.mockResolvedValue({ data: awaiting });

    const action = await useStudioStore.getState().runDryRun();
    expect(action.success).toBe(true);

    const s = useStudioStore.getState();
    expect(s.dryRunAwaiting).toEqual(awaiting);
    expect(s.dryRunResult).toBeNull();
    expect(s.flowState).toBe('configuring'); 
  });
});

describe('useStudioStore — runDraft', () => {
  it('refuses without a committed agent_config', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      selectedCaseId: 'c1',
      agentConfig: null,
    });
    const result = await useStudioStore.getState().runDraft();
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/save configuration first/);
    expect(mockedApi.draft).not.toHaveBeenCalled();
  });

  it('returns the completed draft envelope on happy path', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      selectedCaseId: 'c1',
      agentConfig: { template_id: 't1', template_fields: [] },
    });
    const result = draftCompleted();
    mockedApi.draft.mockResolvedValue({ data: result });

    const action = await useStudioStore.getState().runDraft();
    expect(action.success).toBe(true);
    expect(action.data).toEqual(result);
    expect(useStudioStore.getState().draftResult).toEqual(result);
  });
});

describe('useStudioStore — resumeDraft', () => {
  it('echoes back resolved_values from the awaiting envelope (BE is stateless)', async () => {
    const awaiting = awaitingResult({
      resolved_values: [
        { property_name: 'debtor_name', value: 'Alice', reasoning: 'r', confidence: 'high' },
      ],
    });
    useStudioStore.setState({ draftAwaiting: awaiting });
    mockedApi.draftResume.mockResolvedValue({ data: draftCompleted() });

    await useStudioStore.getState().resumeDraft({});

    expect(mockedApi.draftResume).toHaveBeenCalledWith(
      awaiting.template_id,
      awaiting.case_id,
      awaiting.resolved_values,
      {},
      null,
    );
    expect(useStudioStore.getState().draftAwaiting).toBeNull();
  });
});
