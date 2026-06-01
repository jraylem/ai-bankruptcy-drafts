import React, { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { LuCircleCheck, LuX } from 'react-icons/lu';
import Lottie from 'lottie-react';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { Tooltip } from '@/components/common';
import { AwaitingInputModal } from '@/components/studio-draft/AwaitingInputModal';
import { AwaitingInputBanner } from '@/components/studio';
import { CaseSelectionModal } from '@/components/studio';
import { BranchPickerModal } from '@/components/studio/modals/BranchPickerModal';
import { RegenerateDiffSummary } from '@/components/studio/RegenerateDiffSummary';
import { ConstantsModal } from '@/components/studio';
import { RegenerateTemplateModal } from '@/components/studio';
import { TemplateBundleSettings } from '@/components/studio';
import { TemplatePreview } from '@/components/studio';
import { StudioTemplateUploader, UploadTemplateModal } from '@/components/studio';
import { VariablesWorkspace } from '@/components/studio';
import {
  emptyAwaitingDraftState,
  type AwaitingDraftState,
} from '@/hooks/useDraftingPersistence';
import { useStudioStore } from '@/stores/useStudioStore';
import { useToastStore } from '@/stores/useToastStore';
import dryRunAnimation from '@/assets/lottie/dry-run.json';
import templateLoadingAnimation from '@/assets/lottie/upload-search.json';

import type { PreviewMode } from '@/components/studio/TemplatePreview';

type MobilePane = 'workspace' | 'preview';

const isCompanionPreviewMode = (
  mode: PreviewMode,
): mode is { kind: 'companion'; index: number } =>
  typeof mode === 'object' && mode.kind === 'companion';

// Side-by-side workspace+preview split only fits comfortably at xl (1280px);
// below that we fall back to the single-column Workspace/Preview toggle so the
// preview isn't squeezed/clipped. Keep this in sync with the `xl:` classes.
const DESKTOP_BREAKPOINT_QUERY = '(min-width: 1280px)';
const RESIZE_MIN_PCT = 55;
const RESIZE_MAX_PCT = 75;
const DEFAULT_PREVIEW_WIDTH_PCT = 65;

const DRY_RUN_PHRASES: Array<[string, string]> = [
  ['Resolving', 'the fields'],
  ['Fetching', 'the sources'],
  ['Cross-referencing', 'the record'],
  ['Querying', 'the docket'],
  ['Construing', 'the statute'],
  ['Marshalling', 'the evidence'],
  ['Stipulating', 'the facts'],
  ['Annotating', 'the margins'],
  ['Redlining', 'the draft'],
  ['Filing', 'the caption'],
  ['Compiling', 'the brief'],
  ['Certifying', 'the signature'],
];

const isVariableMapped = (source: unknown, params: unknown): boolean => {
  if (source === null) return false;
  if (source === 'case_vector') return true;
  return params !== null;
};

const isDesktopViewport = (): boolean =>
  typeof window === 'undefined' ? true : window.matchMedia(DESKTOP_BREAKPOINT_QUERY).matches;

const FLOW_STATE_STYLES: Record<string, { label: string; className: string }> = {
  new: { label: 'New', className: 'bg-surface-muted text-muted' },
  generated: { label: 'Generated', className: 'bg-sky-50 text-sky-700' },
  configuring: { label: 'Configuring', className: 'bg-app-warning-soft text-app-warning-text' },
  verified: { label: 'Verified', className: 'bg-app-accent-soft text-app-accent-text' },
  persisted: { label: 'Saved', className: 'bg-app-success-soft text-app-success-text' },
};

const FlowStatePill = ({ state }: { state: string }): ReactElement => {
  const style = FLOW_STATE_STYLES[state] ?? FLOW_STATE_STYLES.new;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${style.className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {style.label}
    </span>
  );
};

const Spinner = (): ReactElement => (
  <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path
      className="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
    />
  </svg>
);

interface EditableTitleProps {
  value: string;
  isEditing: boolean;
  onStartEdit: () => void;
  onCommit: (next: string) => void;
  onCancel: () => void;
}

const EditableTitle = ({
  value,
  isEditing,
  onStartEdit,
  onCommit,
  onCancel,
}: EditableTitleProps): ReactElement => {
  const [draft, setDraft] = useState<string>(value);

  useEffect((): void => {
    if (isEditing) setDraft(value);
  }, [isEditing, value]);

  if (isEditing) {
    return (
      <textarea
        autoFocus
        rows={1}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => onCommit(draft)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onCommit(draft);
          }
          if (e.key === 'Escape') onCancel();
        }}
        className="mt-0.5 block w-full resize-none rounded border border-indigo-300 bg-surface px-2 py-1 text-lg font-semibold leading-snug text-text-secondary break-words focus:outline-none focus:ring-2 focus:ring-app-accent-soft sm:text-xl"
        style={{ minHeight: '2.5rem', height: 'auto' }}
        onInput={(e) => {
          const el = e.currentTarget;
          el.style.height = 'auto';
          el.style.height = `${el.scrollHeight}px`;
        }}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={onStartEdit}
      className="group mt-0.5 flex w-full items-start gap-2 rounded text-left"
      title="Click to rename"
    >
      <span className="min-w-0 flex-1 break-words text-lg font-semibold leading-snug text-text-secondary sm:text-xl">
        {value}
      </span>
      <svg
        className="mt-1.5 h-3 w-3 shrink-0 text-subtle opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
      </svg>
    </button>
  );
};

interface MenuItemDef {
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  danger?: boolean;
  separator?: boolean;
}

interface MenuDropdownProps {
  label: React.ReactNode;
  items: MenuItemDef[];
  title?: string;
}

const MenuDropdown = ({ label, items, title }: MenuDropdownProps): ReactElement => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect((): (() => void) | void => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent): void => {
      if (!containerRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return (): void => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const trigger = (
    <button
      type="button"
      onClick={() => setIsOpen((prev) => !prev)}
      className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
        isOpen ? 'bg-border text-text-secondary' : 'text-text-secondary hover:bg-surface-muted'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="relative" ref={containerRef}>
      {title && !isOpen ? (
        <Tooltip label={title} side="bottom">
          {trigger}
        </Tooltip>
      ) : (
        trigger
      )}
      {isOpen && (
        <div
          role="menu"
          className="absolute left-0 top-full z-50 mt-1 min-w-[200px] rounded-lg border border-border bg-surface py-1 shadow-lg"
        >
          {items.map((item, idx) => {
            if (item.separator) {
              return <div key={`sep-${idx}`} className="my-1 h-px bg-surface-muted" />;
            }
            return (
              <button
                key={`${item.label}-${idx}`}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                onClick={() => {
                  setIsOpen(false);
                  item.onClick?.();
                }}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${
                  item.danger
                    ? 'text-app-danger-text hover:bg-app-danger-soft'
                    : 'text-text-secondary hover:bg-surface-muted'
                } disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent`}
              >
                {item.loading && <Spinner />}
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

const toolbarSvg = {
  fill: 'none',
  stroke: 'currentColor',
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  strokeWidth: 2,
  viewBox: '0 0 24 24',
  className: 'h-3.5 w-3.5',
};

const IconUpload = (): ReactElement => (
  <svg {...toolbarSvg}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);
const IconSaveDisk = (): ReactElement => (
  <svg {...toolbarSvg}>
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
    <polyline points="17 21 17 13 7 13 7 21" />
    <polyline points="7 3 7 8 15 8" />
  </svg>
);
const IconPlay = (): ReactElement => (
  <svg {...toolbarSvg}>
    <polygon points="6 4 20 12 6 20 6 4" fill="currentColor" />
  </svg>
);
const IconMore = (): ReactElement => (
  <svg {...toolbarSvg}>
    <circle cx="5" cy="12" r="1.25" fill="currentColor" />
    <circle cx="12" cy="12" r="1.25" fill="currentColor" />
    <circle cx="19" cy="12" r="1.25" fill="currentColor" />
  </svg>
);

interface ToolbarButtonProps {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
  loading?: boolean;
  title?: string;
}

const ToolbarButton = ({
  onClick,
  icon,
  label,
  disabled = false,
  loading = false,
  title,
}: ToolbarButtonProps): ReactElement => {
  const btn = (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded px-2.5 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-muted hover:text-text-secondary disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-text-secondary"
    >
      {loading ? <Spinner /> : icon}
      <span>{label}</span>
    </button>
  );
  if (!title) return btn;
  return (
    <Tooltip label={title} side="bottom">
      {btn}
    </Tooltip>
  );
};

interface CollapsibleSectionProps {
  title: string;
  description?: string;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

const CollapsibleSection = ({
  title,
  description,
  isOpen,
  onToggle,
  children,
}: CollapsibleSectionProps): ReactElement => (
  <section className="rounded-2xl border border-border bg-surface shadow-sm">
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={isOpen}
      className="flex w-full items-start justify-between gap-3 rounded-t-2xl px-5 py-3 text-left transition-colors hover:bg-surface-muted"
    >
      <div className="min-w-0 flex-1">
        <h2 className="text-sm font-semibold text-text-secondary">{title}</h2>
        {description && (
          <p className="mt-0.5 text-xs leading-relaxed text-muted">{description}</p>
        )}
      </div>
      <svg
        aria-hidden="true"
        className={`mt-1 h-4 w-4 shrink-0 text-muted transition-transform ${
          isOpen ? 'rotate-180' : ''
        }`}
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        viewBox="0 0 24 24"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
    {isOpen && <div className="border-t border-border px-5 py-4">{children}</div>}
  </section>
);

export const StudioPage = (): ReactElement => {
  const {
    selectedTemplateId,
    selectedCaseId,
    cases,
    templates,
    templateSpec,
    templateDocUrl,
    originalDocUrl,
    dryRunResult,
    draftResult,
    agentConfig,
    flowState,
    error,
    isDirty,
    isBundlingDirty,
    bundleRole,
    bundleCompanions,
    regenerateDiff,
    clearRegenerateDiff,
    isSaving,
    justSavedAt,
    clearJustSavedAt,
    isDryRunning,
    isDrafting,
    loadCases,
    loadTemplates,
    loadConnectors,
    loadReferenceData,
    selectTemplate,
    resetToNew,
    saveConfiguration,
    runDryRun,
    runDraft,
    renameTemplate,
    clearError,
    dryRunAwaiting,
    resumeDryRun,
    dismissDryRunAwaiting,
    draftAwaiting,
    resumeDraft,
    dismissDraftAwaiting,
  } = useStudioStore();

  const addToast = useToastStore((state) => state.addToast);
  const navigate = useNavigate();
  const { templateId: routeTemplateId } = useParams<{ templateId?: string }>();

  // Collapsible workspace sections — both default open, user can collapse
  // each independently. Reset to "both open" whenever the user navigates
  // to a different template.
  const [isSpecOpen, setIsSpecOpen] = useState<boolean>(true);
  const [isBundlingOpen, setIsBundlingOpen] = useState<boolean>(true);
  useEffect(() => {
    setIsSpecOpen(true);
    setIsBundlingOpen(true);
  }, [selectedTemplateId]);

  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const [isConstantsModalOpen, setIsConstantsModalOpen] = useState<boolean>(false);
  const [isRegenerateModalOpen, setIsRegenerateModalOpen] = useState<boolean>(false);
  const [casePickerMode, setCasePickerMode] = useState<'dry-run' | 'draft' | null>(null);
  const [branchPickerMode, setBranchPickerMode] = useState<'dry-run' | 'draft' | null>(null);
  const [userPreviewMode, setUserPreviewMode] = useState<PreviewMode | null>(null);
  const [previewWidthPct, setPreviewWidthPct] = useState<number>(DEFAULT_PREVIEW_WIDTH_PCT);
  const [isDesktop, setIsDesktop] = useState<boolean>(isDesktopViewport);
  const [mobileActivePane, setMobileActivePane] = useState<MobilePane>('workspace');
  const [dryRunPhraseIndex, setDryRunPhraseIndex] = useState<number>(0);
  const [awaitingPicks, setAwaitingPicks] = useState<AwaitingDraftState>(
    emptyAwaitingDraftState
  );
  const [draftAwaitingPicks, setDraftAwaitingPicks] = useState<AwaitingDraftState>(
    emptyAwaitingDraftState
  );
  
  const [isDryRunAwaitingMinimized, setIsDryRunAwaitingMinimized] = useState<boolean>(false);
  const [isDraftAwaitingMinimized, setIsDraftAwaitingMinimized] = useState<boolean>(false);

  useEffect(() => {
    setAwaitingPicks(emptyAwaitingDraftState());
    setIsDryRunAwaitingMinimized(false);
    if (dryRunAwaiting) {
      
      const caseName = cases.find((c) => c.id === dryRunAwaiting.case_id)?.case_name;
      addToast(
        `We need your help verifying information${caseName ? ` for ${caseName}` : ''}`,
        'info'
      );
    }
  }, [dryRunAwaiting?.run_id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setDraftAwaitingPicks(emptyAwaitingDraftState());
    setIsDraftAwaitingMinimized(false);
    if (draftAwaiting) {
      const caseName = cases.find((c) => c.id === draftAwaiting.case_id)?.case_name;
      addToast(
        `We need your help verifying information${caseName ? ` for ${caseName}` : ''}`,
        'info'
      );
    }
  }, [draftAwaiting?.run_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAwaitingSubmit = useCallback(
    async (picks: Parameters<typeof resumeDryRun>[0]) => {
      const result = await resumeDryRun(picks);
      if (!result.success && result.error) {
        addToast(result.error, 'error');
      }
    },
    [resumeDryRun, addToast]
  );

  const handleDraftAwaitingSubmit = useCallback(
    async (picks: Parameters<typeof resumeDraft>[0]) => {
      const result = await resumeDraft(picks);
      if (!result.success && result.error) {
        addToast(result.error, 'error');
      }
    },
    [resumeDraft, addToast]
  );

  useEffect(() => {
    if (!isDryRunning) return;
    setDryRunPhraseIndex(0);
    const id = window.setInterval(() => {
      setDryRunPhraseIndex((i) => (i + 1) % DRY_RUN_PHRASES.length);
    }, 1800);
    return () => window.clearInterval(id);
  }, [isDryRunning]);
  const isResizingRef = useRef<boolean>(false);
  const splitContainerRef = useRef<HTMLDivElement | null>(null);
  const exporterRef = useRef<(() => void) | null>(null);
  const studioMainRef = useRef<HTMLElement | null>(null);

  const handleStudioPointerMove = useCallback((e: React.PointerEvent<HTMLElement>) => {
    const node = studioMainRef.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    node.style.setProperty('--studio-mx', `${e.clientX - rect.left}px`);
    node.style.setProperty('--studio-my', `${e.clientY - rect.top}px`);
    node.style.setProperty('--studio-spotlight', '1');
  }, []);

  const handleStudioPointerLeave = useCallback(() => {
    studioMainRef.current?.style.setProperty('--studio-spotlight', '0');
  }, []);

  useEffect((): (() => void) | void => {
    if (typeof window === 'undefined') return;
    const mq: MediaQueryList = window.matchMedia(DESKTOP_BREAKPOINT_QUERY);
    // Sync immediately so isDesktop reflects the current width on mount (and
    // when the query itself changes), not only on the next breakpoint crossing.
    setIsDesktop(mq.matches);
    const handler = (e: MediaQueryListEvent): void => setIsDesktop(e.matches);
    mq.addEventListener('change', handler);
    return (): void => mq.removeEventListener('change', handler);
  }, []);

  useEffect((): (() => void) => {
    const handleMouseMove = (e: MouseEvent): void => {
      if (!isResizingRef.current || !splitContainerRef.current) return;
      const rect: DOMRect = splitContainerRef.current.getBoundingClientRect();
      const fromRight: number = rect.right - e.clientX;
      const pct: number = (fromRight / rect.width) * 100;
      const clamped: number = Math.max(RESIZE_MIN_PCT, Math.min(RESIZE_MAX_PCT, pct));
      setPreviewWidthPct(clamped);
    };
    const handleMouseUp = (): void => {
      if (!isResizingRef.current) return;
      isResizingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return (): void => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  const startResizing = (): void => {
    isResizingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const setExporter = useCallback((exporter: () => void) => {
    exporterRef.current = exporter;
  }, []);

  const handleExport = () => {
    exporterRef.current?.();
  };

  // Default view is always Template — switching templates shouldn't land
  // the user on a stale dry-run / draft preview restored from local cache.
  // Fresh runs explicitly switch to Draft via `setPreviewMode('draft')` in
  // the run completion handlers below.
  const derivedPreviewMode: PreviewMode = 'template';
  const previewMode: PreviewMode = (() => {
    const candidate = userPreviewMode ?? derivedPreviewMode;
    if (isCompanionPreviewMode(candidate)) {
      const source = draftResult ?? dryRunResult;
      const exists = (source?.children?.length ?? 0) > candidate.index;
      if (!exists) return 'draft';
    }
    return candidate;
  })();
  const setPreviewMode = useCallback((mode: PreviewMode) => {
    setUserPreviewMode(mode);
  }, []);

  useEffect(() => {
    setUserPreviewMode(null);
  }, [selectedTemplateId]);

  useEffect(() => {
    loadCases();
    loadTemplates();
    loadConnectors();
    loadReferenceData();
  }, [loadCases, loadTemplates, loadConnectors, loadReferenceData]);

  useEffect(() => {
    
    if (routeTemplateId) {
      if (routeTemplateId !== selectedTemplateId) {
        void (async () => {
          await selectTemplate(routeTemplateId);
          const latest = useStudioStore.getState();
          const found = latest.templates.find((t) => t.id === routeTemplateId);
          if (!found) {
            addToast('Template not found — it may have been deleted.', 'error');
            navigate('/studio', { replace: true });
          }
        })();
      }
    } else if (selectedTemplateId) {
      resetToNew();
    }
  }, [routeTemplateId, selectedTemplateId, selectTemplate, resetToNew, addToast, navigate]);

  const selectedCase = useMemo(
    () => cases.find((c) => c.id === selectedCaseId) ?? null,
    [cases, selectedCaseId]
  );

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId]
  );

  const [editedName, setEditedName] = useState<string | null>(null);
  const [isEditingName, setIsEditingName] = useState<boolean>(false);

  const templateName = editedName ?? selectedTemplate?.name ?? '';

  useEffect((): void => {
    setEditedName(null);
    setIsEditingName(false);
  }, [selectedTemplateId]);

  const commitNameEdit = async (next: string): Promise<void> => {
    const trimmed = next.trim();
    setIsEditingName(false);
    if (!trimmed || !selectedTemplateId || trimmed === selectedTemplate?.name) {
      setEditedName(null);
      return;
    }
    setEditedName(trimmed);
    const result = await renameTemplate(selectedTemplateId, trimmed);
    if (result.success) {
      addToast('Template renamed', 'success');
      setEditedName(null);
    } else {
      addToast(result.error ?? 'Failed to rename template', 'error');
      setEditedName(null);
    }
  };

  const allVariablesMapped = useMemo(
    () =>
      templateSpec.length > 0 &&
      templateSpec.every((v) => isVariableMapped(v.source, v.source_params)),
    [templateSpec]
  );

  const isChildOnly = bundleRole === 'child_only';
  // Save is enabled when EITHER:
  //   - the spec / bundle config was modified since last commit (isDirty), OR
  //   - the agent_config has never been committed (fresh upload / regenerate).
  // The agentConfig === null case is the one that bit us: after a clean
  // generate-template, templateSpec === savedTemplateSpec so isDirty is
  // false, but agent_config is genuinely uncommitted and Save is the
  // exact action the user needs.
  const needsCommit = agentConfig === null;
  const canSave =
    (isDirty || isBundlingDirty || needsCommit) &&
    templateSpec.length > 0 &&
    !isSaving;
  // Dry-run is allowed for child_only templates — slots resolve to fallback
  // placeholders, the rest of the variables resolve normally so authors can
  // validate the non-slot half before Phase 2 wires up real bundling.
  // Run Draft (writes a real docx to R2 against a real case) stays blocked.
  const canDryRun = allVariablesMapped && !isDryRunning;
  const canDraft = agentConfig !== null && !isDrafting && !isChildOnly;

  const handleSave = async () => {
    const result = await saveConfiguration();
    if (result.success) {
      addToast('Configuration saved', 'success');
      return;
    }
    // Surface the strict-slot-validation gate explicitly — it's the most
    // common save rejection and a generic "Save failed" toast would lose
    // signal. Other failures fall back to the result.error string.
    if (result.code === 'BUNDLE_SLOTS_INCOMPLETE') {
      addToast(result.error ?? 'Bundle slots need configuration', 'warning');
      return;
    }
    if (result.error) {
      addToast(result.error, 'error');
    }
  };

  // Auto-dismiss the "Configuration saved" banner after 5s so it doesn't
  // linger. If the user edits something in the meantime the store clears
  // `justSavedAt` itself.
  useEffect(() => {
    if (justSavedAt === null) return;
    const timer = window.setTimeout(clearJustSavedAt, 5_000);
    return () => window.clearTimeout(timer);
  }, [justSavedAt, clearJustSavedAt]);

  const showSavedBanner =
    justSavedAt !== null && !isDirty && !isBundlingDirty && !isSaving && !needsCommit;

  const openDryRunPicker = (): void => setCasePickerMode('dry-run');
  const openDraftPicker = (): void => setCasePickerMode('draft');
  const closeCasePicker = (): void => setCasePickerMode(null);

  const hasBranchCompanions =
    bundleRole === 'parent' &&
    bundleCompanions.some((c) => c.kind === 'branch');

  const triggerRun = (
    mode: 'dry-run' | 'draft',
    bundlePicks: Record<string, string> | null,
  ): void => {
    if (mode === 'dry-run') {
      void runDryRun(bundlePicks).then((result) => {
        if (result.success) {
          addToast('Dry run complete — draft ready', 'success');
          setPreviewMode('draft');
          if (!isDesktop) setMobileActivePane('preview');
        }
      });
      return;
    }
    void runDraft(bundlePicks).then((result) => {
      if (result.success) {
        addToast('Draft generated', 'success');
        setPreviewMode('draft');
        if (!isDesktop) setMobileActivePane('preview');
      } else if (result.error) {
        addToast(result.error, 'error');
      }
    });
  };

  const handleCasePickerConfirm = (caseId: string): void => {
    const mode = casePickerMode;
    closeCasePicker();
    void caseId;
    if (mode === null) return;
    if (hasBranchCompanions) {
      // Defer the run until the user picks a branch option for each
      // BranchBundleCompanion on the parent. Fixed companions don't
      // need a pick — they always run.
      setBranchPickerMode(mode);
      return;
    }
    triggerRun(mode, null);
  };

  const closeBranchPicker = (): void => setBranchPickerMode(null);

  const handleBranchPickerConfirm = (
    picks: Record<string, string>,
  ): void => {
    const mode = branchPickerMode;
    closeBranchPicker();
    if (mode === null) return;
    triggerRun(mode, picks);
  };

  const moreMenuItems: MenuItemDef[] = [
    { label: 'Constants…', onClick: () => setIsConstantsModalOpen(true) },
    {
      label: 'Regenerate template…',
      onClick: () => setIsRegenerateModalOpen(true),
      disabled: !selectedTemplateId,
    },
    { label: '', separator: true },
    {
      label: 'Reset Workspace',
      onClick: () => navigate('/studio'),
      disabled: !selectedTemplateId,
      danger: true,
    },
  ];

  const [hydratedForTemplateId, setHydratedForTemplateId] = useState<string | null>(null);
  const handleDocumentLoaded = useCallback(() => {
    setHydratedForTemplateId(selectedTemplateId);
  }, [selectedTemplateId]);
  const isHydratingMetadata = Boolean(routeTemplateId) && !selectedTemplateId;
  const isHydratingDocument =
    Boolean(selectedTemplateId) && hydratedForTemplateId !== selectedTemplateId;
  const isHydratingTemplate = isHydratingMetadata || isHydratingDocument;
  const showPreview = Boolean(selectedTemplateId);

  return (
    <SidebarLayout contentClassName="overflow-hidden relative h-full">
      <div ref={splitContainerRef} className="flex h-full w-full flex-col overflow-hidden bg-surface-muted xl:flex-row">
        {!isDesktop && showPreview && (
          <div className="flex shrink-0 items-center justify-center gap-1 border-b border-border bg-surface px-3 py-2 xl:hidden">
            <div className="inline-flex rounded-lg border border-border bg-surface-muted p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setMobileActivePane('workspace')}
                title="Show the variables workspace"
                className={`rounded-md px-3 py-1 font-semibold transition-colors ${
                  mobileActivePane === 'workspace'
                    ? 'bg-surface text-app-accent-text shadow-sm'
                    : 'text-muted'
                }`}
              >
                Workspace
              </button>
              <button
                type="button"
                onClick={() => setMobileActivePane('preview')}
                disabled={!templateDocUrl}
                title={
                  templateDocUrl
                    ? 'Show the document preview'
                    : 'Upload a template first to enable preview'
                }
                className={`rounded-md px-3 py-1 font-semibold transition-colors ${
                  mobileActivePane === 'preview'
                    ? 'bg-surface text-app-accent-text shadow-sm'
                    : 'text-muted disabled:text-subtle'
                }`}
              >
                Preview
              </button>
            </div>
          </div>
        )}

        <main
          ref={studioMainRef}
          onPointerMove={!selectedTemplateId ? handleStudioPointerMove : undefined}
          onPointerLeave={!selectedTemplateId ? handleStudioPointerLeave : undefined}
          className={`relative flex flex-1 flex-col overflow-hidden border-border xl:min-w-[480px] ${
            selectedTemplateId ? 'bg-surface' : 'bg-surface-muted'
          } ${
            showPreview ? 'xl:border-r' : ''
          } ${
            !isDesktop && mobileActivePane !== 'workspace' ? 'hidden' : ''
          }`}
          style={
            !selectedTemplateId
              ? {
                  backgroundImage:
                    'radial-gradient(circle, var(--app-studio-dot) 1px, transparent 1px)',
                  backgroundSize: '16px 16px',
                }
              : undefined
          }
        >
          {!selectedTemplateId && (
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 z-0 transition-opacity duration-300"
              style={{
                backgroundImage:
                  'radial-gradient(circle, var(--app-studio-dot-bright) 1px, transparent 1px)',
                backgroundSize: '16px 16px',
                WebkitMaskImage:
                  'radial-gradient(circle 280px at var(--studio-mx, 50%) var(--studio-my, 50%), black 0%, transparent 70%)',
                maskImage:
                  'radial-gradient(circle 280px at var(--studio-mx, 50%) var(--studio-my, 50%), black 0%, transparent 70%)',
                opacity: 'var(--studio-spotlight, 0)',
              }}
            />
          )}
          <header className="relative z-20 flex shrink-0 flex-col border-b border-border bg-surface/80 backdrop-blur">
            <div className="flex flex-col gap-2 px-3 pt-3 sm:flex-row sm:items-start sm:justify-between sm:gap-3 sm:px-6 sm:pt-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-[10px] font-semibold uppercase tracking-widest text-subtle">
                    {selectedTemplateId ? 'Template' : 'Studio'}
                  </p>
                  {selectedTemplateId && <FlowStatePill state={flowState} />}
                </div>
                {selectedTemplateId ? (
                  <EditableTitle
                    value={templateName || 'Untitled template'}
                    isEditing={isEditingName}
                    onStartEdit={() => setIsEditingName(true)}
                    onCommit={commitNameEdit}
                    onCancel={() => setIsEditingName(false)}
                  />
                ) : (
                  <h1 className="mt-0.5 break-words text-lg font-semibold text-text-secondary sm:text-xl">
                    Template Studio
                  </h1>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {selectedCase && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-app-accent-soft px-2.5 py-1 text-[11px] font-semibold text-app-accent-text">
                    <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                    {selectedCase.case_number}
                  </span>
                )}
                <Tooltip
                  label={
                    isChildOnly
                      ? 'Child-only templates cannot be drafted directly — they only run when a parent template attaches them as a bundle companion.'
                      : !agentConfig
                        ? 'Save configuration before drafting — Run Draft commits the agent against a real case and writes the .docx to R2.'
                        : isDrafting
                          ? 'Draft in progress…'
                          : 'Generate the filled .docx against a selected case. The draft is persisted to R2.'
                  }
                  side="bottom"
                >
                <button
                  type="button"
                  onClick={openDraftPicker}
                  disabled={!canDraft}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isDrafting && <Spinner />}
                  {isDrafting ? 'Drafting…' : 'Run Draft'}
                </button>
                </Tooltip>
              </div>
            </div>
            <div className="mt-2 flex min-h-[2.25rem] items-center gap-1 overflow-x-auto border-t border-border bg-surface-muted/60 px-2 py-1 hide-scrollbar sm:px-4">
              <ToolbarButton
                onClick={() => setIsUploadModalOpen(true)}
                icon={<IconUpload />}
                label="Upload"
                title="Upload a new template (DOCX)"
              />
              <ToolbarButton
                onClick={openDryRunPicker}
                disabled={!canDryRun}
                loading={isDryRunning}
                icon={<IconPlay />}
                label={isDryRunning ? 'Running…' : 'Dry Run'}
                title={
                  !canDryRun
                    ? 'Map every variable to a source first'
                    : isChildOnly
                      ? "Dry-run a child-only template against a case — `inherit_from_parent` slots resolve to fallback placeholders; the rest of your variables (court_drive, system_generated, etc.) resolve normally so you can validate them before Phase 2 wires up real bundling."
                      : 'Preview resolved values against a case'
                }
              />
              <ToolbarButton
                onClick={handleSave}
                disabled={!canSave}
                loading={isSaving}
                icon={<IconSaveDisk />}
                label={isSaving ? 'Saving…' : 'Save'}
                title={
                  !canSave
                    ? 'No changes to save'
                    : needsCommit
                      ? 'Commit configuration — agent_config is not yet persisted'
                      : 'Save configuration'
                }
              />
              <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
              <MenuDropdown
                title="More actions (constants, reset workspace)"
                label={
                  <span className="inline-flex items-center gap-1.5">
                    <IconMore />
                    <span>More</span>
                  </span>
                }
                items={moreMenuItems}
              />
              {isSaving && (
                <span className="ml-2 inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-[10px] font-medium text-muted">
                  <Spinner />
                  Saving…
                </span>
              )}
              {!isSaving && (isDirty || isBundlingDirty || needsCommit) && selectedTemplateId && (
                <span className="ml-2 inline-flex shrink-0 items-center gap-1 whitespace-nowrap text-[10px] font-medium text-app-warning-text">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                  {needsCommit && !(isDirty || isBundlingDirty)
                    ? 'Not yet saved'
                    : 'Unsaved changes'}
                </span>
              )}
            </div>
          </header>

          <div className="relative z-10 flex-1 overflow-y-auto p-6">
            {error && (
              <div className="mb-4 flex items-start justify-between gap-3 rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
                <span>{error}</span>
                <button
                  type="button"
                  onClick={clearError}
                  className="shrink-0 text-xs text-red-500 underline"
                >
                  dismiss
                </button>
              </div>
            )}

            {dryRunAwaiting && isDryRunAwaitingMinimized && (
              <AwaitingInputBanner
                kind="dry-run"
                caseName={
                  cases.find((c) => c.id === dryRunAwaiting.case_id)?.case_name ?? null
                }
                pendingCount={Object.keys(dryRunAwaiting.pending_inputs).length}
                onContinue={() => setIsDryRunAwaitingMinimized(false)}
                onDiscard={dismissDryRunAwaiting}
              />
            )}
            {draftAwaiting && isDraftAwaitingMinimized && (
              <AwaitingInputBanner
                kind="draft"
                caseName={
                  cases.find((c) => c.id === draftAwaiting.case_id)?.case_name ?? null
                }
                pendingCount={Object.keys(draftAwaiting.pending_inputs).length}
                onContinue={() => setIsDraftAwaitingMinimized(false)}
                onDiscard={dismissDraftAwaiting}
              />
            )}

            {selectedTemplateId && regenerateDiff && (
              <div className="mb-4">
                <RegenerateDiffSummary
                  diff={regenerateDiff}
                  onDismiss={clearRegenerateDiff}
                />
              </div>
            )}

            {selectedTemplateId && showSavedBanner && (
              <div
                role="status"
                aria-live="polite"
                className="mb-4 flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
              >
                <LuCircleCheck
                  className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600"
                  aria-hidden="true"
                />
                <div className="flex-1">
                  <p className="font-semibold">Configuration saved</p>
                  <p className="mt-0.5 text-xs text-emerald-800">
                    Template spec and bundle settings are now persisted. Dry-run and Draft will use the saved config on the next run.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={clearJustSavedAt}
                  aria-label="Dismiss"
                  className="shrink-0 rounded-md p-1 text-emerald-700 transition-colors hover:bg-emerald-100"
                >
                  <LuX className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            )}
            {selectedTemplateId && (isDirty || isBundlingDirty || needsCommit) && !isSaving && (
              <div className="mb-4 flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 sm:flex-row sm:items-start">
                <div className="flex flex-1 items-start gap-3">
                <svg
                  className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
                  />
                </svg>
                <div className="flex-1">
                  <p className="font-semibold">
                    {needsCommit && !(isDirty || isBundlingDirty)
                      ? 'Configuration not yet saved'
                      : 'Unsaved changes'}
                  </p>
                  <p className="mt-0.5 text-xs text-amber-800">
                    {needsCommit && !(isDirty || isBundlingDirty)
                      ? 'This template has no committed agent_config yet — Run Draft is blocked until you save.'
                      : isDirty && isBundlingDirty
                        ? 'Template spec and bundle settings have been modified but not yet saved.'
                        : isDirty
                          ? 'Template spec has been modified but not yet saved.'
                          : 'Bundle settings have been modified but not yet saved.'}
                    {' '}Click <span className="font-semibold">Save Configuration</span> to commit; dry-run already uses the in-memory config.
                  </p>
                </div>
                </div>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={!canSave}
                  className="shrink-0 self-start rounded-md border border-amber-300 bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-900 hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save now
                </button>
              </div>
            )}

            {selectedTemplateId ? (
              <div className="space-y-4">
                <CollapsibleSection
                  title="Bundle Settings"
                  description="Role of this template in the bundling system, plus (when role is parent) the companion child templates and their slot filling. Configure this first — it changes which sources are available to your variables below."
                  isOpen={isBundlingOpen}
                  onToggle={() => setIsBundlingOpen((v) => !v)}
                >
                  <TemplateBundleSettings />
                </CollapsibleSection>

                <CollapsibleSection
                  title="Template Spec"
                  description="Variables extracted from the docx + their source/instruction config."
                  isOpen={isSpecOpen}
                  onToggle={() => setIsSpecOpen((v) => !v)}
                >
                  <VariablesWorkspace />
                </CollapsibleSection>
              </div>
            ) : isHydratingTemplate ? (
              <div className="flex h-full flex-col items-center justify-center">
                <div className="flex max-w-md flex-col items-center gap-3 rounded-2xl border border-border bg-surface px-8 py-8 text-center text-muted shadow-sm">
                  <Lottie
                    animationData={templateLoadingAnimation}
                    loop
                    autoplay
                    className="h-32 w-full max-w-[180px]"
                  />
                  <p className="text-sm font-semibold text-text-secondary">
                    Loading template…
                  </p>
                  <p className="text-xs text-muted">
                    Hydrating this template's variables and document. Just a moment.
                  </p>
                </div>
              </div>
            ) : (
              <StudioTemplateUploader
                onUploadSuccess={(newTemplateId) => {
                  addToast('Template uploaded', 'success');
                  setPreviewMode('template');
                  if (!isDesktop) setMobileActivePane('preview');
                  navigate(`/studio/template/${newTemplateId}`, { replace: true });
                }}
              />
            )}
          </div>
        </main>

        {isDesktop && showPreview && (
          <div
            onMouseDown={startResizing}
            className="hidden w-1 shrink-0 cursor-col-resize bg-border transition-colors hover:bg-indigo-300 xl:block"
            role="separator"
            aria-orientation="vertical"
            title="Drag to resize"
          />
        )}

        {showPreview && (
        <aside
          style={isDesktop ? { width: `${previewWidthPct}%` } : undefined}
          className={`flex flex-1 flex-col overflow-hidden bg-surface-muted xl:flex-none xl:min-w-[620px] ${
            !isDesktop && mobileActivePane !== 'preview' ? 'hidden' : ''
          }`}
        >
          <header className="flex shrink-0 flex-col border-b border-border bg-surface">
            <div className="flex items-start justify-between gap-3 px-3 pt-3 sm:px-6 sm:pt-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="py-0.5 text-[10px] font-semibold uppercase tracking-widest text-subtle">
                    Preview
                  </p>
                </div>
                <h2 className="mt-0.5 break-words text-lg font-semibold leading-snug text-text-secondary sm:text-xl">
                  Document Preview
                </h2>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={!templateDocUrl}
                  title={
                    templateDocUrl
                      ? 'Download the currently previewed document as a .docx file'
                      : 'No document to export yet'
                  }
                  className="inline-flex items-center gap-1.5 rounded-lg border border-app-accent-soft bg-surface px-3 py-1.5 text-xs font-semibold text-app-accent-text hover:bg-app-accent-soft disabled:cursor-not-allowed disabled:border-border disabled:text-subtle disabled:hover:bg-surface"
                >
                  <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3"
                    />
                  </svg>
                  Export DOCX
                </button>
              </div>
            </div>
            <div className="mt-2 flex min-h-[2.25rem] items-center gap-1 border-t border-border bg-surface-muted/60 px-2 py-1 sm:px-4">
              <div className="inline-flex flex-wrap gap-1 rounded-lg border border-border bg-surface p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setPreviewMode('template')}
                  title="Show the raw uploaded template with placeholder variables"
                  className={`rounded-md px-3 py-1 font-semibold transition-colors ${
                    previewMode === 'template'
                      ? 'bg-surface-muted text-app-accent-text shadow-sm'
                      : 'text-muted hover:text-text-secondary'
                  }`}
                >
                  Template
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewMode('original')}
                  disabled={!originalDocUrl}
                  title={
                    originalDocUrl
                      ? 'Show the original uploaded .docx (pre-extraction source)'
                      : 'No original source available yet'
                  }
                  className={`rounded-md px-3 py-1 font-semibold transition-colors ${
                    previewMode === 'original'
                      ? 'bg-surface-muted text-app-accent-text shadow-sm'
                      : 'text-muted hover:text-text-secondary disabled:cursor-not-allowed disabled:text-subtle disabled:hover:text-subtle'
                  }`}
                >
                  Original
                </button>
                <button
                  type="button"
                  onClick={() => setPreviewMode('draft')}
                  disabled={!dryRunResult && !draftResult}
                  title={
                    dryRunResult || draftResult
                      ? 'Show the most recent draft with values filled in'
                      : 'Run a dry run or draft first to see filled values'
                  }
                  className={`rounded-md px-3 py-1 font-semibold transition-colors ${
                    previewMode === 'draft'
                      ? 'bg-surface-muted text-app-accent-text shadow-sm'
                      : 'text-muted hover:text-text-secondary disabled:cursor-not-allowed disabled:text-subtle disabled:hover:text-subtle'
                  }`}
                >
                  Draft
                </button>
                {(() => {
                  const source = draftResult ?? dryRunResult;
                  const children = source?.children ?? [];
                  return children.map((child, index) => {
                    const isPicked =
                      isCompanionPreviewMode(previewMode) && previewMode.index === index;
                    return (
                      <button
                        key={`${child.template_id}-${index}`}
                        type="button"
                        onClick={() => setPreviewMode({ kind: 'companion', index })}
                        title={`${child.template_name} — ${child.companion_label}`}
                        className={`flex items-center gap-1 rounded-md px-3 py-1 font-semibold transition-colors ${
                          isPicked
                            ? 'bg-surface-muted text-app-accent-text shadow-sm'
                            : 'text-muted hover:text-text-secondary'
                        }`}
                      >
                        <span className="max-w-[12rem] truncate">{child.template_name}</span>
                      </button>
                    );
                  });
                })()}
              </div>
            </div>
          </header>
          <div className="relative flex-1 overflow-hidden bg-surface">
            {selectedTemplateId && (
              <TemplatePreview
                mode={previewMode}
                onExport={setExporter}
                suppressLoadingOverlay={isHydratingTemplate}
                onDocumentLoaded={handleDocumentLoaded}
              />
            )}
            {isHydratingTemplate && (
              <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 bg-surface px-8 text-center">
                <Lottie
                  animationData={templateLoadingAnimation}
                  loop
                  autoplay
                  className="h-56 w-full max-w-sm"
                />
                <p className="text-base font-semibold text-text-secondary">
                  Loading template…
                </p>
                <p className="max-w-md text-sm text-muted">
                  Pulling in this template's variables and document. Just a moment.
                </p>
              </div>
            )}
          </div>
        </aside>
        )}
      </div>

      {isDryRunning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay backdrop-blur-sm">
          <div className="relative flex w-full max-w-xl flex-col items-center gap-4 rounded-2xl border border-app-accent-soft bg-surface px-8 py-8 shadow-2xl">
            <button
              type="button"
              disabled
              title="Dry run is in progress — please wait."
              className="absolute right-4 top-4 cursor-not-allowed rounded-lg p-1 text-subtle opacity-40"
              aria-label="Close"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <Lottie
              animationData={dryRunAnimation}
              loop
              autoplay
              className="h-64 w-full"
            />
            <p
              key={dryRunPhraseIndex}
              className="animate-verb-in text-xl font-semibold text-text-secondary"
            >
              {DRY_RUN_PHRASES[dryRunPhraseIndex][0]}{' '}
              {DRY_RUN_PHRASES[dryRunPhraseIndex][1]}
              {selectedCase ? ` for ${selectedCase.case_number}` : ''}…
            </p>
            <p className="text-sm text-muted">
              {selectedCase ? `Running the draft agent against ${selectedCase.case_number}.` : 'Running the draft agent.'}
            </p>
          </div>
        </div>
      )}
      <UploadTemplateModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUploadSuccess={(newTemplateId) => {
          addToast('Template uploaded', 'success');
          setPreviewMode('template');
          if (!isDesktop) setMobileActivePane('preview');
          navigate(`/studio/template/${newTemplateId}`, { replace: true });
        }}
      />
      <ConstantsModal
        isOpen={isConstantsModalOpen}
        onClose={() => setIsConstantsModalOpen(false)}
      />
      <RegenerateTemplateModal
        isOpen={isRegenerateModalOpen}
        onClose={() => setIsRegenerateModalOpen(false)}
      />
      <CaseSelectionModal
        isOpen={casePickerMode !== null}
        title={casePickerMode === 'draft' ? 'Run Draft against case' : 'Dry Run against case'}
        confirmLabel={casePickerMode === 'draft' ? 'Run Draft' : 'Run Dry Run'}
        isRunning={casePickerMode === 'draft' ? isDrafting : isDryRunning}
        onClose={closeCasePicker}
        onConfirm={handleCasePickerConfirm}
      />
      <BranchPickerModal
        isOpen={branchPickerMode !== null}
        title={
          branchPickerMode === 'draft'
            ? 'Configure draft companions'
            : 'Configure dry-run companions'
        }
        confirmLabel={
          branchPickerMode === 'draft' ? 'Run Draft' : 'Run Dry Run'
        }
        isRunning={branchPickerMode === 'draft' ? isDrafting : isDryRunning}
        bundleCompanions={bundleCompanions}
        onClose={closeBranchPicker}
        onConfirm={handleBranchPickerConfirm}
      />
      <AwaitingInputModal
        isOpen={dryRunAwaiting !== null && !isDryRunAwaitingMinimized}
        awaiting={dryRunAwaiting}
        picks={awaitingPicks}
        onPicksChange={setAwaitingPicks}
        isSubmitting={isDryRunning}
        onCancel={() => setIsDryRunAwaitingMinimized(true)}
        onSubmit={handleAwaitingSubmit}
      />
      <AwaitingInputModal
        isOpen={draftAwaiting !== null && !isDraftAwaitingMinimized}
        awaiting={draftAwaiting}
        picks={draftAwaitingPicks}
        onPicksChange={setDraftAwaitingPicks}
        isSubmitting={isDrafting}
        onCancel={() => setIsDraftAwaitingMinimized(true)}
        onSubmit={handleDraftAwaitingSubmit}
      />
    </SidebarLayout>
  );
};

export default StudioPage;
