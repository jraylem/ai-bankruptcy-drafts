import { create } from 'zustand';
import { studioApi } from '@/services/studio.service';
import {
  clearStudioEntry,
  readStudioEntry,
  writeStudioEntry,
} from '@/hooks/useStudioPersistence';
import { preflightTemplateSpec } from '@/utils/studio/preflight';
import { normalizeSourceParams } from '@/utils/studio/sourceConfig';
import { countIncompleteSlots } from '@/types/studio/bundling';
import type {
  AgentConfig,
  AwaitingInputResult,
  BundleCompanion,
  CaseResponse,
  Connector,
  CreateCaseResult,
  DraftResult,
  DraftTemplateDetail,
  DraftTemplateListItem,
  DryRunResult,
  MergeOperation,
  ReferenceData,
  ReferenceDataCreate,
  ReferenceDataUpdate,
  RegenerateDiff,
  StudioFlowState,
  TemplateBundleRole,
  TemplateVariable,
  UserSelection,
} from '@/types/studio';

const HIDDEN_CONNECTOR_SOURCES = new Set<string>([
  'group_dropdown_from_gmail',
  'group_dropdown_from_court_drive',
]);

// --- Manual case ordering (drag-to-reorder), persisted per browser ---
const CASES_ORDER_KEY = 'cases_manual_order';

const readCasesOrder = (): string[] => {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(CASES_ORDER_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : [];
  } catch {
    return [];
  }
};

const writeCasesOrder = (cases: CaseResponse[]): void => {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CASES_ORDER_KEY, JSON.stringify(cases.map((c) => c.id)));
  } catch {
    /* ignore quota / disabled storage */
  }
};

/** Reorder `cases` to match the saved manual order. Cases absent from the
 *  saved order (newly created or freshly loaded) keep their incoming order
 *  and sit at the top, so new cases stay visible. */
const applyCasesOrder = (cases: CaseResponse[]): CaseResponse[] => {
  const saved = readCasesOrder();
  if (saved.length === 0) return cases;
  const rank = new Map(saved.map((id, i) => [id, i] as const));
  const known: CaseResponse[] = [];
  const unknown: CaseResponse[] = [];
  for (const c of cases) (rank.has(c.id) ? known : unknown).push(c);
  known.sort((a, b) => rank.get(a.id)! - rank.get(b.id)!);
  return [...unknown, ...known];
};

/** Move `draggedId` to sit before/after `targetId` within `cases`. */
const moveCase = (
  cases: CaseResponse[],
  draggedId: string,
  targetId: string,
  position: 'before' | 'after',
): CaseResponse[] => {
  if (draggedId === targetId) return cases;
  const from = cases.findIndex((c) => c.id === draggedId);
  const targetIdx = cases.findIndex((c) => c.id === targetId);
  if (from === -1 || targetIdx === -1) return cases;
  const next = [...cases];
  const [moved] = next.splice(from, 1);
  // Recompute the target index after removal, then offset for before/after.
  const adjustedTarget = next.findIndex((c) => c.id === targetId);
  const insertAt = adjustedTarget + (position === 'after' ? 1 : 0);
  next.splice(insertAt, 0, moved);
  return next;
};

export type ActionErrorKind = 'dry-run' | 'save';

export interface ActionError {
  kind: ActionErrorKind;
  message: string;
  validationErrors?: string[];
}

interface ActionResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
  code?: string;
  /**
   * Populated on `deleteTemplate` 409 when the doomed template is
   * referenced by other parents' bundle_companions. Callers can render
   * a force-delete affordance using this list.
   */
  conflictParents?: import('@/types').ReferencingParent[];
  /**
   * Populated on a successful force-delete to inform the caller which
   * parent templates had their bundle_companions edited.
   */
  cleanedParents?: { template_id: string; name: string; removed_companion_labels: string[] }[];
}

interface PendingCaseDraft {
  /** Synthetic FE-only id of the form `untitled-<uuid>` so it never
   * collides with a real BE-assigned case_id. */
  id: string;
  isUploading: boolean;
}

interface StudioState {
  
  selectedCaseId: string | null;
  selectedTemplateId: string | null;

  cases: CaseResponse[];
  templates: DraftTemplateListItem[];
  connectors: Connector[];
  referenceData: ReferenceData[];

  templateSpec: TemplateVariable[];
  agentConfig: AgentConfig | null;
  bundleRole: TemplateBundleRole;
  bundleCompanions: BundleCompanion[];
  isBundlingDirty: boolean;
  dryRunResult: DryRunResult | null;
  dryRunAwaiting: AwaitingInputResult | null;
  draftResult: DraftResult | null;
  draftAwaiting: AwaitingInputResult | null;

  // Saved baselines used for revert-aware dirty tracking. Snapshotted
  // when a template hydrates and after every successful save; the dirty
  // evaluators below compare current state against these to flip the
  // dirty flags back to false when the user reverts a change.
  savedTemplateSpec: TemplateVariable[];
  savedBundleRole: TemplateBundleRole;
  savedBundleCompanions: BundleCompanion[];

  flowState: StudioFlowState;
  isDirty: boolean;

  // Diff returned by the BE after a successful regenerate (baseline vs.
  // new spec). Null on initial generate (no baseline) and after a manual
  // clear / template switch. Read by RegenerateTemplateModal to render
  // the diff summary post-completion.
  regenerateDiff: RegenerateDiff | null;

  isLoadingCases: boolean;
  isLoadingTemplates: boolean;
  isUploadingTemplate: boolean;
  isCreatingCase: boolean;
  isSaving: boolean;
  /**
   * Timestamp of the last successful `saveConfiguration`. Drives the
   * emerald "Configuration saved" banner on the studio page; cleared
   * after a few seconds OR as soon as the user edits something else.
   */
  justSavedAt: number | null;
  clearJustSavedAt: () => void;
  isDryRunning: boolean;
  isDrafting: boolean;
  error: string | null;

  // Fresh-signed petition PDF URL for the currently selected case. Reset
  // synchronously on every selectCase() so the iframe never briefly shows
  // the previous case's PDF; refetched lazily via getCasePetitionUrl.
  /** Re-signs the petition URL for one case (used as a fallback when the
   * pre-signed URL baked into the cases list page has expired) and
   * patches the cases array with the fresh URL. Returns the new URL or
   * null on failure. */
  refreshCasePetitionUrl: (caseId: string) => Promise<string | null>;

  actionError: ActionError | null;

  templateDocUrl: string | null;
  originalDocUrl: string | null;

  selectCase: (caseId: string | null) => void;
  selectTemplate: (templateId: string) => Promise<void>;
  resetToNew: () => void;

  loadCases: () => Promise<void>;
  loadMoreCases: () => Promise<void>;
  /** Drag-to-reorder a case relative to a target; persists order per browser. */
  reorderCases: (draggedId: string, targetId: string, position: 'before' | 'after') => void;
  /** Move a (possibly new) case to the top of the list and persist the order. */
  promoteCaseToTop: (c: CaseResponse) => void;
  casesHasMore: boolean;
  casesTotal: number;
  isLoadingMoreCases: boolean;
  refreshCase: (caseId: string) => Promise<ActionResult<CaseResponse>>;
  loadTemplates: () => Promise<void>;
  loadConnectors: () => Promise<void>;
  loadReferenceData: () => Promise<void>;

  createCase: (petition: File) => Promise<ActionResult<CreateCaseResult>>;

  // Optimistic "+ New Case" flow used by Draft v2's /new route. The
  // sidebar renders `pendingCase` as a dashed "Untitled" row before
  // (and during) the upload; on success the placeholder is dropped
  // and the real case prepends to `cases`.
  pendingCase: PendingCaseDraft | null;
  startNewCase: () => string;
  submitNewCase: (file: File) => Promise<ActionResult<CreateCaseResult>>;
  submitNewCaseByCaseNumber: (caseNumber: string) => Promise<ActionResult<CreateCaseResult>>;
  cancelNewCase: () => void;
  uploadTemplate: (
    templateName: string,
    document: File,
  ) => Promise<ActionResult<string>>;
  regenerateTemplate: (
    ignoredTexts: string[],
    merges: MergeOperation[],
    regenerationInstruction?: string | null,
  ) => Promise<ActionResult<string>>;

  updateVariable: (propertyName: string, updates: Partial<TemplateVariable>) => void;
  setBundleRole: (role: TemplateBundleRole) => void;
  setBundleCompanions: (companions: BundleCompanion[]) => void;
  saveConfiguration: () => Promise<ActionResult>;
  runDryRun: (
    bundlePicks?: Record<string, string> | null,
  ) => Promise<ActionResult>;
  resumeDryRun: (
    picks: Record<string, UserSelection>,
  ) => Promise<ActionResult>;
  dismissDryRunAwaiting: () => void;
  runDraft: (
    bundlePicks?: Record<string, string> | null,
  ) => Promise<ActionResult<DraftResult>>;
  resumeDraft: (
    picks: Record<string, UserSelection>,
  ) => Promise<ActionResult>;
  dismissDraftAwaiting: () => void;
  dismissDraftResult: () => void;
  clearRegenerateDiff: () => void;

  renameTemplate: (templateId: string, name: string) => Promise<ActionResult<DraftTemplateListItem>>;
  deleteTemplate: (templateId: string, force?: boolean) => Promise<ActionResult>;

  refreshReferenceData: (shortCode: string) => Promise<ActionResult<ReferenceData>>;
  createReferenceData: (payload: ReferenceDataCreate) => Promise<ActionResult<ReferenceData>>;
  updateReferenceData: (
    shortCode: string,
    payload: ReferenceDataUpdate,
  ) => Promise<ActionResult<ReferenceData>>;
  deleteReferenceData: (shortCode: string) => Promise<ActionResult>;
  retryLastAction: () => Promise<ActionResult>;
  clearActionError: () => void;
  dismissDryRunResult: () => void;

  clearError: () => void;
}

const applyPersistedOverlay = <T extends { selectedTemplateId: string | null }>(
  base: T,
  templateId: string,
): T => {
  const persisted = readStudioEntry(templateId);
  if (!persisted) return base;
  return {
    ...base,
    templateSpec: persisted.templateSpec,
    dryRunResult: persisted.dryRunResult,
    flowState: persisted.flowState,
    isDirty: persisted.isDirty,
  };
};

/**
 * Repair any source_params shapes that drifted from their source (e.g. a
 * variable flipped to `inherit_from_parent` while keeping the previous
 * gmail-shape `{subject_query, body_query, scope_to_current_case}`). The BE
 * rejects those at dry-run/draft entry, so we normalize on read.
 */
const normalizeTemplateSpec = (spec: TemplateVariable[]): TemplateVariable[] =>
  spec.map((v) => {
    if (!v.source) return v;
    const normalized = normalizeSourceParams(v.source, v.source_params);
    if (normalized === v.source_params) return v;
    return { ...v, source_params: normalized };
  });

const hydrateFromTemplateDetail = (detail: DraftTemplateDetail) => {
  const templateSpec = normalizeTemplateSpec(detail.template_spec ?? []);
  const bundleRole = (detail.bundle_role ?? 'standalone') as TemplateBundleRole;
  const bundleCompanions = detail.bundle_companions ?? [];
  return {
    selectedTemplateId: detail.id,
    templateSpec,
    savedTemplateSpec: templateSpec,
    agentConfig: detail.agent_config,
    bundleRole,
    savedBundleRole: bundleRole,
    bundleCompanions,
    savedBundleCompanions: bundleCompanions,
    isBundlingDirty: false,
    templateDocUrl: detail.template_doc_url,
    originalDocUrl: detail.original_doc_url,
    flowState: (detail.agent_config ? 'persisted' : 'generated') as StudioFlowState,
    isDirty: false,
    regenerateDiff: null,
    dryRunResult: null,
    dryRunAwaiting: null,
    draftResult: null,
    draftAwaiting: null,
  };
};

/**
 * Stable deep-equality check for the small JSON-shaped structures we
 * snapshot for dirty-tracking (template_spec arrays, bundle_companions
 * arrays, scalar role enums). JSON.stringify is sufficient because:
 *   - These shapes contain only objects, arrays, strings, numbers,
 *     booleans, and null — no Dates / Maps / Sets / cycles.
 *   - Key order is preserved by V8/JavaScriptCore for plain objects, so
 *     stringify is deterministic for our snapshot vs. user-edited copies
 *     (both originate from the same hydration path).
 *
 * Used by the dirty-evaluators below to flip `isDirty` / `isBundlingDirty`
 * back to `false` when the user reverts a change to its saved state.
 */
const isJsonEqual = (a: unknown, b: unknown): boolean =>
  JSON.stringify(a) === JSON.stringify(b);

const emptyTemplateState = {
  selectedTemplateId: null,
  templateSpec: [],
  savedTemplateSpec: [] as TemplateVariable[],
  agentConfig: null,
  bundleRole: 'standalone' as TemplateBundleRole,
  savedBundleRole: 'standalone' as TemplateBundleRole,
  bundleCompanions: [] as BundleCompanion[],
  savedBundleCompanions: [] as BundleCompanion[],
  isBundlingDirty: false,
  regenerateDiff: null,
  dryRunResult: null,
  dryRunAwaiting: null,
  draftResult: null,
  draftAwaiting: null,
  templateDocUrl: null,
  originalDocUrl: null,
  flowState: 'new' as StudioFlowState,
  isDirty: false,
};

export const useStudioStore = create<StudioState>((set, get) => ({
  selectedCaseId: null,
  selectedTemplateId: null,

  cases: [],
  casesHasMore: false,
  casesTotal: 0,
  isLoadingMoreCases: false,
  templates: [],
  connectors: [],
  referenceData: [],

  templateSpec: [],
  savedTemplateSpec: [],
  agentConfig: null,
  bundleRole: 'standalone',
  savedBundleRole: 'standalone',
  bundleCompanions: [],
  savedBundleCompanions: [],
  isBundlingDirty: false,
  regenerateDiff: null,
  dryRunResult: null,
  dryRunAwaiting: null,
  draftResult: null,
  draftAwaiting: null,

  flowState: 'new',
  isDirty: false,

  isLoadingCases: false,
  isLoadingTemplates: false,
  isUploadingTemplate: false,
  isCreatingCase: false,
  isSaving: false,
  justSavedAt: null,
  clearJustSavedAt: () => set({ justSavedAt: null }),
  isDryRunning: false,
  isDrafting: false,
  error: null,
  actionError: null,

  templateDocUrl: null,
  originalDocUrl: null,

  pendingCase: null,

  refreshCasePetitionUrl: async (caseId: string) => {
    // Fallback path for an expired pre-signed URL (cases-list page
    // signs URLs with a 1h TTL; if a user idles past that, the next
    // PDF load will 403 and the page kicks this off). Patches the
    // single case row in `cases` so the new URL is observable to any
    // other consumer that reads from the list.
    const result = await studioApi.getCasePetitionUrl(caseId);
    const fresh = result.data?.petition_pdf_url ?? null;
    if (!fresh) return null;
    set((state) => ({
      cases: state.cases.map((c) =>
        c.id === caseId ? { ...c, petition_pdf_url: fresh } : c,
      ),
    }));
    return fresh;
  },

  selectCase: (caseId) => set({ selectedCaseId: caseId }),

  selectTemplate: async (templateId) => {
    
    const { templates } = get();
    const detail = templates.find((t) => t.id === templateId);
    if (detail) {
      set(applyPersistedOverlay(hydrateFromTemplateDetail(detail), templateId));
      return;
    }
    
    const result = await studioApi.listTemplates();
    if (result.data) {
      set({ templates: result.data });
      const found = result.data.find((t) => t.id === templateId);
      if (found) {
        set(applyPersistedOverlay(hydrateFromTemplateDetail(found), templateId));
        return;
      }
    }
    
    set(emptyTemplateState);
  },

  resetToNew: () => set(emptyTemplateState),

  loadCases: async () => {
    set({ isLoadingCases: true });
    const result = await studioApi.listCases({ limit: 50, offset: 0 });
    if (!result.data) {
      set({ isLoadingCases: false, error: result.error ?? null });
      return;
    }
    set({
      isLoadingCases: false,
      cases: applyCasesOrder(result.data.cases),
      casesTotal: result.data.total,
      casesHasMore: result.data.has_more,
      error: null,
    });
  },

  loadMoreCases: async () => {
    const { cases, casesHasMore, isLoadingMoreCases } = get();
    if (!casesHasMore || isLoadingMoreCases) return;
    set({ isLoadingMoreCases: true });
    const result = await studioApi.listCases({ limit: 50, offset: cases.length });
    if (!result.data) {
      set({ isLoadingMoreCases: false, error: result.error ?? null });
      return;
    }
    // Dedupe defensively in case a case was added between pages.
    const seen = new Set(cases.map((c) => c.id));
    const additions = result.data.cases.filter((c) => !seen.has(c.id));
    set((state) => ({
      isLoadingMoreCases: false,
      cases: [...state.cases, ...additions],
      casesTotal: result.data!.total,
      casesHasMore: result.data!.has_more,
      error: null,
    }));
  },

  reorderCases: (draggedId, targetId, position) => {
    set((state) => {
      const next = moveCase(state.cases, draggedId, targetId, position);
      if (next === state.cases) return {};
      writeCasesOrder(next);
      return { cases: next };
    });
  },

  promoteCaseToTop: (c) => {
    set((state) => {
      const rest = state.cases.filter((x) => x.id !== c.id);
      const next = [c, ...rest];
      writeCasesOrder(next);
      // Select it too, so the case page opens this case immediately and the
      // store→URL effect doesn't race the nav back to the previous selection.
      return { cases: next, selectedCaseId: c.id };
    });
  },

  refreshCase: async (caseId) => {
    const result = await studioApi.getCase(caseId);
    if (!result.data) {
      return { success: false, error: result.error ?? 'Failed to refresh case' };
    }
    const fresh = result.data;
    set((state) => ({
      cases: state.cases.map((c) => (c.id === fresh.id ? fresh : c)),
    }));
    return { success: true, data: fresh };
  },

  loadTemplates: async () => {
    set({ isLoadingTemplates: true });
    const result = await studioApi.listTemplates();
    set({
      isLoadingTemplates: false,
      templates: result.data ?? [],
      error: null,
    });
  },

  loadConnectors: async () => {
    const result = await studioApi.listConnectors();
    if (result.data) {
      set({
        connectors: result.data.filter(
          (c) => !HIDDEN_CONNECTOR_SOURCES.has(c.source),
        ),
      });
    }
  },

  loadReferenceData: async () => {
    const result = await studioApi.listReferenceData();
    if (result.data) set({ referenceData: result.data });
  },

  createCase: async (petition) => {
    set({ isCreatingCase: true, error: null });
    const result = await studioApi.createCase(petition);
    set({ isCreatingCase: false });

    if (!result.data) {
      const error = result.error ?? 'Failed to create case';
      set({ error });
      return { success: false, error };
    }

    const created = result.data.case;
    set((state) => ({
      cases: [created, ...state.cases],
      selectedCaseId: created.id,
    }));
    return { success: true, data: result.data };
  },

  startNewCase: () => {
    const id = `untitled-${Math.random().toString(36).slice(2, 10)}`;
    set({
      pendingCase: { id, isUploading: false },
      selectedCaseId: id,
    });
    return id;
  },

  submitNewCase: async (file) => {
    const { pendingCase } = get();
    set({
      pendingCase: pendingCase
        ? { ...pendingCase, isUploading: true }
        : { id: `untitled-${Math.random().toString(36).slice(2, 10)}`, isUploading: true },
      isCreatingCase: true,
      error: null,
    });
    const result = await studioApi.createCase(file);
    if (!result.data) {
      const error = result.error ?? 'Failed to create case';
      set((state) => ({
        // Keep the placeholder mounted; just clear the uploading flag so
        // the user can retry without losing their slot in the sidebar.
        pendingCase: state.pendingCase ? { ...state.pendingCase, isUploading: false } : null,
        isCreatingCase: false,
        error,
      }));
      return { success: false, error };
    }

    const created = result.data.case;
    set((state) => ({
      pendingCase: null,
      cases: [created, ...state.cases],
      selectedCaseId: created.id,
      isCreatingCase: false,
    }));
    return { success: true, data: result.data };
  },

  submitNewCaseByCaseNumber: async (caseNumber) => {
    const { pendingCase } = get();
    set({
      pendingCase: pendingCase
        ? { ...pendingCase, isUploading: true }
        : { id: `untitled-${Math.random().toString(36).slice(2, 10)}`, isUploading: true },
      isCreatingCase: true,
      error: null,
    });
    const result = await studioApi.createCaseByCaseNumber(caseNumber);
    if (!result.data) {
      const error = result.error ?? 'Failed to extract petition';
      set((state) => ({
        pendingCase: state.pendingCase ? { ...state.pendingCase, isUploading: false } : null,
        isCreatingCase: false,
        error,
      }));
      return { success: false, error };
    }

    const created = result.data.case;
    set((state) => ({
      pendingCase: null,
      cases: [created, ...state.cases],
      selectedCaseId: created.id,
      isCreatingCase: false,
    }));
    return { success: true, data: result.data };
  },

  cancelNewCase: () => {
    const { pendingCase, selectedCaseId } = get();
    if (!pendingCase) return;
    set({
      pendingCase: null,
      // Only clear the selection if it was pointing at the placeholder —
      // otherwise the user had already moved on to a real case.
      selectedCaseId: selectedCaseId === pendingCase.id ? null : selectedCaseId,
    });
  },

  uploadTemplate: async (templateName, document) => {
    set({ isUploadingTemplate: true, error: null });
    const result = await studioApi.generateTemplate(templateName, document);
    set({ isUploadingTemplate: false });

    if (!result.data) {
      const error = result.error ?? 'Failed to upload template';
      set({ error });
      return { success: false, error };
    }

    const generated = result.data;
    const generatedSpec = normalizeTemplateSpec(generated.template_spec);
    const newTemplate: DraftTemplateListItem = {
      id: generated.template_id,
      name: generated.template_name,
      original_doc_url: generated.original_doc_url,
      template_doc_url: generated.template_doc_url,
      template_spec: generatedSpec,
      agent_config: null,
      bundle_role: 'standalone',
      bundle_companions: null,
      created_at: new Date().toISOString(),
      is_active: true,
    };
    set((state: StudioState) => ({
      selectedTemplateId: generated.template_id,
      templateSpec: generatedSpec,
      savedTemplateSpec: generatedSpec,
      templateDocUrl: generated.template_doc_url,
      originalDocUrl: generated.original_doc_url,
      agentConfig: null,
      dryRunResult: null,
      flowState: 'generated',
      isDirty: false,
      templates: state.templates.some((t) => t.id === generated.template_id)
        ? state.templates.map((t) => (t.id === generated.template_id ? newTemplate : t))
        : [...state.templates, newTemplate],
    }));
    return { success: true, data: generated.template_id };
  },

  regenerateTemplate: async (ignoredTexts, merges, regenerationInstruction = null) => {
    const { selectedTemplateId } = get();
    if (!selectedTemplateId) {
      const error = 'No template selected';
      set({ error });
      return { success: false, error };
    }
    set({ isUploadingTemplate: true, error: null });
    const result = await studioApi.regenerateTemplate(
      selectedTemplateId,
      ignoredTexts,
      merges,
      regenerationInstruction,
    );
    set({ isUploadingTemplate: false });

    if (!result.data) {
      const error = result.error ?? 'Failed to regenerate template';
      set({ error });
      return { success: false, error };
    }

    const regenerated = result.data;
    const regeneratedSpec = normalizeTemplateSpec(regenerated.template_spec);

    clearStudioEntry(selectedTemplateId);
    set((state: StudioState) => ({
      templateSpec: regeneratedSpec,
      savedTemplateSpec: regeneratedSpec,
      templateDocUrl: regenerated.template_doc_url,
      originalDocUrl: regenerated.original_doc_url,
      agentConfig: null,
      dryRunResult: null,
      dryRunAwaiting: null,
      flowState: 'generated',
      isDirty: false,
      regenerateDiff: regenerated.diff ?? null,
      templates: state.templates.map((t) =>
        t.id === regenerated.template_id
          ? {
              ...t,
              template_spec: regenerated.template_spec,
              template_doc_url: regenerated.template_doc_url,
              original_doc_url: regenerated.original_doc_url,
              agent_config: null,
            }
          : t,
      ),
    }));
    void get().loadTemplates();
    return { success: true, data: regenerated.template_id };
  },

  clearRegenerateDiff: (): void => set({ regenerateDiff: null }),

  updateVariable: (propertyName, updates) =>
    set((state) => {
      const nextSpec = state.templateSpec.map((v) =>
        v.template_variable === propertyName ? { ...v, ...updates } : v,
      );
      const nextDirty = !isJsonEqual(nextSpec, state.savedTemplateSpec);
      const next = {
        templateSpec: nextSpec,
        isDirty: nextDirty,
        flowState: (state.flowState === 'generated' ? 'configuring' : state.flowState) as StudioFlowState,
        // Clear the saved-banner the moment the user starts editing again.
        justSavedAt: nextDirty ? null : state.justSavedAt,
      };
      writeStudioEntry(state.selectedTemplateId, {
        templateSpec: next.templateSpec,
        dryRunResult: state.dryRunResult,
        flowState: next.flowState,
        isDirty: next.isDirty,
      });
      return next;
    }),

  setBundleRole: (role) =>
    set((state) => {
      // Keep `bundleCompanions` in memory across role flips so toggling
      // parent → child_only → parent doesn't lose the user's authored
      // companion list. The save path (`saveBundlingConfig`) sends NULL
      // for companions when role !== 'parent', and the bundling engine
      // ignores companions for non-parent roles, so retaining them here
      // is purely a UX win — no risk of leaking invalid state to the BE.
      const dirty =
        role !== state.savedBundleRole ||
        !isJsonEqual(state.bundleCompanions, state.savedBundleCompanions);
      return {
        bundleRole: role,
        isBundlingDirty: dirty,
        justSavedAt: dirty ? null : state.justSavedAt,
      };
    }),

  setBundleCompanions: (companions) =>
    set((state) => {
      const dirty =
        state.bundleRole !== state.savedBundleRole ||
        !isJsonEqual(companions, state.savedBundleCompanions);
      return {
        bundleCompanions: companions,
        isBundlingDirty: dirty,
        justSavedAt: dirty ? null : state.justSavedAt,
      };
    }),

  saveConfiguration: async () => {
    const {
      selectedTemplateId,
      templateSpec,
      bundleRole,
      bundleCompanions,
      isBundlingDirty,
      templates,
    } = get();
    if (!selectedTemplateId) {
      const error = 'No template selected';
      set({ actionError: { kind: 'save', message: error } });
      return { success: false, error };
    }

    // Strict gate: don't even hit the BE if any companion slot is incomplete.
    // Mirrors the BE's BUNDLE_SLOTS_INCOMPLETE check so the user gets instant
    // feedback instead of a round-trip 400. We deliberately DO NOT set
    // `actionError` here — that field drives the template-spec workspace's
    // red card, but slot-incompleteness is a BUNDLING concern and would be
    // misplaced there. The BundleCompanionsEditor already renders an inline
    // amber banner with the count, and the page-level toast covers the
    // transient signal.
    if (bundleRole === 'parent') {
      const requiredSlotsByChild = (childId: string): string[] => {
        const child = templates.find((t) => t.id === childId);
        if (!child?.template_spec) return [];
        return child.template_spec
          .filter((v) => v.source === 'inherit_from_parent')
          .map((v) => v.template_variable);
      };
      const missing = countIncompleteSlots(bundleCompanions, requiredSlotsByChild);
      if (missing > 0) {
        const message = `${missing} bundle slot${missing === 1 ? '' : 's'} need configuration before saving.`;
        return { success: false, error: message, code: 'BUNDLE_SLOTS_INCOMPLETE' };
      }
    }

    set({ isSaving: true, actionError: null });
    const composeResult = await studioApi.composeAgentConfig(selectedTemplateId, templateSpec);

    if (!composeResult.data) {
      set({ isSaving: false });
      const message = composeResult.error ?? 'Failed to save configuration';
      set({
        actionError: {
          kind: 'save',
          message,
          validationErrors: composeResult.validationErrors,
        },
      });
      return { success: false, error: message };
    }

    // Bundling-config save is gated on isBundlingDirty — no point hitting
    // the BE if the parent didn't change role / companions.
    if (isBundlingDirty) {
      const bundlingResult = await studioApi.saveBundlingConfig(
        selectedTemplateId,
        bundleRole,
        bundleRole === 'parent' ? bundleCompanions : null,
      );
      if (!bundlingResult.data) {
        set({ isSaving: false });
        const message = bundlingResult.error ?? 'Failed to save bundling settings';
        set({
          actionError: {
            kind: 'save',
            message,
            validationErrors: bundlingResult.validationErrors,
          },
        });
        return { success: false, error: message };
      }
    }

    set({
      isSaving: false,
      agentConfig: composeResult.data,
      isDirty: false,
      isBundlingDirty: false,
      flowState: 'persisted',
      // Drives the emerald "Configuration saved" banner on the studio page.
      // Cleared automatically (by the page's setTimeout) or by any
      // dirty-flipping setter below.
      justSavedAt: Date.now(),
      // Snapshot the just-saved values as the new baseline so subsequent
      // edits compare against what's actually persisted; reverting back
      // to these exact values flips dirty back to false.
      savedTemplateSpec: templateSpec,
      savedBundleRole: bundleRole,
      savedBundleCompanions: bundleRole === 'parent' ? bundleCompanions : [],
    });

    clearStudioEntry(selectedTemplateId);
    void get().loadTemplates();
    return { success: true };
  },

  runDryRun: async (bundlePicks?: Record<string, string> | null) => {
    const {
      templateSpec,
      selectedTemplateId,
      selectedCaseId,
      referenceData,
      bundleRole,
      bundleCompanions,
    } = get();
    if (!selectedTemplateId) {
      const message = 'No template selected';
      set({ actionError: { kind: 'dry-run', message } });
      return { success: false, error: message };
    }
    if (!selectedCaseId) {
      const message = 'No case selected — pick one from the sidebar before running';
      set({ actionError: { kind: 'dry-run', message } });
      return { success: false, error: message };
    }

    const normalizedSpec = normalizeTemplateSpec(templateSpec);
    if (!isJsonEqual(normalizedSpec, templateSpec)) {
      set((state) => ({
        templateSpec: normalizedSpec,
        isDirty: !isJsonEqual(normalizedSpec, state.savedTemplateSpec),
      }));
    }

    const preflightErrors = preflightTemplateSpec(normalizedSpec, referenceData);
    if (preflightErrors.length > 0) {
      set({
        actionError: {
          kind: 'dry-run',
          message: `Cannot run dry run — ${preflightErrors.length} variable(s) need attention`,
          validationErrors: preflightErrors,
        },
      });
      return { success: false, error: preflightErrors[0] };
    }

    set({ isDryRunning: true, actionError: null });
    const result = await studioApi.dryRun(
      selectedTemplateId,
      normalizedSpec,
      selectedCaseId,
      bundlePicks ?? null,
      bundleRole,
      bundleRole === 'parent' ? bundleCompanions : null,
    );
    set({ isDryRunning: false });

    if (!result.data) {
      const message = result.error ?? 'Dry run failed';
      set({
        actionError: {
          kind: 'dry-run',
          message,
          validationErrors: result.validationErrors,
        },
      });
      return { success: false, error: message };
    }

    if (result.data.status === 'awaiting_input') {
      
      set({ dryRunAwaiting: result.data });
      return { success: true };
    }

    set({
      dryRunResult: result.data,
      dryRunAwaiting: null,
      // Clear any prior draftResult so the dry-run's outputs aren't
      // shadowed downstream (TemplatePreview + VariablesWorkspace use
      // `draftResult ?? dryRunResult` as the source — stale draftResult
      // would mask the new dry-run's docx + AI reasoning).
      draftResult: null,
      draftAwaiting: null,
      flowState: 'verified',
    });
    const { templateSpec: specAfter, isDirty: dirtyAfter } = get();
    writeStudioEntry(selectedTemplateId, {
      templateSpec: specAfter,
      dryRunResult: result.data,
      flowState: 'verified',
      isDirty: dirtyAfter,
    });
    return { success: true };
  },

  resumeDryRun: async (picks) => {
    const {
      dryRunAwaiting,
      templateSpec,
      selectedTemplateId,
      bundleRole,
      bundleCompanions,
    } = get();
    if (!dryRunAwaiting) {
      const message = 'No paused dry-run to resume';
      set({ actionError: { kind: 'dry-run', message } });
      return { success: false, error: message };
    }

    set({ isDryRunning: true, actionError: null });

    const result = await studioApi.dryRunResume(
      dryRunAwaiting.template_id,
      dryRunAwaiting.template_spec ?? templateSpec,
      dryRunAwaiting.case_id,
      dryRunAwaiting.resolved_values,
      picks,
      dryRunAwaiting.bundle_picks ?? null,
      bundleRole,
      bundleRole === 'parent' ? bundleCompanions : null,
    );
    set({ isDryRunning: false });

    if (!result.data) {
      const message = result.error ?? 'Dry run resume failed';
      set({
        actionError: {
          kind: 'dry-run',
          message,
          validationErrors: result.validationErrors,
        },
      });
      return { success: false, error: message };
    }

    if (result.data.status === 'awaiting_input') {
      
      set({ dryRunAwaiting: result.data });
      return { success: true };
    }

    set({
      dryRunResult: result.data,
      dryRunAwaiting: null,
      // Same shadowing fix as runDryRun — clear any prior draftResult
      // so the resumed dry-run's outputs render.
      draftResult: null,
      draftAwaiting: null,
      flowState: 'verified',
    });
    if (selectedTemplateId) {
      const { templateSpec: specAfter, isDirty: dirtyAfter } = get();
      writeStudioEntry(selectedTemplateId, {
        templateSpec: specAfter,
        dryRunResult: result.data,
        flowState: 'verified',
        isDirty: dirtyAfter,
      });
    }
    return { success: true };
  },

  dismissDryRunAwaiting: () => set({ dryRunAwaiting: null }),

  runDraft: async (
    bundlePicks?: Record<string, string> | null,
  ): Promise<ActionResult<DraftResult>> => {
    const { selectedTemplateId, selectedCaseId, agentConfig } = get();
    if (!selectedTemplateId) {
      return { success: false, error: 'No template selected' };
    }
    if (!selectedCaseId) {
      return { success: false, error: 'No case selected — pick one from the sidebar before drafting' };
    }
    if (!agentConfig) {
      return { success: false, error: 'Template has no committed agent config — save configuration first' };
    }

    set({ isDrafting: true });
    const result = await studioApi.draft(
      selectedTemplateId,
      selectedCaseId,
      bundlePicks ?? null,
    );
    set({ isDrafting: false });

    if (!result.data) {
      return { success: false, error: result.error ?? 'Draft failed' };
    }

    if (result.data.status === 'awaiting_input') {
      
      set({ draftAwaiting: result.data });
      return { success: true };
    }

    set({
      draftResult: result.data,
      draftAwaiting: null,
      // Clear prior dryRunResult so this draft's outputs aren't shadowed
      // by stale dry-run data downstream (TemplatePreview + workspace
      // use the most-recent-of-the-two; explicit clear keeps it clean).
      dryRunResult: null,
      dryRunAwaiting: null,
    });
    return { success: true, data: result.data };
  },

  resumeDraft: async (picks) => {
    const { draftAwaiting } = get();
    if (!draftAwaiting) {
      return { success: false, error: 'No paused draft to resume' };
    }

    set({ isDrafting: true });
    
    const result = await studioApi.draftResume(
      draftAwaiting.template_id,
      draftAwaiting.case_id,
      draftAwaiting.resolved_values,
      picks,
      draftAwaiting.bundle_picks ?? null,
    );
    set({ isDrafting: false });

    if (!result.data) {
      return { success: false, error: result.error ?? 'Draft resume failed' };
    }

    if (result.data.status === 'awaiting_input') {
      
      set({ draftAwaiting: result.data });
      return { success: true };
    }

    set({
      draftResult: result.data,
      draftAwaiting: null,
      // Clear prior dryRunResult so this draft's outputs aren't shadowed
      // by stale dry-run data downstream (TemplatePreview + workspace
      // use the most-recent-of-the-two; explicit clear keeps it clean).
      dryRunResult: null,
      dryRunAwaiting: null,
    });
    return { success: true };
  },

  dismissDraftAwaiting: (): void => set({ draftAwaiting: null }),

  dismissDraftResult: (): void => set({ draftResult: null }),

  renameTemplate: async (
    templateId: string,
    name: string,
  ): Promise<ActionResult<DraftTemplateListItem>> => {
    const result = await studioApi.renameTemplate(templateId, name);
    if (!result.data) {
      return { success: false, error: result.error ?? 'Failed to rename template' };
    }
    set((state: StudioState) => ({
      templates: state.templates.map((t: DraftTemplateListItem): DraftTemplateListItem =>
        t.id === templateId ? result.data! : t,
      ),
    }));
    void get().loadTemplates();
    return { success: true, data: result.data };
  },

  deleteTemplate: async (
    templateId: string,
    force = false,
  ): Promise<ActionResult> => {
    const result = await studioApi.deleteTemplate(templateId, force);
    if (!result.data) {
      // 409 conflict path — propagate the parents list so the UI can
      // offer a force-delete affordance.
      if (result.conflictParents && result.conflictParents.length > 0) {
        return {
          success: false,
          error: result.error ?? 'Template is referenced by other templates',
          conflictParents: result.conflictParents,
        };
      }
      return { success: false, error: result.error ?? 'Failed to delete template' };
    }
    clearStudioEntry(templateId);
    const cleanedParents = result.data.cleaned_parents ?? [];
    set((state: StudioState) => ({
      templates: state.templates.filter((t: DraftTemplateListItem) => t.id !== templateId),
      ...(state.selectedTemplateId === templateId ? emptyTemplateState : {}),
    }));
    // When force-delete cascade-cleaned other parents, their
    // bundle_companions (and possibly bundle_role — the BE auto-demotes
    // to 'standalone' when the last companion is pruned) just changed.
    // Refetch so the templates list reflects the new state instead of
    // showing stale "Parent" badges. Skipped on plain delete since
    // nothing else changed.
    if (cleanedParents.length > 0) {
      void get().loadTemplates();
    }
    return {
      success: true,
      cleanedParents,
    };
  },

  refreshReferenceData: async (shortCode: string): Promise<ActionResult<ReferenceData>> => {
    const result = await studioApi.getReferenceData(shortCode);
    if (!result.data) {
      return { success: false, error: result.error ?? 'Failed to refresh constant' };
    }
    const fresh = result.data;
    set((state: StudioState) => ({
      referenceData: state.referenceData.map((r: ReferenceData): ReferenceData =>
        r.short_code === fresh.short_code ? fresh : r,
      ),
    }));
    return { success: true, data: fresh };
  },

  createReferenceData: async (payload: ReferenceDataCreate): Promise<ActionResult<ReferenceData>> => {
    const result = await studioApi.createReferenceData(payload);
    if (!result.data) {
      return { success: false, error: result.error ?? 'Failed to create constant' };
    }
    set((state: StudioState) => ({ referenceData: [...state.referenceData, result.data!] }));
    return { success: true, data: result.data };
  },

  updateReferenceData: async (
    shortCode: string,
    payload: ReferenceDataUpdate,
  ): Promise<ActionResult<ReferenceData>> => {
    const result = await studioApi.updateReferenceData(shortCode, payload);
    if (!result.data) {
      return { success: false, error: result.error ?? 'Failed to update constant' };
    }
    set((state: StudioState) => ({
      referenceData: state.referenceData.map((r: ReferenceData): ReferenceData =>
        r.short_code === shortCode ? result.data! : r,
      ),
    }));
    return { success: true, data: result.data };
  },

  deleteReferenceData: async (shortCode: string): Promise<ActionResult> => {
    const result = await studioApi.deleteReferenceData(shortCode);
    if (result.error) {
      return { success: false, error: result.error };
    }
    set((state: StudioState) => ({
      referenceData: state.referenceData.filter(
        (r: ReferenceData): boolean => r.short_code !== shortCode,
      ),
    }));
    return { success: true };
  },

  retryLastAction: async () => {
    const { actionError, runDryRun, saveConfiguration } = get();
    if (!actionError) return { success: false, error: 'Nothing to retry' };
    if (actionError.kind === 'dry-run') return runDryRun();
    return saveConfiguration();
  },

  clearActionError: () => set({ actionError: null }),

  dismissDryRunResult: () => {
    const { selectedTemplateId, templateSpec, flowState, isDirty } = get();
    writeStudioEntry(selectedTemplateId, {
      templateSpec,
      dryRunResult: null,
      flowState,
      isDirty,
    });
    set({ dryRunResult: null });
  },

  clearError: () => set({ error: null }),
}));
