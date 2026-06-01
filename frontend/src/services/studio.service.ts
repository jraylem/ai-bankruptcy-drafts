
import apiService from './api';
import { API_ENDPOINTS } from '@/constants';
import type { ApiResponse } from '@/types';
import type {
  AgentConfig,
  Attorney,
  AttorneyCreate,
  AttorneyUpdate,
  BundleCompanion,
  CaseResponse,
  Connector,
  CreateCaseResult,
  DocumentParseResult,
  DraftOrAwaiting,
  DraftTemplateListItem,
  DryRunOrAwaiting,
  GenerateTemplateResult,
  MergeOperation,
  ReferenceData,
  ReferenceDataCreate,
  ReferenceDataUpdate,
  ResolvedTemplateValue,
  SupportingDocUploadResponse,
  TemplateBundleRole,
  TemplateVariable,
  UserSelection,
} from '@/types/studio';

const MULTIPART_HEADERS = { 'Content-Type': 'multipart/form-data' };

const buildFormData = (field: string, file: File): FormData => {
  const fd = new FormData();
  fd.append(field, file);
  return fd;
};

export interface CaseListPage {
  cases: CaseResponse[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export const listCases = (
  { limit = 20, offset = 0 }: { limit?: number; offset?: number } = {},
): Promise<ApiResponse<CaseListPage>> =>
  apiService.get<CaseListPage>(
    `${API_ENDPOINTS.CORE.CASES}?limit=${limit}&offset=${offset}`,
  );

export const getCase = (caseId: string): Promise<ApiResponse<CaseResponse>> =>
  apiService.get<CaseResponse>(API_ENDPOINTS.CORE.CASE_BY_ID(caseId));

export const getCasePetitionUrl = (
  caseId: string,
): Promise<ApiResponse<{ petition_pdf_url: string }>> =>
  apiService.get<{ petition_pdf_url: string }>(
    API_ENDPOINTS.CORE.CASE_PETITION_URL(caseId),
  );

export const createCase = (
  petition: File,
): Promise<ApiResponse<CreateCaseResult>> =>
  apiService.post<CreateCaseResult>(
    API_ENDPOINTS.CORE.CASES,
    buildFormData('petition', petition),
    { headers: MULTIPART_HEADERS },
  );

export const createCaseByCaseNumber = (
  caseNumber: string,
): Promise<ApiResponse<CreateCaseResult>> =>
  apiService.post<CreateCaseResult>(
    API_ENDPOINTS.CORE.CASES_EXTRACT_BY_NUMBER,
    { case_number: caseNumber },
  );

export const uploadSupportingDocs = (
  caseId: string,
  files: File[],
): Promise<ApiResponse<SupportingDocUploadResponse[]>> => {
  const fd = new FormData();
  for (const f of files) fd.append('files', f);
  return apiService.post<SupportingDocUploadResponse[]>(
    API_ENDPOINTS.CORE.CASE_SUPPORTING_DOCS(caseId),
    fd,
    { headers: MULTIPART_HEADERS },
  );
};

export const listTemplates = (): Promise<ApiResponse<DraftTemplateListItem[]>> =>
  apiService.get<DraftTemplateListItem[]>(API_ENDPOINTS.CORE.TEMPLATES);

export const renameTemplate = (
  templateId: string,
  name: string,
): Promise<ApiResponse<DraftTemplateListItem>> =>
  apiService.put<DraftTemplateListItem>(
    API_ENDPOINTS.CORE.TEMPLATE_BY_ID(templateId),
    { name },
  );

export const saveBundlingConfig = (
  templateId: string,
  bundle_role: TemplateBundleRole,
  bundle_companions: BundleCompanion[] | null,
): Promise<ApiResponse<DraftTemplateListItem>> =>
  apiService.put<DraftTemplateListItem>(
    API_ENDPOINTS.CORE.TEMPLATE_BUNDLING_CONFIG(templateId),
    { bundle_role, bundle_companions },
  );

export const deleteTemplate = (
  templateId: string,
  force = false,
): Promise<ApiResponse<{ success: boolean; id: string; cleaned_parents?: { template_id: string; name: string; removed_companion_labels: string[] }[] }>> =>
  apiService.delete(
    `${API_ENDPOINTS.CORE.TEMPLATE_BY_ID(templateId)}${force ? '?force=true' : ''}`,
  );

export const parseDocument = (
  document: File,
): Promise<ApiResponse<DocumentParseResult>> =>
  apiService.post<DocumentParseResult>(
    API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_PARSE,
    buildFormData('document', document),
    { headers: MULTIPART_HEADERS },
  );

export const generateTemplate = (
  templateName: string,
  document: File,
): Promise<ApiResponse<GenerateTemplateResult>> =>
  apiService.post<GenerateTemplateResult>(
    API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_GENERATE(templateName),
    buildFormData('document', document),
    { headers: MULTIPART_HEADERS },
  );

export const regenerateTemplate = (
  templateId: string,
  ignoredTexts: string[],
  merges: MergeOperation[],
  regenerationInstruction?: string | null,
): Promise<ApiResponse<GenerateTemplateResult>> =>
  apiService.put<GenerateTemplateResult>(
    API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_REGENERATE(templateId),
    {
      ignored_texts: ignoredTexts,
      merges,
      regeneration_instruction: regenerationInstruction ?? null,
    },
  );

export const composeAgentConfig = (
  templateId: string,
  templateSpec: TemplateVariable[],
): Promise<ApiResponse<AgentConfig>> =>
  apiService.post<AgentConfig>(
    API_ENDPOINTS.CORE.TEMPLATE_COMPOSER_COMPOSE_AGENT_CONFIG(templateId),
    templateSpec,
  );

export const dryRun = (
  templateId: string,
  templateSpec: TemplateVariable[],
  caseId: string,
  bundlePicks?: Record<string, string> | null,
  bundleRole?: string | null,
  bundleCompanions?: unknown[] | null,
): Promise<ApiResponse<DryRunOrAwaiting>> =>
  apiService.post<DryRunOrAwaiting>(API_ENDPOINTS.CORE.TEMPLATE_DRY_RUN, {
    template_id: templateId,
    template_spec: templateSpec,
    case_id: caseId,
    bundle_picks: bundlePicks ?? null,
    bundle_role: bundleRole ?? null,
    bundle_companions: bundleCompanions ?? null,
  });

export const dryRunResume = (
  templateId: string,
  templateSpec: TemplateVariable[],
  caseId: string,
  resolvedValues: ResolvedTemplateValue[],
  userPicks: Record<string, UserSelection>,
  bundlePicks?: Record<string, string> | null,
  bundleRole?: string | null,
  bundleCompanions?: unknown[] | null,
): Promise<ApiResponse<DryRunOrAwaiting>> =>
  apiService.post<DryRunOrAwaiting>(API_ENDPOINTS.CORE.TEMPLATE_DRY_RUN_RESUME, {
    template_id: templateId,
    template_spec: templateSpec,
    case_id: caseId,
    resolved_values: resolvedValues,
    user_picks: userPicks,
    bundle_picks: bundlePicks ?? null,
    bundle_role: bundleRole ?? null,
    bundle_companions: bundleCompanions ?? null,
  });

export const draft = (
  templateId: string,
  caseId: string,
  bundlePicks?: Record<string, string> | null,
): Promise<ApiResponse<DraftOrAwaiting>> =>
  apiService.post<DraftOrAwaiting>(API_ENDPOINTS.CORE.DRAFT, {
    template_id: templateId,
    case_id: caseId,
    bundle_picks: bundlePicks ?? null,
  });

export const draftResume = (
  templateId: string,
  caseId: string,
  resolvedValues: ResolvedTemplateValue[],
  userPicks: Record<string, UserSelection>,
  bundlePicks?: Record<string, string> | null,
): Promise<ApiResponse<DraftOrAwaiting>> =>
  apiService.post<DraftOrAwaiting>(API_ENDPOINTS.CORE.DRAFT_RESUME, {
    template_id: templateId,
    case_id: caseId,
    resolved_values: resolvedValues,
    user_picks: userPicks,
    bundle_picks: bundlePicks ?? null,
  });

export const listReferenceData = (
  category?: string,
): Promise<ApiResponse<ReferenceData[]>> => {
  const url = category
    ? `${API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA}?category=${encodeURIComponent(category)}`
    : API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA;
  return apiService.get<ReferenceData[]>(url);
};

export const getReferenceData = (
  shortCode: string,
): Promise<ApiResponse<ReferenceData>> =>
  apiService.get<ReferenceData>(
    API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA_BY_CODE(shortCode),
  );

export const createReferenceData = (
  payload: ReferenceDataCreate,
): Promise<ApiResponse<ReferenceData>> =>
  apiService.post<ReferenceData>(
    API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA,
    payload,
  );

export const updateReferenceData = (
  shortCode: string,
  payload: ReferenceDataUpdate,
): Promise<ApiResponse<ReferenceData>> =>
  apiService.put<ReferenceData>(
    API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA_BY_CODE(shortCode),
    payload,
  );

export const deleteReferenceData = (
  shortCode: string,
): Promise<ApiResponse<void>> =>
  apiService.delete<void>(
    API_ENDPOINTS.CORE.TEMPLATE_REFERENCE_DATA_BY_CODE(shortCode),
  );

export const listConnectors = (): Promise<ApiResponse<Connector[]>> =>
  apiService.get<Connector[]>(API_ENDPOINTS.CORE.TEMPLATE_CONNECTORS);

// Attorney roster — structured CRUD over the reserved ATTORNEYS
// reference_data row. Mutations go through these endpoints (not the
// generic reference-data PUT) so the FE doesn't hand-edit the JSON
// payload; the BE keeps the underlying row in sync.
export const listAttorneys = (): Promise<ApiResponse<Attorney[]>> =>
  apiService.get<Attorney[]>(API_ENDPOINTS.CORE.ATTORNEYS);

export const createAttorney = (
  payload: AttorneyCreate,
): Promise<ApiResponse<Attorney>> =>
  apiService.post<Attorney>(API_ENDPOINTS.CORE.ATTORNEYS, payload);

export const updateAttorney = (
  attorneyId: string,
  payload: AttorneyUpdate,
): Promise<ApiResponse<Attorney>> =>
  apiService.put<Attorney>(
    API_ENDPOINTS.CORE.ATTORNEY_BY_ID(attorneyId),
    payload,
  );

export const deleteAttorney = (
  attorneyId: string,
): Promise<ApiResponse<void>> =>
  apiService.delete<void>(API_ENDPOINTS.CORE.ATTORNEY_BY_ID(attorneyId));

export const studioApi = {
  listCases,
  getCase,
  getCasePetitionUrl,
  createCase,
  createCaseByCaseNumber,
  uploadSupportingDocs,
  listTemplates,
  renameTemplate,
  saveBundlingConfig,
  deleteTemplate,
  parseDocument,
  generateTemplate,
  regenerateTemplate,
  composeAgentConfig,
  dryRun,
  dryRunResume,
  draft,
  draftResume,
  listReferenceData,
  getReferenceData,
  createReferenceData,
  updateReferenceData,
  deleteReferenceData,
  listAttorneys,
  createAttorney,
  updateAttorney,
  deleteAttorney,
  listConnectors,
};
