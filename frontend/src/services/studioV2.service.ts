import apiService from './api';
import { API_ENDPOINTS } from '@/constants';
import type { ApiResponse } from '@/types';
import type { SupportingDocUploadResponse } from '@/types/studio/resolution';
import type {
  BundlingConfigRequest,
  DeleteTemplateResponseV2,
  DocumentParseResponseV2,
  DryRunRequestV2,
  DryRunResponseV2,
  DryRunResultV2,
  DryRunResumeRequestV2,
  FieldPatchRequest,
  RegenerateTemplateRequest,
  TemplateFieldV2Response,
  TemplateGenerateResponseV2,
  TemplateRegenerateDiffV2,
  TemplateV2Response,
} from '@/types/studio-v2';

const MULTIPART_HEADERS = { 'Content-Type': 'multipart/form-data' };

// ─── Composer ──────────────────────────────────────────────────────────

export const parseDocumentV2 = (
  file: File,
): Promise<ApiResponse<DocumentParseResponseV2>> => {
  const fd = new FormData();
  fd.append('document', file);
  return apiService.post<DocumentParseResponseV2>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_PARSE,
    fd,
    { headers: MULTIPART_HEADERS },
  );
};

export const generateTemplateV2 = (
  file: File,
  templateName: string,
  templateRole: 'single' | 'master' | 'part_of_packet' = 'single',
): Promise<ApiResponse<TemplateGenerateResponseV2>> => {
  const fd = new FormData();
  fd.append('document', file);
  fd.append('template_name', templateName);
  fd.append('template_role', templateRole);
  return apiService.post<TemplateGenerateResponseV2>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_GENERATE,
    fd,
    { headers: MULTIPART_HEADERS },
  );
};

export const regenerateTemplateV2 = (
  templateId: string,
  body: RegenerateTemplateRequest,
): Promise<ApiResponse<TemplateRegenerateDiffV2>> =>
  apiService.put<TemplateRegenerateDiffV2>(
    API_ENDPOINTS.STUDIO_V2.COMPOSER_REGENERATE(templateId),
    body,
  );

// ─── Templates CRUD ───────────────────────────────────────────────────

export const listTemplatesV2 = (): Promise<ApiResponse<TemplateV2Response[]>> =>
  apiService.get<TemplateV2Response[]>(API_ENDPOINTS.STUDIO_V2.TEMPLATES);

export const getTemplateV2 = (
  templateId: string,
): Promise<ApiResponse<TemplateV2Response>> =>
  apiService.get<TemplateV2Response>(
    API_ENDPOINTS.STUDIO_V2.TEMPLATE_BY_ID(templateId),
  );

export const patchTemplateFieldV2 = (
  templateId: string,
  fieldId: string,
  body: FieldPatchRequest,
): Promise<ApiResponse<TemplateFieldV2Response>> =>
  apiService.patch<TemplateFieldV2Response>(
    API_ENDPOINTS.STUDIO_V2.TEMPLATE_FIELD_PATCH(templateId, fieldId),
    body,
  );

export const putTemplateBundlingConfigV2 = (
  templateId: string,
  body: BundlingConfigRequest,
): Promise<ApiResponse<TemplateV2Response>> =>
  apiService.put<TemplateV2Response>(
    API_ENDPOINTS.STUDIO_V2.TEMPLATE_BUNDLING_CONFIG(templateId),
    body,
  );

export const deleteTemplateV2 = (
  templateId: string,
): Promise<ApiResponse<DeleteTemplateResponseV2>> =>
  apiService.delete<DeleteTemplateResponseV2>(
    API_ENDPOINTS.STUDIO_V2.TEMPLATE_BY_ID(templateId),
  );

// ─── Dry-run ──────────────────────────────────────────────────────────

export const dryRunTemplateV2 = (
  templateId: string,
  body: DryRunRequestV2,
): Promise<ApiResponse<DryRunResultV2>> =>
  apiService.post<DryRunResultV2>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN(templateId),
    body,
  );

export const resumeDryRunV2 = (
  templateId: string,
  body: DryRunResumeRequestV2,
): Promise<ApiResponse<DryRunResponseV2>> =>
  apiService.post<DryRunResponseV2>(
    API_ENDPOINTS.STUDIO_V2.DRY_RUN_RESUME(templateId),
    body,
  );

// ─── Publish ──────────────────────────────────────────────────────────

export const publishTemplateV2 = (
  templateId: string,
): Promise<ApiResponse<TemplateV2Response>> =>
  apiService.post<TemplateV2Response>(
    API_ENDPOINTS.STUDIO_V2.TEMPLATE_PUBLISH(templateId),
    {},
  );

// ─── Supporting docs upload ───────────────────────────────────────────
// Reuses the case-level endpoint (`POST /api/v2/core/cases/{case_id}/supporting-docs`)
// — same R2 prefix v2's _expand_supporting_docs reads from. Not a v1
// studio dependency: the route lives under cases/, not studio/.

export const uploadSupportingDocsV2 = (
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
