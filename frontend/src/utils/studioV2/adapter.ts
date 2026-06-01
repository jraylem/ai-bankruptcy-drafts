/**
 * Adapter — TemplateV2Response (wire shape) → StudioTemplate (existing
 * UI component shape).
 *
 * Phase 1 keeps the existing studio-v2 mock components consuming
 * StudioTemplate so the wizard / rail / preview don't need touching
 * during the BE wiring sprint. Once the BE-truth flow is demoed,
 * a follow-up will swap the components to consume the wire types
 * directly and this adapter goes away.
 */

import type {
  StudioTemplate,
  StudioVariable,
  TemplateConfig,
} from '@/components/studio-v2/types';
import type {
  TemplateFieldV2Response,
  TemplateFieldV2Spec,
  TemplateSpecV2Wire,
  TemplateV2Response,
} from '@/types/studio-v2';

export const adaptFieldToStudioVariable = (
  field: TemplateFieldV2Response,
): StudioVariable => ({
  template_variable: field.template_variable,
  description: field.description ?? '',
  template_property_marker: field.template_property_marker,
  template_identifying_text_match: field.template_identifying_text_match,
  params: field.params,
});

export const adaptResponseToStudioTemplate = (
  response: TemplateV2Response,
): StudioTemplate => ({
  id: response.id,
  name: response.name,
  config: (response.config ?? { role: 'single', companions: [] }) as TemplateConfig,
  variables: (response.fields ?? [])
    .slice()
    .sort((a, b) => a.template_index - b.template_index)
    .map(adaptFieldToStudioVariable),
  updatedRelative: formatRelativeTime(response.updated_at ?? response.created_at),
  publishedAt: response.published_at ?? null,
  hasUnpublishedChanges: response.has_unpublished_changes,
  totalFields: response.total_fields,
  configuredFields: response.configured_fields,
});

export const formatRelativeTime = (iso: string | null): string => {
  if (!iso) return 'just now';
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return 'just now';
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
};

/**
 * Build the `TemplateSpecV2` wire shape the BE dry-run endpoint
 * accepts from a `TemplateV2Response`. Strips API-only fields
 * (`created_at`, `updated_at`) the BE's `extra=forbid` spec rejects.
 *
 * Field shape matches BE `TemplateFieldV2`: carries `id` +
 * `template_id` (required) but NOT `template_variable_string`
 * (v1-only — v2 uses the `[[{template_variable}]]` convention
 * baked into the docx fill helper).
 */
export const buildSpecV2Wire = (
  response: TemplateV2Response,
): TemplateSpecV2Wire => ({
  template_id: response.id,
  fields: (response.fields ?? [])
    .slice()
    .sort((a, b) => a.template_index - b.template_index)
    .map(
      (f: TemplateFieldV2Response): TemplateFieldV2Spec => ({
        id: f.id,
        template_id: f.template_id,
        template_variable: f.template_variable,
        template_property_marker: f.template_property_marker,
        template_property_marker_aliases: f.template_property_marker_aliases,
        template_identifying_text_match: f.template_identifying_text_match,
        description: f.description,
        template_index: f.template_index,
        params: f.params,
      }),
    ),
});
