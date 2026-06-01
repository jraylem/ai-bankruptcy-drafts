import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useToastStore } from '@/stores/useToastStore';
import {
  useStudioV2SelectedTemplate,
  useStudioV2Store,
  useStudioV2Templates,
} from '@/stores/useStudioV2Store';
import { useStudioV2ComposerTasksStore } from '@/stores/useStudioV2ComposerTasksStore';
import {
  useStudioV2DryRunTasksStore,
  selectDryRunTaskById,
} from '@/stores/useStudioV2DryRunTasksStore';
import {
  startStudioV2ComposerEventStream,
  stopStudioV2ComposerEventStream,
} from '@/services/studioV2ComposerAsyncEvents.service';
import type {
  V2ComposerTask,
  V2ComposerTaskStatus,
} from '@/services/studioV2ComposerAsync.service';
import {
  startStudioV2DryRunEventStream,
  stopStudioV2DryRunEventStream,
} from '@/services/studioV2DryRunAsyncEvents.service';
import type {
  V2DryRunStatus,
  V2DryRunTask,
} from '@/services/studioV2DryRunAsync.service';
import { buildSpecV2Wire } from '@/utils/studioV2/adapter';
import { AwaitingInputModalV2 } from '@/components/studio-v2/AwaitingInputModalV2';
import { BranchPickerModal } from '@/components/studio-v2/BranchPickerModal';
import { CasePickerModal } from '@/components/studio-v2/CasePickerModal';
import { EmptyStateUploader } from '@/components/studio-v2/EmptyStateUploader';
import { SetupPanel } from '@/components/studio-v2/SetupPanel';
import {
  TemplatePreviewV2,
  type PreviewTab,
} from '@/components/studio-v2/TemplatePreviewV2';
import { StudioV2Topbar } from '@/components/studio-v2/StudioV2Topbar';
import { TemplatesRail } from '@/components/studio-v2/TemplatesRail';
import { RegenerateTemplateModal } from '@/components/studio-v2/RegenerateTemplateModal';
import { UploadTemplateModal } from '@/components/studio-v2/UploadTemplateModal';
import { VariableWizard } from '@/components/studio-v2/VariableWizard';
import type {
  TemplateConfig,
  TemplateRole,
  WizardSourceParams,
} from '@/components/studio-v2/types';
import type { CaseResponse } from '@/types/studio/resolution';
import type {
  DryRunResponseV2,
  MergeOperationV2,
  PendingUserInputV2,
  UserSelectionV2,
} from '@/types/studio-v2';

// Dry-run flow state machine:
//   idle      — no dry-run in flight
//   running   — POST in flight (initial or resume)
//   awaiting  — BE paused; modal showing pending envelopes
//   completed — final result; modal showing rendered docx
type DryRunPhase = 'idle' | 'running' | 'awaiting' | 'completed';

export const StudioV2Page = () => {
  const addToast = useToastStore((state) => state.addToast);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const templates = useStudioV2Templates();
  const selectedTemplate = useStudioV2SelectedTemplate();
  const selectedTemplateId = useStudioV2Store((s) => s.selectedTemplateId);
  // Per-template docx-content version — bumped by composer-async
  // completion handlers (generate / regenerate). Threaded into
  // TemplatePreviewV2's renderKey so the editor knows to actually
  // re-fetch the docx when its content changes server-side (R2 path
  // alone can't detect overwrites; see TemplatePreviewV2 renderKey
  // comment for the full rationale).
  const selectedDocContentVersion = useStudioV2Store((s) =>
    s.selectedTemplateId ? s.docContentVersion[s.selectedTemplateId] ?? 0 : 0,
  );
  // True while the lazy GET /templates/{id} is in flight for the
  // currently-selected template. SetupPanel uses this to show a
  // skeleton + spinner under the Fields header so paralegals see
  // feedback during the fetch (otherwise fields just blink-fill
  // silently on lazy-load completion, which feels broken).
  const selectedFieldsLoading = useStudioV2Store((s) =>
    s.selectedTemplateId
      ? Boolean(s.loadingTemplateById[s.selectedTemplateId])
      : false,
  );
  const loading = useStudioV2Store((s) => s.loading);
  const refreshTemplates = useStudioV2Store((s) => s.refreshTemplates);
  const selectTemplate = useStudioV2Store((s) => s.selectTemplate);
  const saveFieldParams = useStudioV2Store((s) => s.saveFieldParams);
  const saveBundlingConfig = useStudioV2Store((s) => s.saveBundlingConfig);
  const removeTemplate = useStudioV2Store((s) => s.removeTemplate);
  const publishTemplate = useStudioV2Store((s) => s.publishTemplate);
  // Async composer store — fires Taskiq tasks instead of synchronous
  // POSTs so prod 504s on long LLM runs are no longer possible.
  const composerStartGenerate = useStudioV2ComposerTasksStore((s) => s.startGenerate);
  const composerStartRegenerate = useStudioV2ComposerTasksStore((s) => s.startRegenerate);
  const composerTasks = useStudioV2ComposerTasksStore((s) => s.tasks);
  const composerAutoSelectTaskId = useStudioV2ComposerTasksStore(
    (s) => s.autoSelectOnCompleteTaskId,
  );
  const composerSetAutoSelect = useStudioV2ComposerTasksStore(
    (s) => s.setAutoSelectOnCompleteTaskId,
  );
  // Async dry-run store — replaces the prior in-page synchronous
  // dryRun{Spec,Resolved,Pending,Result,BundlePicks} state. The task
  // record carries the spec + pause state + result; we just track
  // which task is currently focused (drives the modal + result tab).
  const dryRunStartFn = useStudioV2DryRunTasksStore((s) => s.startDryRun);
  const dryRunSubmitInputFn = useStudioV2DryRunTasksStore(
    (s) => s.submitInput,
  );
  const dryRunSetFocus = useStudioV2DryRunTasksStore(
    (s) => s.setFocusOnAwaitingInputTaskId,
  );
  const focusedDryRunTaskId = useStudioV2DryRunTasksStore(
    (s) => s.focusOnAwaitingInputTaskId,
  );
  const focusedDryRunTask = useStudioV2DryRunTasksStore((s) =>
    selectDryRunTaskById(s, s.focusOnAwaitingInputTaskId),
  );
  const selectedTemplateRaw = useStudioV2Store((s) =>
    s.selectedTemplateId ? s.templatesByIdRaw[s.selectedTemplateId] : null,
  );

  const [activeVariableName, setActiveVariableName] = useState<string | null>(null);
  const [highlightedVariableName, setHighlightedVariableName] = useState<string | null>(
    null,
  );
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [isRegenerateOpen, setIsRegenerateOpen] = useState(false);
  const [regenerateBusy, setRegenerateBusy] = useState(false);

  // Dry-run flow — see DryRunPhase type at top of file. Async flow:
  // the task record (on the dry-run store, populated via SSE) is the
  // source of truth for spec + resolved_values + pending_inputs +
  // result; the page only keeps the UI phase + the modal-driven case
  // label + bundle_picks (the latter needed pre-flight before the
  // task is created).
  const [dryRunPhase, setDryRunPhase] = useState<DryRunPhase>('idle');
  const [isCasePickerOpen, setIsCasePickerOpen] = useState(false);
  const [isBranchPickerOpen, setIsBranchPickerOpen] = useState(false);
  const [dryRunCase, setDryRunCase] = useState<CaseResponse | null>(null);
  const [dryRunPending, setDryRunPending] = useState<Record<string, PendingUserInputV2>>({});
  const [dryRunResult, setDryRunResult] = useState<DryRunResponseV2 | null>(null);
  // Pre-flight bundle picks — captured by BranchPickerModal before the
  // dry-run task is created. After /start, the server holds them on
  // the task record; we still cache the value here so /submit-input
  // can echo them on resume if needed.
  const [dryRunBundlePicks, setDryRunBundlePicks] = useState<Record<string, string> | null>(null);
  const [previewTab, setPreviewTab] = useState<PreviewTab>({ kind: 'template' });
  // Publish flow — busy state + validation errors surfaced inline on PublishStep.
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishValidationErrors, setPublishValidationErrors] = useState<string[]>([]);

  // Bundling-config save status. Two separate channels:
  //   - `roleStatus` drives the inline pill-morph feedback in
  //     TemplateRolePicker (single-click action — fires immediately,
  //     paralegal needs hard confirmation).
  //   - `bundlingStatus` covers other config saves (companion modal
  //     "Save changes") — surfaced as the smaller header chip in
  //     SetupPanel.
  const [roleStatus, setRoleStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');
  const [roleLastSavedAt, setRoleLastSavedAt] = useState<number | null>(null);
  // Persistent banner copy when the BE rejects a role change (e.g.
  // "part_of_packet templates can't contain user-input fields"). Toast
  // notifications fade away; this stays at the top of the sidebar
  // until the paralegal picks a new role or resolves the offending
  // fields.
  const [roleError, setRoleError] = useState<string | null>(null);
  const [bundlingStatus, setBundlingStatus] = useState<
    'idle' | 'saving' | 'saved' | 'error'
  >('idle');
  const roleSavedFadeRef = useRef<number | null>(null);
  const bundlingSavedFadeRef = useRef<number | null>(null);

  // URL → state. `:templateId` path param drives template selection;
  // `?tab=draft` query param requests the Syncfusion preview open on
  // the Draft tab by default (e.g. when arriving from a completed
  // dry-run chip click).
  const navigate = useNavigate();
  const { templateId: urlTemplateId } = useParams<{ templateId?: string }>();
  const [searchParams] = useSearchParams();
  const urlInitialTab = searchParams.get('tab');

  // Initial load: fetch templates from the v3 API.
  useEffect(() => {
    void refreshTemplates();
  }, [refreshTemplates]);

  // Sync URL → store. When the URL carries `:templateId`, drive the
  // store to that template. NO auto-select on bare `/studio-v2` —
  // the empty-state uploader IS the landing experience there
  // (per "user clicks Studio V2 from menu → upload page").
  useEffect(() => {
    if (urlTemplateId && urlTemplateId !== selectedTemplateId) {
      selectTemplate(urlTemplateId);
    } else if (!urlTemplateId && selectedTemplateId !== null) {
      // Navigated back to /studio-v2 (no id) — clear selection so
      // the EmptyStateUploader takes over instead of leaving the
      // last-viewed template stale.
      selectTemplate(null);
    }
  }, [urlTemplateId, selectedTemplateId, selectTemplate]);

  // Composer-async SSE stream — mount once per page, tear down on unmount.
  // The store rehydrates from the `snapshot` event on connect so a cold
  // reload always rebuilds in-flight cards.
  useEffect(() => {
    startStudioV2ComposerEventStream();
    return () => stopStudioV2ComposerEventStream();
  }, []);

  // Dry-run-async SSE stream — same pattern as composer-async.
  // Mounted ONLY here so dry-run task cards stay scoped to the
  // studio rail and never bleed into chat / cases / other pages.
  useEffect(() => {
    startStudioV2DryRunEventStream();
    return () => stopStudioV2DryRunEventStream();
  }, []);

  // Auto-select + refresh when a generate/regenerate task COMPLETES.
  // The store sets `autoSelectOnCompleteTaskId` when the user starts a
  // generate; once the SSE delivers the COMPLETED event with a
  // template_id, we refresh the rail + select the new template so the
  // wizard opens automatically.
  useEffect(() => {
    if (!composerAutoSelectTaskId) return;
    const task = composerTasks[composerAutoSelectTaskId];
    if (!task) return;
    if (task.status === 'COMPLETED' && task.template_id) {
      const newTemplateId = task.template_id;
      void refreshTemplates().then(() => {
        selectTemplate(newTemplateId);
      });
      composerSetAutoSelect(null);
    } else if (task.status === 'FAILED' || task.status === 'CANCELLED') {
      composerSetAutoSelect(null);
    }
    // Success / failure toasts live in the composer-transitions effect
    // below so EVERY composer task (auto-select or regenerate) gets
    // consistent feedback instead of only the upload-triggered one.
  }, [
    composerAutoSelectTaskId,
    composerTasks,
    composerSetAutoSelect,
    refreshTemplates,
    selectTemplate,
  ]);

  // For non-auto-select tasks (e.g. regenerate), still refresh the rail
  // when ANY composer task completes so the rail picks up updated_at /
  // field counts.
  const completedTaskIds = useMemo(() => {
    const ids = new Set<string>();
    for (const t of Object.values(composerTasks)) {
      if (t.status === 'COMPLETED') ids.add(t.task_id);
    }
    return Array.from(ids).sort().join(',');
  }, [composerTasks]);

  useEffect(() => {
    if (!completedTaskIds) return;
    void refreshTemplates();
  }, [completedTaskIds, refreshTemplates]);

  // Composer write completions (generate / regenerate) overwrite the
  // template's docx at the same R2 path. Bump the doc-content version
  // for newly-completed task's template_id so TemplatePreviewV2's
  // load-effect renderKey changes → editor actually re-fetches the
  // fresh content (path-only dedupe can't detect content changes on
  // an unchanged path).
  //
  // **Transition-only rule:** bump only on observed transition INTO
  // COMPLETED — never on the FIRST observation, even if the task is
  // already COMPLETED. SSE snapshot replays every task the user owns
  // on connect, many of which will be old COMPLETED runs from prior
  // sessions; bumping for those would trigger spurious editor
  // reloads (which openBlank-wipes the highlights on the currently-
  // selected template).
  //
  // Previous attempt seeded a tombstone set on first effect
  // invocation, but the first invocation ran with `composerTasks =
  // {}` (the SSE snapshot hadn't landed yet), so seeding was a
  // no-op and the bug returned the moment the snapshot arrived.
  // The per-task observed-status ref doesn't suffer from that race.
  const bumpDocContentVersion = useStudioV2Store((s) => s.bumpDocContentVersion);
  const composerObservedStatusRef = useRef<
    Record<string, V2ComposerTaskStatus>
  >({});
  useEffect(() => {
    for (const task of Object.values(composerTasks)) {
      const prevStatus = composerObservedStatusRef.current[task.task_id];
      composerObservedStatusRef.current[task.task_id] = task.status;
      if (task.status !== 'COMPLETED') continue;
      if (!task.template_id) continue;
      // First-time observation: even if status is already COMPLETED,
      // we never saw it transition — assume it's snapshot replay of
      // a prior-session completion and skip the bump.
      if (prevStatus === undefined) continue;
      // Already saw it as COMPLETED in a prior render — bump fired
      // (or was skipped) on that transition; don't re-bump.
      if (prevStatus === 'COMPLETED') continue;
      bumpDocContentVersion(task.template_id);
    }
  }, [composerTasks, bumpDocContentVersion]);

  // ─── Composer state-transition toasts ────────────────────────────
  // Fires a single toast on every observed transition (RUNNING / COMPLETED /
  // FAILED) so paralegals get feedback even if they're not watching the
  // rail chip. Skips the first observation of each task (snapshot replay
  // of prior-session tasks shouldn't blast toasts at page load).
  const composerToastObservedRef = useRef<
    Record<string, V2ComposerTaskStatus>
  >({});
  useEffect(() => {
    for (const task of Object.values(composerTasks)) {
      const prev = composerToastObservedRef.current[task.task_id];
      composerToastObservedRef.current[task.task_id] = task.status;
      if (prev === undefined) continue; // snapshot replay
      if (prev === task.status) continue; // no transition
      const name = task.template_name || task.original_filename || 'Template';
      const isRegen = task.kind === 'regenerate';
      if (task.status === 'RUNNING') {
        addToast(
          isRegen ? `Re-reading "${name}"…` : `Reading "${name}"…`,
          'info',
        );
      } else if (task.status === 'COMPLETED') {
        addToast(
          isRegen ? `"${name}" re-read complete` : `Template "${name}" is ready`,
          'success',
        );
      } else if (task.status === 'FAILED') {
        addToast(
          task.error || `Failed to process "${name}"`,
          'error',
        );
      }
    }
  }, [composerTasks, addToast]);

  // ─── Dry-run state-transition toasts ─────────────────────────────
  // Same pattern as composer-transitions: skip first observation
  // (snapshot replay), fire on each genuine status hop.
  const dryRunTasksMap = useStudioV2DryRunTasksStore((s) => s.tasks);
  const dryRunToastObservedRef = useRef<Record<string, V2DryRunStatus>>({});
  useEffect(() => {
    for (const task of Object.values(dryRunTasksMap)) {
      const prev = dryRunToastObservedRef.current[task.task_id];
      dryRunToastObservedRef.current[task.task_id] = task.status;
      if (prev === undefined) continue;
      if (prev === task.status) continue;
      const label = task.template_name || 'Dry-run';
      const caseTag = task.case_label || '';
      const suffix = caseTag ? ` (${caseTag})` : '';
      if (task.status === 'RUNNING') {
        addToast(`Resolving fields for "${label}"${suffix}…`, 'info');
      } else if (task.status === 'AWAITING_INPUT') {
        addToast(
          `"${label}"${suffix} needs your input — click the rail chip`,
          'info',
        );
      } else if (task.status === 'COMPLETED') {
        addToast(
          `Dry-run of "${label}"${suffix} is ready — click the rail chip to open`,
          'success',
        );
      } else if (task.status === 'FAILED') {
        addToast(task.error || `Dry-run of "${label}"${suffix} failed`, 'error');
      }
    }
  }, [dryRunTasksMap, addToast]);

  // Reset dry-run state whenever the selected template changes — a
  // result from template A is meaningless once you're viewing template
  // B, and the Draft tab would otherwise keep loading the old filled
  // docx into the new template's editor.
  //
  // EXCEPTION: if the focused dry-run task already belongs to the new
  // template (e.g. paralegal clicked a completed dry-run chip → we
  // navigated here intentionally with `?tab=draft`), preserve the
  // dry-run state so the watcher's `dryRunResult` survives into the
  // Draft pane.
  useEffect(() => {
    const arrivedFromDryRunChip =
      focusedDryRunTask?.template_id === selectedTemplateId &&
      focusedDryRunTask?.status === 'COMPLETED';
    if (!arrivedFromDryRunChip) {
      setDryRunPhase('idle');
      setDryRunCase(null);
      setDryRunPending({});
      setDryRunResult(null);
      setDryRunBundlePicks(null);
    }
    // Initial Syncfusion tab: `?tab=draft` query param (set by the
    // dry-run chip click) opens the Draft pane immediately; otherwise
    // land on the Template tab.
    setPreviewTab(
      urlInitialTab === 'draft' ? { kind: 'draft' } : { kind: 'template' },
    );
    setIsCasePickerOpen(false);
    setIsBranchPickerOpen(false);
    setPublishValidationErrors([]);
    // Intentional dep list — re-fire on template switch only. Reading
    // `focusedDryRunTask` / `urlInitialTab` directly so we always see
    // the latest values at fire time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTemplateId]);

  const activeVariable = useMemo(() => {
    if (!selectedTemplate) return null;
    return (
      selectedTemplate.variables.find(
        (v) => v.template_variable === activeVariableName,
      ) ?? null
    );
  }, [selectedTemplate, activeVariableName]);

  const allVariableNames = useMemo(
    () => selectedTemplate?.variables.map((v) => v.template_variable) ?? [],
    [selectedTemplate],
  );

  const configuredCount =
    selectedTemplate?.variables.filter((v) => v.params !== null).length ?? 0;
  const totalCount = selectedTemplate?.variables.length ?? 0;

  const handleSelectTemplate = (id: string) => {
    // Drive selection via the URL so the address bar, back/forward,
    // and shareable links all stay in sync. The URL→store effect
    // above will call `selectTemplate(id)` on the param change.
    navigate(`/studio-v2/${encodeURIComponent(id)}`);
    setActiveVariableName(null);
    setHighlightedVariableName(null);
  };

  const handleSaveVariable = (variableName: string, params: WizardSourceParams) => {
    if (!selectedTemplateId) return;
    void saveFieldParams(selectedTemplateId, variableName, params);
  };

  const handleOpenWizard = (variableName: string) => {
    setActiveVariableName(variableName);
    setHighlightedVariableName(variableName);
  };

  const handleCloseWizard = () => {
    setActiveVariableName(null);
  };

  const handleConfigChange = (patch: Partial<TemplateConfig>) => {
    if (!selectedTemplateId || !selectedTemplate) return;
    const nextConfig: TemplateConfig = { ...selectedTemplate.config, ...patch };
    // Fire immediately. Callers are explicit, user-initiated actions:
    //   - role pill click (TemplateRolePicker — single click)
    //   - "Save changes" in CompanionsModal (paralegal already
    //     committed to saving by clicking the button)
    // Debouncing was only needed when slot-config text inputs fired
    // onChange per keystroke; that's gone now (modal holds local draft).
    const isRoleChange = patch.role !== undefined;
    if (isRoleChange) {
      setRoleStatus('saving');
      setRoleError(null); // clear stale banner on every fresh attempt
      if (roleSavedFadeRef.current !== null) {
        window.clearTimeout(roleSavedFadeRef.current);
        roleSavedFadeRef.current = null;
      }
    } else {
      setBundlingStatus('saving');
      if (bundlingSavedFadeRef.current !== null) {
        window.clearTimeout(bundlingSavedFadeRef.current);
        bundlingSavedFadeRef.current = null;
      }
    }
    const targetId = selectedTemplateId;
    void (async () => {
      // For role saves we suppress the toast (banner is more persistent
      // + lives next to the picker that owns the action). For other
      // bundling saves the toast still fires as the primary error UX.
      const errorMsg = await saveBundlingConfig(targetId, nextConfig, {
        silent: isRoleChange,
      });
      if (errorMsg) {
        if (isRoleChange) {
          setRoleStatus('error');
          setRoleError(errorMsg);
        } else {
          setBundlingStatus('error');
        }
        return;
      }
      if (isRoleChange) {
        setRoleStatus('saved');
        setRoleLastSavedAt(Date.now());
        roleSavedFadeRef.current = window.setTimeout(() => {
          setRoleStatus('idle');
          roleSavedFadeRef.current = null;
        }, 1800);
      } else {
        setBundlingStatus('saved');
        bundlingSavedFadeRef.current = window.setTimeout(() => {
          setBundlingStatus('idle');
          bundlingSavedFadeRef.current = null;
        }, 1800);
      }
    })();
  };

  // Auto-dismiss the persistent role-error banner if the paralegal
  // switches templates — the error was about the OLD template.
  useEffect(() => {
    setRoleError(null);
  }, [selectedTemplateId]);

  // Cleanup pending fade timers on unmount.
  useEffect(
    () => () => {
      if (roleSavedFadeRef.current !== null) {
        window.clearTimeout(roleSavedFadeRef.current);
      }
      if (bundlingSavedFadeRef.current !== null) {
        window.clearTimeout(bundlingSavedFadeRef.current);
      }
    },
    [],
  );

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFilePicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.docx')) {
      addToast('Only .docx files are supported', 'error');
      return;
    }
    setPendingFile(file);
  };

  const handleConfirmUpload = async (templateName: string, role: TemplateRole) => {
    if (!pendingFile) return;
    setUploadBusy(true);
    // Async path: enqueue the task and close the modal IMMEDIATELY.
    // The card overlay shows progress; on COMPLETED, the useEffect
    // below auto-selects the new template once it appears in the rail.
    const result = await composerStartGenerate(pendingFile, templateName, role);
    setUploadBusy(false);
    if (result.success) {
      setPendingFile(null);
      addToast(
        'Template upload queued — track progress in the rail on the left.',
        'info',
      );
    } else {
      addToast(result.error ?? 'Failed to start template upload', 'error');
    }
  };

  const handleCancelUpload = () => {
    if (uploadBusy) return;
    setPendingFile(null);
  };

  const handleRegenerateConfirm = async (payload: {
    ignored_texts: string[];
    merges: MergeOperationV2[];
    regeneration_instruction: string | null;
  }): Promise<void> => {
    if (!selectedTemplateId) return;
    setRegenerateBusy(true);
    const result = await composerStartRegenerate({
      template_id: selectedTemplateId,
      ignored_texts: payload.ignored_texts,
      merges: payload.merges,
      regeneration_instruction: payload.regeneration_instruction,
    });
    setRegenerateBusy(false);
    setIsRegenerateOpen(false);
    if (result.success) {
      addToast(
        'Re-read queued — track progress in the rail on the left.',
        'info',
      );
    } else {
      addToast(result.error ?? 'Failed to start re-extract', 'error');
    }
  };

  // ─── Dry-run flow ───────────────────────────────────────────────

  const handleOpenCasePicker = (): void => {
    if (!selectedTemplateRaw) return;
    if (selectedTemplate?.variables.length === 0) {
      addToast('Add fields before testing — there is nothing to extract.', 'info');
      return;
    }
    setIsCasePickerOpen(true);
  };

  const handleCasePicked = async (caseRow: CaseResponse): Promise<void> => {
    if (!selectedTemplateRaw) return;
    setIsCasePickerOpen(false);
    setDryRunCase(caseRow);

    // Pre-flight: if the lead template has any BRANCH companions, the
    // paralegal must pick which option per branch BEFORE we POST. The
    // bundling engine needs bundle_picks to know which child template
    // to schedule for each branch. Fixed companions always run — no
    // pick needed.
    const hasBranchCompanions =
      selectedTemplate?.config.companions.some((c) => c.kind === 'branch') ?? false;
    if (hasBranchCompanions) {
      setIsBranchPickerOpen(true);
      return;
    }

    await launchDryRun(caseRow, null);
  };

  const handleBranchPicked = async (
    bundlePicks: Record<string, string>,
  ): Promise<void> => {
    if (!dryRunCase) return;
    setIsBranchPickerOpen(false);
    await launchDryRun(dryRunCase, bundlePicks);
  };

  const launchDryRun = async (
    caseRow: CaseResponse,
    bundlePicks: Record<string, string> | null,
  ): Promise<void> => {
    if (!selectedTemplateRaw) return;
    const spec = buildSpecV2Wire(selectedTemplateRaw);
    setDryRunBundlePicks(bundlePicks);
    setDryRunPhase('running');
    setDryRunPending({});
    setDryRunResult(null);

    // Async path — POST returns a task_id in <100ms; SSE delivers the
    // status_changed → awaiting_input / completed / failed events that
    // drive the modal + result preview via `focusedDryRunTask`.
    const result = await dryRunStartFn({
      template_id: selectedTemplateRaw.id,
      case_id: caseRow.id,
      template_spec: spec,
      bundle_picks: bundlePicks,
    });

    if (!result.success || !result.data) {
      setDryRunPhase('idle');
      setDryRunCase(null);
      setDryRunBundlePicks(null);
      addToast(result.error ?? 'Dry-run failed', 'error');
      return;
    }
    // `dryRunStartFn` already set focusOnAwaitingInputTaskId — the
    // useEffect watching `focusedDryRunTask.status` below promotes
    // the modal / result tab when the SSE event lands.
  };

  const handleAwaitingSubmit = async (
    picks: Record<string, UserSelectionV2>,
  ): Promise<void> => {
    if (!focusedDryRunTaskId) return;
    const taskId = focusedDryRunTaskId;

    // Close the modal IMMEDIATELY — no "Submitting…" / "Working on
    // it" placeholder while the POST is in flight. The POST runs in
    // the background; SSE picks up the RESUMING → COMPLETED
    // transitions and the rail chip tracks progress. On failure,
    // the task is still AWAITING_INPUT on the BE — paralegal can
    // re-open the modal via the chip and retry.
    setDryRunPending({});
    setDryRunPhase('idle');

    const result = await dryRunSubmitInputFn(taskId, {
      user_picks: picks,
      bundle_picks: dryRunBundlePicks,
    });
    if (!result.success) {
      addToast(result.error ?? 'Resume failed', 'error');
    }
  };

  const handleBranchPickerCancel = (): void => {
    setIsBranchPickerOpen(false);
    setDryRunCase(null);
    setDryRunPhase('idle');
  };

  const handleDryRunClose = (): void => {
    // Closing the modal does NOT cancel the task. AWAITING_INPUT
    // means the worker is paused waiting for picks — nothing is
    // running, no LLM tokens burning. The paralegal might just be
    // stepping away to look at another template; the chip in the
    // rail stays in AWAITING_INPUT and they can re-open the modal
    // by clicking the chip. If they want to abandon the run, they
    // click × on the chip itself (which fires DELETE → tombstone).
    //
    // We DO clear local page state (focus, case, pending,
    // previewTab) so the page isn't stuck on a half-closed modal
    // state; the chip in the rail is the source of truth.
    dryRunSetFocus(null);
    setDryRunPhase('idle');
    setDryRunBundlePicks(null);
    setDryRunCase(null);
    setDryRunPending({});
    setDryRunResult(null);
    setPreviewTab({ kind: 'template' });
  };

  // Watch the focused dry-run task's SSE-delivered status and drive
  // the local UI phase + preview tab off it. Until the user starts
  // a fresh dry-run, status hops here: PENDING / RUNNING / RESUMING
  // → 'running'; AWAITING_INPUT → 'awaiting' (modal opens, even
  //   when on a different template — the modal is standalone);
  // COMPLETED → 'completed' (BUT NO auto-tab-flip; user clicks the
  //   chip's Open to view the rendered draft);
  // FAILED → 'idle' (toast surfaced by the dry-run transition
  //   watcher above; this branch just clears local state).
  //
  // Template-match guard now applies PER-BRANCH, not globally:
  //   - AWAITING_INPUT bypasses the guard so the modal can open
  //     regardless of which template the user is currently viewing
  //     (the modal reads template_name directly from the focused
  //     task, not from selectedTemplate).
  //   - COMPLETED stays guarded so dryRunResult doesn't spill into
  //     a different template view's Draft pane.
  //   - Active phase syncing (PENDING/RUNNING/QUEUED) stays guarded
  //     so the "running" page state only reflects work for the
  //     currently-viewed template.
  useEffect(() => {
    if (!focusedDryRunTask) return;
    const s = focusedDryRunTask.status;
    const onSameTemplate =
      focusedDryRunTask.template_id === selectedTemplateId;
    if (s === 'RESUMING') {
      // Resume happens AFTER the paralegal submitted picks. The
      // submit handler already closed the modal — don't reopen it
      // by flipping phase to 'running'. The rail chip is the
      // canonical progress indicator while resume runs.
      return;
    }
    if (s === 'AWAITING_INPUT') {
      // Open the pick modal regardless of which template is selected.
      // The modal renders standalone with the focused task's own
      // template_name in its header.
      setDryRunPending(focusedDryRunTask.pending_inputs ?? {});
      setDryRunPhase('awaiting');
      return;
    }
    if (!onSameTemplate) {
      // For non-AWAITING states, never spill into a different template
      // view's page state. The chip in the rail still shows progress.
      return;
    }
    if (s === 'PENDING' || s === 'RUNNING' || s === 'QUEUED') {
      setDryRunPhase('running');
      return;
    }
    if (s === 'COMPLETED' && focusedDryRunTask.result) {
      // Populate dryRunResult so the Draft pane can render when the
      // user opens it — but do NOT auto-flip the preview tab. The
      // user must explicitly click the chip's Open button.
      setDryRunResult(focusedDryRunTask.result);
      setDryRunPhase('completed');
      return;
    }
    if (s === 'FAILED') {
      setDryRunPhase('idle');
      dryRunSetFocus(null);
      return;
    }
  }, [focusedDryRunTask, dryRunSetFocus, selectedTemplateId]);

  // Rail-card click handler — paralegal clicked a dry-run card.
  // Only COMPLETED navigates; AWAITING_INPUT opens the pick modal
  // in place (no template hop, no surprise redirect when the user
  // is configuring something else).
  //
  //   - AWAITING_INPUT → focus the task. The watcher pops
  //     AwaitingInputModalV2 even when the user is on a different
  //     template; the modal renders standalone with the task's
  //     own template_name in the header.
  //   - COMPLETED → open the rendered draft. If already on the
  //     task's template, flip preview to the Draft tab. Otherwise
  //     navigate to `/studio-v2/<template_id>?tab=draft`.
  // Composer rail-card click — fires on COMPLETED composer chips
  // (cards filter to .status === 'COMPLETED' before calling onClick).
  // Navigates to the new template's URL, mirroring the dry-run chip
  // pattern. If the user is already on that template the URL change
  // is a no-op (useNavigate dedupes); the rail row will already be
  // selected.
  const handleComposerTaskClick = (task: V2ComposerTask): void => {
    if (!task.template_id) return;
    if (task.template_id === selectedTemplateId) return;
    navigate(`/studio-v2/${encodeURIComponent(task.template_id)}`);
  };

  const handleDryRunRailClick = (task: V2DryRunTask): void => {
    dryRunSetFocus(task.task_id);
    setDryRunCase({
      id: task.case_id,
      case_number: task.case_label,
      created_at: '',
    } as unknown as CaseResponse);

    if (task.status === 'COMPLETED') {
      const onSameTemplate = task.template_id === selectedTemplateId;
      if (onSameTemplate) {
        setPreviewTab({ kind: 'draft' });
      } else {
        navigate(
          `/studio-v2/${encodeURIComponent(task.template_id)}?tab=draft`,
        );
      }
    }
    // AWAITING_INPUT: no navigation. The watcher's AWAITING_INPUT
    // branch (no template-match guard) opens the modal in place.
  };

  // Phase 1: in-line template creation from Companions modal is mocked
  // (no separate "create blank" endpoint in v3 yet — paralegal uploads
  // a docx). Surface a toast so the user understands.
  const handleCreateTemplate = (name: string): string => {
    addToast(
      `Stub-template "${name.trim()}" creation isn't wired in Phase 1 — upload a .docx instead.`,
      'info',
    );
    return '';
  };

  const topbarTemplateName = selectedTemplate?.name ?? 'No template selected';
  const initialFetchInProgress = loading && templates.length === 0 && !pendingFile;

  return (
    <div className="flex h-screen min-h-0 flex-col bg-page">
      <StudioV2Topbar
        templateName={topbarTemplateName}
        configuredCount={configuredCount}
        totalCount={totalCount}
      />

      <div className="shrink-0 border-b border-border bg-app-accent-soft/40 px-5 py-1.5">
        <p className="text-[11px] text-app-accent-text">
          <span className="font-semibold">Template Studio V2.</span>{' '}
          {loading ? 'Loading…' : 'Backed by /api/v3/studio.'}
        </p>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        onChange={handleFilePicked}
      />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <TemplatesRail
          templates={templates}
          selectedTemplateId={selectedTemplateId}
          onSelectTemplate={handleSelectTemplate}
          onUploadClick={handleUploadClick}
          onComposerTaskClick={handleComposerTaskClick}
          onDryRunTaskClick={handleDryRunRailClick}
        />

        {selectedTemplate ? (
          <>
            <main className="flex min-w-0 flex-1 flex-col bg-surface-muted/30 p-3">
              <TemplatePreviewV2
                template={selectedTemplate}
                templateDocUrl={selectedTemplateRaw?.template_doc_url ?? null}
                onSelectVariable={handleOpenWizard}
                dryRunResult={
                  dryRunPhase === 'completed' ? dryRunResult : null
                }
                activeTab={previewTab}
                onTabChange={setPreviewTab}
                docContentVersion={selectedTemplateId ? selectedDocContentVersion : 0}
              />
            </main>

            <SetupPanel
              isFieldsLoading={selectedFieldsLoading}
              templateName={selectedTemplate.name}
              templateConfig={selectedTemplate.config}
              variables={selectedTemplate.variables}
              highlightedVariableName={highlightedVariableName}
              allTemplates={templates}
              currentTemplateId={selectedTemplate.id}
              publishedAt={selectedTemplateRaw?.published_at ?? null}
              hasUnpublishedChanges={
                selectedTemplateRaw?.has_unpublished_changes ?? true
              }
              onChangeConfig={handleConfigChange}
              bundlingStatus={bundlingStatus}
              roleStatus={roleStatus}
              roleLastSavedAt={roleLastSavedAt}
              roleError={roleError}
              onDismissRoleError={() => setRoleError(null)}
              onSelectVariable={handleOpenWizard}
              onHoverVariable={setHighlightedVariableName}
              onCreateTemplate={handleCreateTemplate}
              isPublishing={isPublishing}
              publishValidationErrors={publishValidationErrors}
              onDismissPublishValidationErrors={() => setPublishValidationErrors([])}
              onPublishClick={async () => {
                if (!selectedTemplateId || isPublishing) return;
                setPublishValidationErrors([]);
                setIsPublishing(true);
                const result = await publishTemplate(selectedTemplateId);
                setIsPublishing(false);
                if (!result.ok && result.validationErrors.length > 0) {
                  setPublishValidationErrors(result.validationErrors);
                }
              }}
              onRegenerateClick={() => setIsRegenerateOpen(true)}
              onTestAgainstCaseClick={handleOpenCasePicker}
              onDeleteTemplate={async () => {
                if (!selectedTemplateId) return;
                // Capture name before delete so the toast still has
                // a label even after `removeTemplate` clears the
                // store's selected template.
                const deletedName = selectedTemplate.name;
                await removeTemplate(selectedTemplateId);
                addToast(`Deleted "${deletedName}"`, 'success');
                // Navigate back to the bare studio URL so the
                // EmptyStateUploader takes over. The URL→store
                // effect drops the selection alongside the
                // navigation (we already ran the DB delete).
                navigate('/studio-v2');
              }}
            />
          </>
        ) : (
          <main className="flex min-w-0 flex-1 flex-col">
            {initialFetchInProgress ? (
              <div className="flex h-full items-center justify-center text-subtle">
                <span className="inline-flex items-center gap-2 text-sm">
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-app-accent/30 border-t-app-accent" />
                  Loading templates…
                </span>
              </div>
            ) : (
              <EmptyStateUploader
                variant={templates.length === 0 ? 'no_templates' : 'no_selection'}
                onUploadClick={handleUploadClick}
              />
            )}
          </main>
        )}
      </div>

      <UploadTemplateModal
        isOpen={pendingFile !== null}
        file={pendingFile}
        busy={uploadBusy}
        onConfirm={handleConfirmUpload}
        onClose={handleCancelUpload}
      />

      {selectedTemplate && (
        <RegenerateTemplateModal
          isOpen={isRegenerateOpen}
          templateName={selectedTemplate.name}
          variables={selectedTemplate.variables}
          busy={regenerateBusy}
          onConfirm={handleRegenerateConfirm}
          onClose={() => {
            // Closing while busy hides the modal but lets the
            // regenerate promise keep running in the background; the
            // store's regenerateTemplate fires a toast on success and
            // refreshes the template list automatically.
            setIsRegenerateOpen(false);
          }}
        />
      )}

      {/* Dry-run flow — modals discriminated by phase. */}
      {selectedTemplate && (
        <CasePickerModal
          isOpen={isCasePickerOpen}
          templateName={selectedTemplate.name}
          onPick={handleCasePicked}
          onClose={() => setIsCasePickerOpen(false)}
        />
      )}

      {selectedTemplate && (
        <BranchPickerModal
          isOpen={isBranchPickerOpen}
          templateName={selectedTemplate.name}
          caseLabel={dryRunCase?.case_number ?? null}
          companions={selectedTemplate.config.companions}
          onSubmit={handleBranchPicked}
          onCancel={handleBranchPickerCancel}
        />
      )}

      {/* Modal is rendered unconditionally so AWAITING_INPUT chips
          can pop it even when the user is on bare /studio-v2 (no
          template selected) or on a different template than the
          dry-run's. templateName comes from the focused task, not
          selectedTemplate, so the header always shows the correct
          template. */}
      <AwaitingInputModalV2
        isOpen={dryRunPhase === 'awaiting'}
        templateName={
          focusedDryRunTask?.template_name ||
          selectedTemplate?.name ||
          'Dry-run'
        }
        caseId={dryRunCase?.id ?? null}
        caseLabel={dryRunCase?.case_number ?? null}
        caseName={dryRunCase?.case_name ?? null}
        pendingInputs={dryRunPending}
        onSubmit={handleAwaitingSubmit}
        onCancel={handleDryRunClose}
      />

      {/* The old full-screen DryRunRunningOverlay was removed when
          dry-run moved to Taskiq. The async card in the rail
          (DryRunTasksRailSection) is now the canonical progress
          indicator — paralegals can keep iterating on the wizard
          while the run executes in the background. */}

      <VariableWizard
        variable={activeVariable}
        allVariableNames={allVariableNames}
        onClose={handleCloseWizard}
        onSave={handleSaveVariable}
      />
    </div>
  );
};
