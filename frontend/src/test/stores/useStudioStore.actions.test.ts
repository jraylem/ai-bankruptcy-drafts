import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  AwaitingInputResult,
  CaseResponse,
  Connector,
  CreateCaseResult,
  DraftTemplateListItem,
  DryRunResult,
  GenerateTemplateResult,
  ReferenceData,
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

const sampleCase: CaseResponse = {
  id: 'c1',
  case_name: 'Doe, John',
  case_number: '26-10700',
  case_number_original: '26-10700',
  court_district: 'EDPA',
  chapter: 13,
  petition_pdf_url: 'https://r2/cases/c1/petition.pdf',
  case_file_collection: 'case_file_c1',
  gmail_collection: 'gmail_emails_c1',
  courtdrive_collection: 'courtdrive_emails_c1',
};

const sampleTemplate: DraftTemplateListItem = {
  id: 't1',
  name: 'Motion',
  original_doc_url: null,
  template_doc_url: null,
  template_spec: [baseVariable()],
  agent_config: null,
  bundle_role: 'standalone',
  bundle_companions: null,
  created_at: new Date('2026-05-06').toISOString(),
  is_active: true,
};

const generated: GenerateTemplateResult = {
  template_id: 't2',
  template_name: 'Generated',
  template_spec: [baseVariable({ template_variable: 'foo' })],
  generated: true,
  original_doc_url: 'https://r2/template/t2/original.docx',
  template_doc_url: 'https://r2/template/t2/template.docx',
};

const createCaseResult: CreateCaseResult = {
  case: sampleCase,
  case_file_chunks_indexed: 12,
  gmail_emails_indexed: 4,
  courtdrive_emails_indexed: 2,
};

const referenceEntry: ReferenceData = {
  id: 'rd1',
  short_code: 'firm_address',
  display_name: 'Firm Address',
  value: '123 Main St',
  category: null,
  description: null,
};

const dryRunCompleted: DryRunResult = {
  status: 'completed',
  template_id: 't1',
  resolved_values: [],
  generated_doc_url: 'https://r2/dry_run/abc.docx',
  validation: { valid: true, errors: [], warnings: [] },
  can_generate: true,
};

const awaitingResult: AwaitingInputResult = {
  status: 'awaiting_input',
  run_id: 'run-x',
  template_id: 't1',
  case_id: 'c1',
  template_spec: null,
  resolved_values: [],
  pending_inputs: {},
};

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

afterEach(() => localStorage.clear());

describe('selectTemplate', () => {
  it('hydrates from already-loaded templates list', async () => {
    useStudioStore.setState({ templates: [sampleTemplate] });
    await useStudioStore.getState().selectTemplate('t1');
    expect(useStudioStore.getState().selectedTemplateId).toBe('t1');
    expect(mockedApi.listTemplates).not.toHaveBeenCalled();
  });

  it('fetches templates list when missing locally', async () => {
    mockedApi.listTemplates.mockResolvedValue({ data: [sampleTemplate] });
    await useStudioStore.getState().selectTemplate('t1');
    expect(mockedApi.listTemplates).toHaveBeenCalled();
    expect(useStudioStore.getState().selectedTemplateId).toBe('t1');
  });

  it('clears selection when template is unknown both locally and on BE', async () => {
    mockedApi.listTemplates.mockResolvedValue({ data: [] });
    useStudioStore.setState({ selectedTemplateId: 'old' });
    await useStudioStore.getState().selectTemplate('does-not-exist');
    expect(useStudioStore.getState().selectedTemplateId).toBeNull();
  });

  it('overlays persisted state when present', async () => {
    localStorage.setItem(
      'vanhorn:studio:t1',
      JSON.stringify({
        templateSpec: [baseVariable({ template_variable: 'overlay_var' })],
        dryRunResult: null,
        flowState: 'configuring',
        isDirty: true,
        savedAt: new Date().toISOString(),
      }),
    );
    useStudioStore.setState({ templates: [sampleTemplate] });
    await useStudioStore.getState().selectTemplate('t1');
    const s = useStudioStore.getState();
    expect(s.templateSpec[0]!.template_variable).toBe('overlay_var');
    expect(s.flowState).toBe('configuring');
    expect(s.isDirty).toBe(true);
  });
});

describe('resetToNew', () => {
  it('returns store to empty template baseline', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templateSpec: [baseVariable()],
      flowState: 'verified',
      isDirty: true,
    });
    useStudioStore.getState().resetToNew();
    const s = useStudioStore.getState();
    expect(s.selectedTemplateId).toBeNull();
    expect(s.templateSpec).toEqual([]);
    expect(s.flowState).toBe('new');
    expect(s.isDirty).toBe(false);
  });
});

describe('loadCases / loadTemplates / loadConnectors / loadReferenceData', () => {
  it('loadCases populates cases and clears loading flag', async () => {
    mockedApi.listCases.mockResolvedValue({
      data: { cases: [sampleCase], total: 1, limit: 20, offset: 0, has_more: false },
    });
    await useStudioStore.getState().loadCases();
    const s = useStudioStore.getState();
    expect(s.cases).toEqual([sampleCase]);
    expect(s.isLoadingCases).toBe(false);
    expect(s.casesTotal).toBe(1);
    expect(s.casesHasMore).toBe(false);
    expect(s.error).toBeNull();
  });

  it('loadCases surfaces error from response', async () => {
    mockedApi.listCases.mockResolvedValue({ error: 'boom' });
    await useStudioStore.getState().loadCases();
    expect(useStudioStore.getState().error).toBe('boom');
  });

  it('loadTemplates populates templates', async () => {
    mockedApi.listTemplates.mockResolvedValue({ data: [sampleTemplate] });
    await useStudioStore.getState().loadTemplates();
    expect(useStudioStore.getState().templates).toEqual([sampleTemplate]);
  });

  it('loadConnectors filters out hidden sources', async () => {
    const connectors: Connector[] = [
      { source: 'gmail', display_name: 'Gmail', description: '', params: [] },
      { source: 'group_dropdown_from_gmail', display_name: 'GD Gmail', description: '', params: [] },
      { source: 'group_dropdown_from_court_drive', display_name: 'GD CD', description: '', params: [] },
    ];
    mockedApi.listConnectors.mockResolvedValue({ data: connectors });
    await useStudioStore.getState().loadConnectors();
    const visible = useStudioStore.getState().connectors.map((c) => c.source);
    expect(visible).toEqual(['gmail']);
  });

  it('loadReferenceData populates referenceData', async () => {
    mockedApi.listReferenceData.mockResolvedValue({ data: [referenceEntry] });
    await useStudioStore.getState().loadReferenceData();
    expect(useStudioStore.getState().referenceData).toEqual([referenceEntry]);
  });
});

describe('refreshCase', () => {
  it('replaces the matching case in the cases array', async () => {
    useStudioStore.setState({ cases: [sampleCase] });
    const updated = { ...sampleCase, case_name: 'Doe, J.' };
    mockedApi.getCase.mockResolvedValue({ data: updated });
    const result = await useStudioStore.getState().refreshCase('c1');
    expect(result.success).toBe(true);
    expect(useStudioStore.getState().cases[0]!.case_name).toBe('Doe, J.');
  });

  it('returns error when fetch fails', async () => {
    mockedApi.getCase.mockResolvedValue({ error: 'no such case' });
    const result = await useStudioStore.getState().refreshCase('missing');
    expect(result.success).toBe(false);
    expect(result.error).toBe('no such case');
  });
});

describe('createCase', () => {
  it('prepends the new case and selects it', async () => {
    mockedApi.createCase.mockResolvedValue({ data: createCaseResult });
    const result = await useStudioStore.getState().createCase(new File([''], 'p.pdf'));
    expect(result.success).toBe(true);
    const s = useStudioStore.getState();
    expect(s.cases[0]).toEqual(sampleCase);
    expect(s.selectedCaseId).toBe('c1');
  });

  it('on failure surfaces error and leaves cases unchanged', async () => {
    mockedApi.createCase.mockResolvedValue({ error: 'bad pdf' });
    const result = await useStudioStore.getState().createCase(new File([''], 'p.pdf'));
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().error).toBe('bad pdf');
  });
});

describe('uploadTemplate', () => {
  it('on success appends a new templates row and selects it', async () => {
    mockedApi.generateTemplate.mockResolvedValue({ data: generated });
    const result = await useStudioStore.getState().uploadTemplate('My Tpl', new File([''], 't.docx'));
    expect(result.success).toBe(true);
    const s = useStudioStore.getState();
    expect(s.selectedTemplateId).toBe('t2');
    expect(s.flowState).toBe('generated');
    expect(s.templates.find((t) => t.id === 't2')).toBeDefined();
  });

  it('replaces an existing template row when re-uploaded under the same id', async () => {
    useStudioStore.setState({
      templates: [{ ...sampleTemplate, id: 't2', name: 'Old' }],
    });
    mockedApi.generateTemplate.mockResolvedValue({ data: generated });
    await useStudioStore.getState().uploadTemplate('Generated', new File([''], 't.docx'));
    const matches = useStudioStore.getState().templates.filter((t) => t.id === 't2');
    expect(matches).toHaveLength(1);
    expect(matches[0]!.name).toBe('Generated');
  });

  it('on failure leaves selection untouched', async () => {
    mockedApi.generateTemplate.mockResolvedValue({ error: 'parse failed' });
    const result = await useStudioStore.getState().uploadTemplate('Tpl', new File([''], 't.docx'));
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().selectedTemplateId).toBeNull();
  });
});

describe('regenerateTemplate', () => {
  it('refuses when no template is selected', async () => {
    const result = await useStudioStore.getState().regenerateTemplate([], []);
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().error).toBe('No template selected');
  });

  it('clears agent_config and persisted overlay on success', async () => {
    localStorage.setItem(
      'vanhorn:studio:t1',
      JSON.stringify({
        templateSpec: [],
        dryRunResult: null,
        flowState: 'configuring',
        isDirty: true,
        savedAt: new Date().toISOString(),
      }),
    );
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templates: [sampleTemplate],
      agentConfig: { template_id: 't1', template_fields: [] },
    });
    mockedApi.regenerateTemplate.mockResolvedValue({
      data: { ...generated, template_id: 't1' },
    });
    mockedApi.listTemplates.mockResolvedValue({ data: [] });

    await useStudioStore.getState().regenerateTemplate(['ignored'], []);

    expect(useStudioStore.getState().agentConfig).toBeNull();
    expect(localStorage.getItem('vanhorn:studio:t1')).toBeNull();
    expect(useStudioStore.getState().flowState).toBe('generated');
  });

  it('stages the returned diff into store on success', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      templates: [sampleTemplate],
      regenerateDiff: null,
    });
    const diff = {
      added: ['debtor_phone'],
      removed: [
        { name: 'case_no_title', reason: 'merged' as const, merged_into: 'case_number' },
      ],
      preserved: ['case_number', 'debtor_name'],
    };
    mockedApi.regenerateTemplate.mockResolvedValue({
      data: { ...generated, template_id: 't1', diff },
    });
    mockedApi.listTemplates.mockResolvedValue({ data: [] });

    await useStudioStore.getState().regenerateTemplate([], []);

    const staged = useStudioStore.getState().regenerateDiff;
    expect(staged).not.toBeNull();
    expect(staged?.added).toEqual(['debtor_phone']);
    expect(staged?.removed[0]?.reason).toBe('merged');
    expect(staged?.preserved).toEqual(['case_number', 'debtor_name']);
  });

  it('clearRegenerateDiff resets the staged diff to null', () => {
    useStudioStore.setState({
      regenerateDiff: { added: [], removed: [], preserved: ['x'] },
    });
    useStudioStore.getState().clearRegenerateDiff();
    expect(useStudioStore.getState().regenerateDiff).toBeNull();
  });
});

describe('renameTemplate / deleteTemplate', () => {
  it('renameTemplate updates the matching row', async () => {
    const renamed = { ...sampleTemplate, name: 'New' };
    useStudioStore.setState({ templates: [sampleTemplate] });
    mockedApi.renameTemplate.mockResolvedValue({ data: renamed });
    mockedApi.listTemplates.mockResolvedValue({ data: [renamed] });
    await useStudioStore.getState().renameTemplate('t1', 'New');
    expect(mockedApi.renameTemplate).toHaveBeenCalledWith('t1', 'New');
  });

  it('deleteTemplate removes the row and resets state if it was selected', async () => {
    useStudioStore.setState({
      templates: [sampleTemplate],
      selectedTemplateId: 't1',
      templateSpec: [baseVariable()],
    });
    mockedApi.deleteTemplate.mockResolvedValue({ data: { success: true, id: 't1' } });
    await useStudioStore.getState().deleteTemplate('t1');
    const s = useStudioStore.getState();
    expect(s.templates).toEqual([]);
    expect(s.selectedTemplateId).toBeNull();
    expect(s.templateSpec).toEqual([]);
  });

  it('deleteTemplate keeps current selection if a different template was deleted', async () => {
    useStudioStore.setState({
      templates: [sampleTemplate, { ...sampleTemplate, id: 't2', name: 'Other' }],
      selectedTemplateId: 't1',
    });
    mockedApi.deleteTemplate.mockResolvedValue({ data: { success: true, id: 't2' } });
    await useStudioStore.getState().deleteTemplate('t2');
    expect(useStudioStore.getState().selectedTemplateId).toBe('t1');
  });

  it('deleteTemplate returns failure when API errors', async () => {
    mockedApi.deleteTemplate.mockResolvedValue({ error: 'not found' });
    const result = await useStudioStore.getState().deleteTemplate('t1');
    expect(result.success).toBe(false);
  });

  it('deleteTemplate surfaces conflictParents on 409 without mutating state', async () => {
    useStudioStore.setState({ templates: [sampleTemplate], selectedTemplateId: 't1' });
    const parents = [
      { template_id: 'parent-A', name: 'Motion to Waive', companion_labels: ['Cover'] },
    ];
    mockedApi.deleteTemplate.mockResolvedValue({
      error: 'Template is referenced by 1 parent template(s).',
      conflictParents: parents,
    });
    const result = await useStudioStore.getState().deleteTemplate('t1');

    expect(result.success).toBe(false);
    expect(result.conflictParents).toEqual(parents);
    // State must NOT have been mutated on conflict.
    expect(useStudioStore.getState().templates).toEqual([sampleTemplate]);
    expect(useStudioStore.getState().selectedTemplateId).toBe('t1');
  });

  it('deleteTemplate passes force flag through to the service', async () => {
    useStudioStore.setState({ templates: [sampleTemplate] });
    mockedApi.deleteTemplate.mockResolvedValue({
      data: { success: true, id: 't1', cleaned_parents: [
        { template_id: 'parent-A', name: 'Motion to Waive', removed_companion_labels: ['Cover'] },
      ] },
    });
    // When cleaned_parents is non-empty, the store triggers a templates
    // refetch to refresh stale role badges — mock it so the post-delete
    // call doesn't blow up the test environment.
    mockedApi.listTemplates.mockResolvedValue({ data: [] });
    const result = await useStudioStore.getState().deleteTemplate('t1', true);

    expect(mockedApi.deleteTemplate).toHaveBeenCalledWith('t1', true);
    expect(result.success).toBe(true);
    expect(result.cleanedParents).toEqual([
      { template_id: 'parent-A', name: 'Motion to Waive', removed_companion_labels: ['Cover'] },
    ]);
    // Verify the post-force-delete refetch fired.
    expect(mockedApi.listTemplates).toHaveBeenCalled();
  });

  it('deleteTemplate does NOT refetch templates on plain delete (no cleaned parents)', async () => {
    useStudioStore.setState({ templates: [sampleTemplate] });
    mockedApi.deleteTemplate.mockResolvedValue({ data: { success: true, id: 't1' } });
    mockedApi.listTemplates.mockResolvedValue({ data: [] });

    await useStudioStore.getState().deleteTemplate('t1');

    // No cleaned_parents → no refetch fired.
    expect(mockedApi.listTemplates).not.toHaveBeenCalled();
  });
});

describe('reference data CRUD', () => {
  it('refreshReferenceData replaces the matching row', async () => {
    useStudioStore.setState({ referenceData: [referenceEntry] });
    const fresh = { ...referenceEntry, value: 'Updated' };
    mockedApi.getReferenceData.mockResolvedValue({ data: fresh });
    const result = await useStudioStore.getState().refreshReferenceData('firm_address');
    expect(result.success).toBe(true);
    expect(useStudioStore.getState().referenceData[0]!.value).toBe('Updated');
  });

  it('createReferenceData appends a new row', async () => {
    mockedApi.createReferenceData.mockResolvedValue({ data: referenceEntry });
    await useStudioStore.getState().createReferenceData({
      name: 'Firm Address',
      value: '123 Main St',
    });
    expect(useStudioStore.getState().referenceData).toContainEqual(referenceEntry);
  });

  it('updateReferenceData replaces the matching row', async () => {
    useStudioStore.setState({ referenceData: [referenceEntry] });
    const updated = { ...referenceEntry, value: 'New' };
    mockedApi.updateReferenceData.mockResolvedValue({ data: updated });
    await useStudioStore.getState().updateReferenceData('firm_address', { value: 'New' });
    expect(useStudioStore.getState().referenceData[0]!.value).toBe('New');
  });

  it('all three reference-data actions return failure with error string on api error', async () => {
    mockedApi.getReferenceData.mockResolvedValue({ error: 'gone' });
    mockedApi.createReferenceData.mockResolvedValue({ error: 'dup' });
    mockedApi.updateReferenceData.mockResolvedValue({ error: '404' });
    expect((await useStudioStore.getState().refreshReferenceData('x')).error).toBe('gone');
    expect((await useStudioStore.getState().createReferenceData({ name: '', value: '' })).error).toBe('dup');
    expect((await useStudioStore.getState().updateReferenceData('x', {})).error).toBe('404');
  });
});

describe('dry-run resume + dismiss', () => {
  it('resumeDryRun returns failure when nothing is paused', async () => {
    const result = await useStudioStore.getState().resumeDryRun({});
    expect(result.success).toBe(false);
    expect(useStudioStore.getState().actionError?.message).toBe('No paused dry-run to resume');
  });

  it('resumeDryRun routes to dryRunResume with awaiting envelope values', async () => {
    useStudioStore.setState({ dryRunAwaiting: awaitingResult, selectedTemplateId: 't1' });
    mockedApi.dryRunResume.mockResolvedValue({ data: dryRunCompleted });
    await useStudioStore.getState().resumeDryRun({});
    expect(mockedApi.dryRunResume).toHaveBeenCalledWith(
      awaitingResult.template_id,
      [],
      awaitingResult.case_id,
      awaitingResult.resolved_values,
      {},
      null,
      'standalone',
      null,
    );
    expect(useStudioStore.getState().dryRunResult).toEqual(dryRunCompleted);
    expect(useStudioStore.getState().flowState).toBe('verified');
  });

  it('resumeDryRun keeps modal open when BE returns another awaiting envelope', async () => {
    useStudioStore.setState({ dryRunAwaiting: awaitingResult });
    mockedApi.dryRunResume.mockResolvedValue({ data: { ...awaitingResult, run_id: 'next' } });
    await useStudioStore.getState().resumeDryRun({});
    expect(useStudioStore.getState().dryRunAwaiting?.run_id).toBe('next');
  });

  it('dismissDryRunAwaiting clears the envelope', () => {
    useStudioStore.setState({ dryRunAwaiting: awaitingResult });
    useStudioStore.getState().dismissDryRunAwaiting();
    expect(useStudioStore.getState().dryRunAwaiting).toBeNull();
  });

  it('dismissDryRunResult clears the result and updates the persisted overlay', () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      dryRunResult: dryRunCompleted,
      templateSpec: [baseVariable()],
      flowState: 'verified',
    });
    useStudioStore.getState().dismissDryRunResult();
    expect(useStudioStore.getState().dryRunResult).toBeNull();
    const stored = JSON.parse(localStorage.getItem('vanhorn:studio:t1')!);
    expect(stored.dryRunResult).toBeNull();
  });
});

describe('draft resume + dismiss', () => {
  it('dismissDraftAwaiting and dismissDraftResult clear their slots', () => {
    useStudioStore.setState({
      draftAwaiting: awaitingResult,
      draftResult: { ...dryRunCompleted, status: 'completed', case_id: 'c1' } as never,
    });
    useStudioStore.getState().dismissDraftAwaiting();
    expect(useStudioStore.getState().draftAwaiting).toBeNull();
    useStudioStore.getState().dismissDraftResult();
    expect(useStudioStore.getState().draftResult).toBeNull();
  });

  it('resumeDraft keeps modal open on another awaiting envelope', async () => {
    useStudioStore.setState({ draftAwaiting: awaitingResult });
    mockedApi.draftResume.mockResolvedValue({ data: { ...awaitingResult, run_id: 'second' } });
    await useStudioStore.getState().resumeDraft({});
    expect(useStudioStore.getState().draftAwaiting?.run_id).toBe('second');
  });
});

describe('retryLastAction + clearActionError', () => {
  it('returns failure when nothing to retry', async () => {
    const result = await useStudioStore.getState().retryLastAction();
    expect(result.success).toBe(false);
  });

  it('retries the dry-run when actionError.kind === "dry-run"', async () => {
    useStudioStore.setState({
      actionError: { kind: 'dry-run', message: 'failed' },
      selectedTemplateId: 't1',
      selectedCaseId: 'c1',
      templateSpec: [baseVariable()],
      referenceData: [],
    });
    mockedApi.dryRun.mockResolvedValue({ data: dryRunCompleted });
    await useStudioStore.getState().retryLastAction();
    expect(mockedApi.dryRun).toHaveBeenCalled();
  });

  it('retries the save when actionError.kind === "save"', async () => {
    useStudioStore.setState({
      actionError: { kind: 'save', message: 'failed' },
      selectedTemplateId: 't1',
      templateSpec: [baseVariable()],
    });
    mockedApi.composeAgentConfig.mockResolvedValue({
      data: { template_id: 't1', template_fields: [] },
    });
    mockedApi.listTemplates.mockResolvedValue({ data: [] });
    await useStudioStore.getState().retryLastAction();
    expect(mockedApi.composeAgentConfig).toHaveBeenCalled();
  });

  it('clearActionError resets actionError to null', () => {
    useStudioStore.setState({ actionError: { kind: 'save', message: 'x' } });
    useStudioStore.getState().clearActionError();
    expect(useStudioStore.getState().actionError).toBeNull();
  });

  it('clearError resets error to null', () => {
    useStudioStore.setState({ error: 'boom' });
    useStudioStore.getState().clearError();
    expect(useStudioStore.getState().error).toBeNull();
  });
});

describe('runDraft — additional gates', () => {
  it('refuses without a case selected', async () => {
    useStudioStore.setState({ selectedTemplateId: 't1', agentConfig: { template_id: 't1', template_fields: [] } });
    const result = await useStudioStore.getState().runDraft();
    expect(result.success).toBe(false);
    expect(result.error).toMatch(/case selected/);
  });

  it('refuses without a template selected', async () => {
    useStudioStore.setState({ selectedCaseId: 'c1' });
    const result = await useStudioStore.getState().runDraft();
    expect(result.success).toBe(false);
    expect(result.error).toBe('No template selected');
  });

  it('opens awaiting envelope without setting draftResult when BE pauses', async () => {
    useStudioStore.setState({
      selectedTemplateId: 't1',
      selectedCaseId: 'c1',
      agentConfig: { template_id: 't1', template_fields: [] },
    });
    mockedApi.draft.mockResolvedValue({ data: awaitingResult });
    await useStudioStore.getState().runDraft();
    expect(useStudioStore.getState().draftAwaiting).toEqual(awaitingResult);
    expect(useStudioStore.getState().draftResult).toBeNull();
  });
});
