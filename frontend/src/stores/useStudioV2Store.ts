/**
 * Studio V2 store — Phase 1 surface.
 *
 * Holds the BE-truth shape (TemplateV2Response[]) alongside an adapted
 * StudioTemplate[] that the existing UI components consume without
 * needing changes. The adapter is intentional scaffolding for Phase 1
 * — once the BE truth is in place and demoed, a follow-up cleanup
 * will swap the UI components to consume TemplateV2Response directly
 * and drop the adapter.
 *
 * Field-id tracking: the wizard saves variables by `template_variable`
 * name; the BE patches by `field_id`. The store maintains a per-
 * template name→id map so wizard saves know which row to PATCH.
 */

import { create } from 'zustand';

import { useToastStore } from './useToastStore';
import {
  deleteTemplateV2,
  generateTemplateV2,
  getTemplateV2,
  listTemplatesV2,
  patchTemplateFieldV2,
  publishTemplateV2,
  putTemplateBundlingConfigV2,
  regenerateTemplateV2,
} from '@/services/studioV2.service';
import { adaptResponseToStudioTemplate } from '@/utils/studioV2/adapter';
import type {
  StudioTemplate,
  TemplateConfig,
  WizardSourceParams,
} from '@/components/studio-v2/types';
import type {
  RegenerateTemplateRequest,
  TemplateV2Response,
} from '@/types/studio-v2';

interface StudioV2State {
  // BE-truth state
  templatesByIdRaw: Record<string, TemplateV2Response>;
  // FE-render state (derived from raw via the adapter)
  templatesById: Record<string, StudioTemplate>;
  templateOrder: string[]; // ids ordered by created_at DESC
  // Per-template name → field_id map for wizard saves
  fieldIdByVariable: Record<string, Record<string, string>>;

  // UI selection
  selectedTemplateId: string | null;

  // Per-template docx-content version counter — bumps when the
  // template.docx content changes server-side (composer generate /
  // regenerate). The Syncfusion preview includes this in its render
  // key so it knows to actually re-fetch the docx even though the R2
  // path didn't change (regenerate overwrites the same key, so the
  // path-only dedupe in TemplatePreviewV2 wouldn't catch it).
  // PATCH on a field does NOT bump this — params edits don't change
  // the docx content. Only composer writes do.
  docContentVersion: Record<string, number>;

  // Per-template "lazy fetch in flight" flag. Set to true while
  // `loadTemplate(id)` is waiting on /api/v3/studio/templates/{id};
  // SetupPanel reads it to show a skeleton/spinner over the fields
  // list so paralegals see feedback during the fetch instead of
  // fields appearing to materialize out of nowhere on completion.
  loadingTemplateById: Record<string, boolean>;

  // Async status
  loading: boolean;
  error: string | null;

  // Actions
  refreshTemplates: () => Promise<void>;
  loadTemplate: (templateId: string) => Promise<void>;
  selectTemplate: (templateId: string | null) => void;
  /** Bump the docx-content version for a template (force-reload the
   * Syncfusion preview). Called by composer-async task completion
   * handlers for `kind === 'generate' | 'regenerate'`. */
  bumpDocContentVersion: (templateId: string) => void;
  uploadAndGenerate: (
    file: File,
    templateName: string,
    role?: 'single' | 'master' | 'part_of_packet',
  ) => Promise<string | null>; // returns new template_id on success
  saveFieldParams: (
    templateId: string,
    variableName: string,
    params: WizardSourceParams,
  ) => Promise<void>;
  saveBundlingConfig: (
    templateId: string,
    config: TemplateConfig,
    opts?: { silent?: boolean },
  ) => Promise<string | null>;
  regenerateTemplate: (
    templateId: string,
    body: RegenerateTemplateRequest,
  ) => Promise<void>;
  removeTemplate: (templateId: string) => Promise<void>;
  // Publish the working draft to `published_spec` after validators
  // pass. On failure returns the validation error strings so the
  // caller (PublishStep) can render them inline.
  publishTemplate: (templateId: string) => Promise<PublishResult>;
}

export type PublishResult =
  | { ok: true }
  | { ok: false; validationErrors: string[]; error: string };

const _ingestTemplate = (
  state: StudioV2State,
  response: TemplateV2Response,
): Partial<StudioV2State> => {
  const id = response.id;
  const mock = adaptResponseToStudioTemplate(response);
  const fieldIds: Record<string, string> = {};
  for (const f of response.fields ?? []) {
    fieldIds[f.template_variable] = f.id;
  }
  const order = state.templateOrder.includes(id)
    ? state.templateOrder
    : [id, ...state.templateOrder];
  return {
    templatesByIdRaw: { ...state.templatesByIdRaw, [id]: response },
    templatesById: { ...state.templatesById, [id]: mock },
    fieldIdByVariable: { ...state.fieldIdByVariable, [id]: fieldIds },
    templateOrder: order,
  };
};

export const useStudioV2Store = create<StudioV2State>((set, get) => ({
  templatesByIdRaw: {},
  templatesById: {},
  templateOrder: [],
  fieldIdByVariable: {},
  selectedTemplateId: null,
  docContentVersion: {},
  loadingTemplateById: {},
  loading: false,
  error: null,

  refreshTemplates: async () => {
    set({ loading: true, error: null });
    const { data, error } = await listTemplatesV2();
    if (error || !data) {
      set({ loading: false, error: error ?? 'Failed to load templates' });
      return;
    }
    // The list endpoint returns `fields: []` (only total/configured
    // counts) — full field arrays come from the single-template
    // endpoint. When refreshTemplates runs after composer-async task
    // completion, we DON'T want to wipe the fields we already lazy-
    // loaded for the selected template (would cause renderKey churn
    // → double load in TemplatePreviewV2 + an empty-vars window in
    // the wizard). Merge per-template: if list response has empty
    // fields AND we already have fields cached, keep the cached
    // fields.
    const existingRaw = get().templatesByIdRaw;
    const existingFieldIds = get().fieldIdByVariable;
    const order = data.map((t) => t.id);
    const raw: Record<string, TemplateV2Response> = {};
    const mocks: Record<string, StudioTemplate> = {};
    const fieldIds: Record<string, Record<string, string>> = {};
    for (const t of data) {
      const prior = existingRaw[t.id];
      const priorHasFields = prior && (prior.fields?.length ?? 0) > 0;
      const merged: TemplateV2Response =
        t.fields.length === 0 && priorHasFields
          ? { ...t, fields: prior.fields }
          : t;
      raw[t.id] = merged;
      mocks[t.id] = adaptResponseToStudioTemplate(merged);
      if (merged.fields.length > 0) {
        fieldIds[t.id] = {};
        for (const f of merged.fields) {
          fieldIds[t.id][f.template_variable] = f.id;
        }
      } else {
        // Preserve fieldIdByVariable when we kept prior fields above;
        // otherwise leave the slot empty so loadTemplate fills it.
        fieldIds[t.id] = existingFieldIds[t.id] ?? {};
      }
    }
    set({
      templatesByIdRaw: raw,
      templatesById: mocks,
      templateOrder: order,
      fieldIdByVariable: fieldIds,
      loading: false,
    });
  },

  bumpDocContentVersion: (templateId) => {
    set((s) => ({
      docContentVersion: {
        ...s.docContentVersion,
        [templateId]: (s.docContentVersion[templateId] ?? 0) + 1,
      },
    }));
  },

  loadTemplate: async (templateId) => {
    set((s) => ({
      loadingTemplateById: { ...s.loadingTemplateById, [templateId]: true },
    }));
    try {
      const { data, error } = await getTemplateV2(templateId);
      if (error || !data) {
        useToastStore.getState().addToast(
          error ?? `Failed to load template ${templateId}`,
          'error',
        );
        return;
      }
      set((s) => _ingestTemplate(s, data));
    } finally {
      set((s) => {
        const next = { ...s.loadingTemplateById };
        delete next[templateId];
        return { loadingTemplateById: next };
      });
    }
  },

  selectTemplate: (templateId) => {
    set({ selectedTemplateId: templateId });
    if (templateId && !get().templatesById[templateId]?.variables.length) {
      void get().loadTemplate(templateId);
    } else if (templateId) {
      // Re-fetch fields lazily so the wizard always opens against the
      // server's view of the spec.
      void get().loadTemplate(templateId);
    }
  },

  uploadAndGenerate: async (file, templateName, role = 'single') => {
    set({ loading: true, error: null });
    const { data, error } = await generateTemplateV2(file, templateName, role);
    set({ loading: false });
    if (error || !data) {
      useToastStore.getState().addToast(
        error ?? 'Failed to generate template from .docx',
        'error',
      );
      return null;
    }
    const tplResponse: TemplateV2Response = {
      id: data.template_id,
      firm_id: null,
      name: data.name,
      config: { role, companions: [] },
      original_doc_url: data.original_doc_url,
      template_doc_url: data.template_doc_url,
      published_at: null,
      has_unpublished_changes: true,
      total_fields: data.template_spec.length,
      configured_fields: data.template_spec.filter(
        (f) => f.params !== null,
      ).length,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      fields: data.template_spec.map((extract) => ({
        // The composer endpoint returns the extracted spec but NOT the
        // persisted field IDs — we have to re-fetch via /templates/{id}
        // to pick up the row ids. For Phase 1 we synthesize stable
        // placeholder ids; selectTemplate triggers a fresh /load which
        // overwrites with the real ids before the user touches the wizard.
        id: `pending-${extract.template_variable}`,
        template_id: data.template_id,
        template_variable: extract.template_variable,
        template_property_marker: extract.template_property_marker,
        template_property_marker_aliases: extract.template_property_marker_aliases,
        template_identifying_text_match: extract.template_identifying_text_match,
        description: extract.description,
        template_index: extract.template_index,
        params: extract.params,
        created_at: new Date().toISOString(),
        updated_at: null,
      })),
    };
    set((s) => _ingestTemplate(s, tplResponse));
    useToastStore.getState().addToast(
      `Created template "${data.name}" with ${data.template_spec.length} variables`,
      'success',
    );
    // Fetch the persisted row so field IDs are real before the wizard opens.
    void get().loadTemplate(data.template_id);
    return data.template_id;
  },

  saveFieldParams: async (templateId, variableName, params) => {
    const fieldId = get().fieldIdByVariable[templateId]?.[variableName];
    if (!fieldId || fieldId.startsWith('pending-')) {
      // Field IDs not yet hydrated from the server — fetch + retry once.
      await get().loadTemplate(templateId);
      const refreshed = get().fieldIdByVariable[templateId]?.[variableName];
      if (!refreshed || refreshed.startsWith('pending-')) {
        useToastStore.getState().addToast(
          `Could not find field "${variableName}" on the server — try refreshing.`,
          'error',
        );
        return;
      }
      return get().saveFieldParams(templateId, variableName, params);
    }

    // 1. OPTIMISTIC patch — apply the new params to the cached row + adapted
    //    mock immediately so the SetupPanel + wizard reflect the change
    //    without waiting for the server round-trip. Capture the prior
    //    field shape so we can revert on failure.
    const tplBefore = get().templatesByIdRaw[templateId];
    const fieldBefore = tplBefore?.fields.find((f) => f.id === fieldId);
    if (!tplBefore || !fieldBefore) {
      useToastStore.getState().addToast(
        `Field "${variableName}" not in local cache — refresh and try again.`,
        'error',
      );
      return;
    }
    set((s) => {
      const tpl = s.templatesByIdRaw[templateId];
      if (!tpl) return {};
      const fields = tpl.fields.map((f) =>
        f.id === fieldId
          ? { ...f, params, updated_at: new Date().toISOString() }
          : f,
      );
      // Bump derived template-level fields so the PublishStep status
      // pill + rail pill flip immediately. Server bumps the matching
      // values on the PATCH (templates_v2.touch_updated_at + the
      // list endpoint's grouped count query) — this just keeps the
      // local view in sync without an extra GET round-trip.
      const newRaw = {
        ...tpl,
        fields,
        updated_at: new Date().toISOString(),
        has_unpublished_changes: true,
        configured_fields: fields.filter((f) => f.params !== null).length,
      };
      return {
        templatesByIdRaw: { ...s.templatesByIdRaw, [templateId]: newRaw },
        templatesById: {
          ...s.templatesById,
          [templateId]: adaptResponseToStudioTemplate(newRaw),
        },
      };
    });

    // 2. Fire the PATCH. On success, overlay the server's authoritative
    //    response (mostly the same shape but with the real updated_at);
    //    on failure, REVERT to the prior field state + show a toast.
    const { data, error } = await patchTemplateFieldV2(
      templateId, fieldId, { params },
    );
    if (error || !data) {
      // REVERT optimistic patch.
      set((s) => {
        const tpl = s.templatesByIdRaw[templateId];
        if (!tpl) return {};
        const fields = tpl.fields.map((f) =>
          f.id === fieldId ? fieldBefore : f,
        );
        const newRaw = { ...tpl, fields };
        return {
          templatesByIdRaw: { ...s.templatesByIdRaw, [templateId]: newRaw },
          templatesById: {
            ...s.templatesById,
            [templateId]: adaptResponseToStudioTemplate(newRaw),
          },
        };
      });
      useToastStore.getState().addToast(
        error ?? `Failed to save "${variableName}" — reverted`,
        'error',
      );
      return;
    }
    // Overlay server-authoritative shape (updated_at, normalized params).
    // Keep derived template-level fields in sync — the field PATCH
    // response only includes the field, but the server has bumped the
    // parent's updated_at + has_unpublished_changes alongside.
    set((s) => {
      const tpl = s.templatesByIdRaw[templateId];
      if (!tpl) return {};
      const fields = tpl.fields.map((f) =>
        f.id === fieldId
          ? { ...f, params: data.params, updated_at: data.updated_at }
          : f,
      );
      const newRaw = {
        ...tpl,
        fields,
        updated_at: data.updated_at ?? tpl.updated_at,
        has_unpublished_changes: true,
        configured_fields: fields.filter((f) => f.params !== null).length,
      };
      return {
        templatesByIdRaw: { ...s.templatesByIdRaw, [templateId]: newRaw },
        templatesById: {
          ...s.templatesById,
          [templateId]: adaptResponseToStudioTemplate(newRaw),
        },
      };
    });
  },

  saveBundlingConfig: async (templateId, config, opts) => {
    const { data, error } = await putTemplateBundlingConfigV2(templateId, { config });
    if (error || !data) {
      const msg = error ?? 'Failed to save bundling config';
      if (!opts?.silent) {
        useToastStore.getState().addToast(msg, 'error');
      }
      return msg;
    }
    set((s) => _ingestTemplate(s, { ...data, fields: s.templatesByIdRaw[templateId]?.fields ?? [] }));
    return null;
  },

  regenerateTemplate: async (templateId, body) => {
    set({ loading: true });
    const { data, error } = await regenerateTemplateV2(templateId, body);
    set({ loading: false });
    if (error || !data) {
      useToastStore.getState().addToast(
        error ?? 'Failed to regenerate template',
        'error',
      );
      return;
    }
    useToastStore.getState().addToast(
      `Regenerated: +${data.inserted.length} / ~${data.updated.length} / -${data.deleted.length}`,
      'success',
    );
    await get().loadTemplate(templateId);
  },

  removeTemplate: async (templateId) => {
    const { data, error } = await deleteTemplateV2(templateId);
    if (error || !data?.deleted) {
      useToastStore.getState().addToast(
        error ?? 'Failed to delete template',
        'error',
      );
      return;
    }
    set((s) => {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [templateId]: _r, ...restRaw } = s.templatesByIdRaw;
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [templateId]: _m, ...restMocks } = s.templatesById;
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { [templateId]: _f, ...restFields } = s.fieldIdByVariable;
      return {
        templatesByIdRaw: restRaw,
        templatesById: restMocks,
        fieldIdByVariable: restFields,
        templateOrder: s.templateOrder.filter((id) => id !== templateId),
        selectedTemplateId:
          s.selectedTemplateId === templateId ? null : s.selectedTemplateId,
      };
    });
  },

  publishTemplate: async (templateId): Promise<PublishResult> => {
    const response = await publishTemplateV2(templateId);
    if (response.data) {
      set((s) => _ingestTemplate(s, response.data!));
      useToastStore.getState().addToast(
        `Published "${response.data.name}" — drafts will use this version.`,
        'success',
      );
      return { ok: true };
    }
    // Validation failure — BE returns 400 with detail.validation_errors,
    // which api.ts pulls into response.validationErrors. Surface as a
    // structured failure so PublishStep can render each error inline.
    const validationErrors = response.validationErrors ?? [];
    const error = response.error ?? 'Publish failed';
    if (validationErrors.length === 0) {
      // Non-validation error (network, 404, etc.) — toast it.
      useToastStore.getState().addToast(error, 'error');
    }
    return { ok: false, validationErrors, error };
  },
}));

// Selector helpers ------------------------------------------------------

export const useStudioV2Templates = (): StudioTemplate[] => {
  const order = useStudioV2Store((s) => s.templateOrder);
  const byId = useStudioV2Store((s) => s.templatesById);
  return order.map((id) => byId[id]).filter(Boolean);
};

export const useStudioV2SelectedTemplate = (): StudioTemplate | null => {
  const id = useStudioV2Store((s) => s.selectedTemplateId);
  const byId = useStudioV2Store((s) => s.templatesById);
  return id ? byId[id] ?? null : null;
};
