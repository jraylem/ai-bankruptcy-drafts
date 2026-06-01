import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiService = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  default: apiService,
}));

import {
  composeAgentConfig,
  createCase,
  createReferenceData,
  deleteTemplate,
  draft,
  draftResume,
  dryRun,
  dryRunResume,
  generateTemplate,
  getCase,
  getReferenceData,
  listCases,
  listConnectors,
  listReferenceData,
  listTemplates,
  parseDocument,
  regenerateTemplate,
  renameTemplate,
  studioApi,
  updateReferenceData,
  uploadSupportingDocs,
} from '@/services/studio.service';
import { API_ENDPOINTS } from '@/constants';

const ok = <T>(data: T) => ({ data });

beforeEach(() => {
  for (const fn of Object.values(apiService)) fn.mockReset();
});

afterEach(() => {
  for (const fn of Object.values(apiService)) fn.mockReset();
});

describe('cases', () => {
  it('listCases GETs /cases with default pagination', async () => {
    apiService.get.mockResolvedValue(ok({ cases: [], total: 0, limit: 20, offset: 0, has_more: false }));
    await listCases();
    expect(apiService.get).toHaveBeenCalledWith(`${API_ENDPOINTS.CORE.CASES}?limit=20&offset=0`);
  });

  it('listCases threads custom limit/offset', async () => {
    apiService.get.mockResolvedValue(ok({ cases: [], total: 0, limit: 5, offset: 10, has_more: false }));
    await listCases({ limit: 5, offset: 10 });
    expect(apiService.get).toHaveBeenCalledWith(`${API_ENDPOINTS.CORE.CASES}?limit=5&offset=10`);
  });

  it('getCase GETs /cases/{id} with encoded id', async () => {
    apiService.get.mockResolvedValue(ok({}));
    await getCase('case 42');
    expect(apiService.get).toHaveBeenCalledWith(API_ENDPOINTS.CORE.CASE_BY_ID('case 42'));
  });

  it('createCase POSTs multipart with petition file', async () => {
    apiService.post.mockResolvedValue(ok({}));
    const file = new File(['x'], 'petition.pdf', { type: 'application/pdf' });
    await createCase(file);
    const [url, body, opts] = apiService.post.mock.calls[0]!;
    expect(url).toBe(API_ENDPOINTS.CORE.CASES);
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get('petition')).toBe(file);
    expect(opts.headers['Content-Type']).toBe('multipart/form-data');
  });

  it('uploadSupportingDocs POSTs all files under "files"', async () => {
    apiService.post.mockResolvedValue(ok([]));
    const a = new File(['a'], 'a.pdf');
    const b = new File(['b'], 'b.pdf');
    await uploadSupportingDocs('c1', [a, b]);
    const [url, body] = apiService.post.mock.calls[0]!;
    expect(url).toBe(API_ENDPOINTS.CORE.CASE_SUPPORTING_DOCS('c1'));
    expect((body as FormData).getAll('files')).toEqual([a, b]);
  });
});

describe('templates CRUD', () => {
  it('listTemplates GETs /template', async () => {
    apiService.get.mockResolvedValue(ok([]));
    await listTemplates();
    expect(apiService.get).toHaveBeenCalledWith(API_ENDPOINTS.CORE.TEMPLATES);
  });

  it('renameTemplate PUTs { name }', async () => {
    apiService.put.mockResolvedValue(ok({}));
    await renameTemplate('t1', 'New');
    expect(apiService.put).toHaveBeenCalledWith(
      API_ENDPOINTS.CORE.TEMPLATE_BY_ID('t1'),
      { name: 'New' },
    );
  });

  it('deleteTemplate DELETEs /template/{id}', async () => {
    apiService.delete.mockResolvedValue(ok({ success: true, id: 't1' }));
    await deleteTemplate('t1');
    expect(apiService.delete).toHaveBeenCalledWith(API_ENDPOINTS.CORE.TEMPLATE_BY_ID('t1'));
  });

  it('deleteTemplate appends ?force=true when called with force', async () => {
    apiService.delete.mockResolvedValue(ok({ success: true, id: 't1' }));
    await deleteTemplate('t1', true);
    expect(apiService.delete).toHaveBeenCalledWith(
      `${API_ENDPOINTS.CORE.TEMPLATE_BY_ID('t1')}?force=true`,
    );
  });

  it('deleteTemplate omits force query param when called with force=false', async () => {
    apiService.delete.mockResolvedValue(ok({ success: true, id: 't1' }));
    await deleteTemplate('t1', false);
    expect(apiService.delete).toHaveBeenCalledWith(API_ENDPOINTS.CORE.TEMPLATE_BY_ID('t1'));
  });
});

describe('composer', () => {
  it('parseDocument POSTs multipart with document file', async () => {
    apiService.post.mockResolvedValue(ok({}));
    const file = new File(['x'], 'doc.docx');
    await parseDocument(file);
    const [url, body] = apiService.post.mock.calls[0]!;
    expect(url).toBe(API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_PARSE);
    expect((body as FormData).get('document')).toBe(file);
  });

  it('generateTemplate POSTs to the templated URL with the docx', async () => {
    apiService.post.mockResolvedValue(ok({}));
    const file = new File(['x'], 'doc.docx');
    await generateTemplate('My Tpl', file);
    const [url] = apiService.post.mock.calls[0]!;
    expect(url).toBe(API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_GENERATE('My Tpl'));
  });

  it('regenerateTemplate PUTs body with ignored_texts + merges + null instruction by default', async () => {
    apiService.put.mockResolvedValue(ok({}));
    await regenerateTemplate('t1', ['ignore me'], [{ source_variables: ['a', 'b'] }]);
    expect(apiService.put).toHaveBeenCalledWith(
      API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_REGENERATE('t1'),
      {
        ignored_texts: ['ignore me'],
        merges: [{ source_variables: ['a', 'b'] }],
        regeneration_instruction: null,
      },
    );
  });

  it('regenerateTemplate forwards explicit instruction', async () => {
    apiService.put.mockResolvedValue(ok({}));
    await regenerateTemplate('t1', [], [], 'extract footer dates');
    expect(apiService.put.mock.calls[0]![1]).toMatchObject({
      regeneration_instruction: 'extract footer dates',
    });
  });

  it('composeAgentConfig POSTs the spec to the templated URL', async () => {
    apiService.post.mockResolvedValue(ok({}));
    await composeAgentConfig('t1', []);
    expect(apiService.post).toHaveBeenCalledWith(
      API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_COMPOSE_AGENT_CONFIG('t1'),
      [],
    );
  });
});

describe('dry-run + draft', () => {
  it('dryRun POSTs body with template_id + template_spec + case_id (bundle fields default to null)', async () => {
    apiService.post.mockResolvedValue(ok({}));
    await dryRun('t1', [], 'c1');
    expect(apiService.post).toHaveBeenCalledWith(API_ENDPOINTS.CORE.TEMPLATE_DRY_RUN, {
      template_id: 't1',
      template_spec: [],
      case_id: 'c1',
      bundle_picks: null,
      bundle_role: null,
      bundle_companions: null,
    });
  });

  it('dryRun forwards bundle_picks + candidate bundle_role + bundle_companions when supplied', async () => {
    apiService.post.mockResolvedValue(ok({}));
    await dryRun('t1', [], 'c1', { '0': 'No' }, 'parent', [{ kind: 'fixed' }]);
    expect(apiService.post).toHaveBeenCalledWith(API_ENDPOINTS.CORE.TEMPLATE_DRY_RUN, {
      template_id: 't1',
      template_spec: [],
      case_id: 'c1',
      bundle_picks: { '0': 'No' },
      bundle_role: 'parent',
      bundle_companions: [{ kind: 'fixed' }],
    });
  });

  it('dryRunResume POSTs the full echo payload (BE is stateless)', async () => {
    apiService.post.mockResolvedValue(ok({}));
    await dryRunResume('t1', [], 'c1', [], { foo: { value: 'bar' } });
    expect(apiService.post).toHaveBeenCalledWith(
      API_ENDPOINTS.CORE.TEMPLATE_DRY_RUN_RESUME,
      {
        template_id: 't1',
        template_spec: [],
        case_id: 'c1',
        resolved_values: [],
        user_picks: { foo: { value: 'bar' } },
        bundle_picks: null,
        bundle_role: null,
        bundle_companions: null,
      },
    );
  });

  it('draft POSTs template_id + case_id with null bundle_picks by default', async () => {
    apiService.post.mockResolvedValue(ok({}));
    await draft('t1', 'c1');
    expect(apiService.post).toHaveBeenCalledWith(API_ENDPOINTS.CORE.DRAFT, {
      template_id: 't1',
      case_id: 'c1',
      bundle_picks: null,
    });
  });

  it('draftResume POSTs the echo payload', async () => {
    apiService.post.mockResolvedValue(ok({}));
    await draftResume('t1', 'c1', [], {});
    expect(apiService.post).toHaveBeenCalledWith(API_ENDPOINTS.CORE.DRAFT_RESUME, {
      template_id: 't1',
      case_id: 'c1',
      resolved_values: [],
      user_picks: {},
      bundle_picks: null,
    });
  });
});

describe('reference-data', () => {
  it('listReferenceData GETs the bare URL when no category', async () => {
    apiService.get.mockResolvedValue(ok([]));
    await listReferenceData();
    expect(apiService.get).toHaveBeenCalledWith(API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA);
  });

  it('listReferenceData appends ?category=... when category passed', async () => {
    apiService.get.mockResolvedValue(ok([]));
    await listReferenceData('addresses');
    const [url] = apiService.get.mock.calls[0]!;
    expect(url).toContain('?category=addresses');
  });

  it('listReferenceData percent-encodes category', async () => {
    apiService.get.mockResolvedValue(ok([]));
    await listReferenceData('a/b c');
    const [url] = apiService.get.mock.calls[0]!;
    expect(url).toContain('?category=a%2Fb%20c');
  });

  it('getReferenceData GETs by short_code', async () => {
    apiService.get.mockResolvedValue(ok({}));
    await getReferenceData('firm_address');
    expect(apiService.get).toHaveBeenCalledWith(
      API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA_BY_CODE('firm_address'),
    );
  });

  it('createReferenceData POSTs the payload', async () => {
    apiService.post.mockResolvedValue(ok({}));
    await createReferenceData({ name: 'Firm', value: '123' });
    expect(apiService.post).toHaveBeenCalledWith(
      API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA,
      { name: 'Firm', value: '123' },
    );
  });

  it('updateReferenceData PUTs the payload to the encoded short_code URL', async () => {
    apiService.put.mockResolvedValue(ok({}));
    await updateReferenceData('firm_address', { value: '456' });
    expect(apiService.put).toHaveBeenCalledWith(
      API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA_BY_CODE('firm_address'),
      { value: '456' },
    );
  });
});

describe('connectors', () => {
  it('listConnectors GETs /template/connectors', async () => {
    apiService.get.mockResolvedValue(ok([]));
    await listConnectors();
    expect(apiService.get).toHaveBeenCalledWith(API_ENDPOINTS.CORE.TEMPLATE_CONNECTORS);
  });
});

describe('studioApi namespace alias', () => {
  it('exposes the same functions as the named exports', () => {
    expect(studioApi.listCases).toBe(listCases);
    expect(studioApi.draftResume).toBe(draftResume);
    expect(studioApi.composeAgentConfig).toBe(composeAgentConfig);
    expect(studioApi.listConnectors).toBe(listConnectors);
  });

  it('contains every function (count matches the named exports)', () => {
    const expected = [
      'listCases', 'getCase', 'createCase', 'uploadSupportingDocs',
      'listTemplates', 'renameTemplate', 'deleteTemplate',
      'parseDocument', 'generateTemplate', 'regenerateTemplate', 'composeAgentConfig',
      'dryRun', 'dryRunResume', 'draft', 'draftResume',
      'listReferenceData', 'getReferenceData', 'createReferenceData', 'updateReferenceData',
      'listConnectors',
    ];
    for (const k of expected) {
      expect(studioApi).toHaveProperty(k);
    }
  });
});
