import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import Lottie from 'lottie-react';
import { LuFilePlus, LuX } from 'react-icons/lu';
import petitionLoadingAnimation from '@/assets/lottie/upload-search.json';
import { NewCaseTabs } from '@/components/case/NewCaseTabs';
import { MessageList } from '@/components/draft-v2/chat/MessageList';
import { TemplateDraftBranchPickerModal } from '@/components/draft-v2/TemplateDraftBranchPickerModal';
import { TemplateDraftCancelConfirmModal } from '@/components/draft-v2/TemplateDraftCancelConfirmModal';
import { TemplateDraftDocumentViewer } from '@/components/draft-v2/TemplateDraftDocumentViewer';
import { TemplateDraftExistingModal } from '@/components/draft-v2/TemplateDraftExistingModal';
import { TemplateDraftInputModal } from '@/components/draft-v2/TemplateDraftInputModal';
import { TemplateDraftModal } from '@/components/draft-v2/TemplateDraftModal';
import { TemplateDraftStatusStrip } from '@/components/draft-v2/TemplateDraftStatusStrip';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { PDFViewer } from '@/components/pdf/PDFViewer';
import {
  startTemplateDraftEventStream,
  stopTemplateDraftEventStream,
} from '@/services/templateDraftEvents.service';
import { useAuthSession } from '@/features/auth/queries';
import { EMPTY_CASE_CHAT_SLICE, useCaseChatStore } from '@/stores/useCaseChatStore';
import { EMPTY_PDF_SLICE, usePDFStore } from '@/stores/usePDFStore';
import { useStudioStore } from '@/stores/useStudioStore';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import { useToastStore } from '@/stores/useToastStore';
import { useUIStore } from '@/stores/useUIStore';
import { useWorkspaceSplitStore } from '@/stores/useWorkspaceSplitStore';
import { formatCaseName } from '@/utils/studio';

/**
 * Draft v2 — case-drafting workspace with agentic chat.
 *
 * Layout: status strip + 1 or 2 CaseWorkspacePane(s) side-by-side. Each
 * pane is a full case workspace (header + chat/pdf/split toggle +
 * composer) with its own independent state.
 *
 * Split-screen UX: drag a case row from the sidebar onto the workspace
 * to open the dropped case in a right pane. Drop on an existing pane to
 * replace its case. The left pane is URL-bound (`/case/:caseId`); the
 * right pane lives in component state (in-memory only, no reload
 * persistence).
 */

type View = 'chat' | 'pdf' | 'split';

const SIDEBAR_CASE_MIME = 'text/plain';

const buildPdfCacheKey = (caseId: string): string => `case-${caseId}`;

interface PaneHeaderProps {
  caseId: string;
  view: View;
  onViewChange: (next: View) => void;
  onClose?: () => void;
}

const PaneHeader: React.FC<PaneHeaderProps> = ({ caseId, view, onViewChange, onClose }) => {
  const selectedCase = useStudioStore((s) => s.cases.find((c) => c.id === caseId) ?? null);

  let title: string;
  let subtitle: string;
  if (selectedCase) {
    title = formatCaseName(selectedCase.case_name);
    subtitle = selectedCase.case_number;
  } else {
    title = 'Loading case…';
    subtitle = '';
  }

  return (
    <div className="flex items-center justify-between gap-3 border-b border-border bg-surface px-3 py-1.5">
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-text-secondary">{title}</p>
        <p className="truncate text-xs text-muted">{subtitle}</p>
      </div>
      <div className="flex items-center gap-2">
        <div className="inline-flex items-center rounded-full border border-border bg-surface p-0.5 shadow-sm">
          {(['chat', 'pdf', 'split'] as const).map((kind) => (
            <button
              key={kind}
              type="button"
              onClick={() => onViewChange(kind)}
              className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors ${
                view === kind
                  ? 'bg-app-accent-soft text-app-accent-text shadow-sm'
                  : 'text-muted hover:text-text-secondary'
              }`}
            >
              {kind}
            </button>
          ))}
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close split pane"
            title="Close split pane"
            className="inline-flex h-7 w-7 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-muted hover:text-text-secondary"
          >
            <LuX className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
};

const NewCaseHeader: React.FC = () => (
  <div className="flex items-center justify-between gap-3 border-b border-border bg-surface px-3 py-1.5">
    <div className="min-w-0">
      <p className="truncate text-sm font-semibold text-text-secondary">Untitled</p>
      <p className="truncate text-xs text-muted">New case — upload the petition to begin.</p>
    </div>
  </div>
);

interface SlashTemplate {
  id: string;
  name: string;
}

interface ComposerProps {
  caseId: string;
}

const Composer: React.FC<ComposerProps> = ({ caseId }) => {
  const [draft, setDraft] = useState<string>('');
  const [isMotionsModalOpen, setIsMotionsModalOpen] = useState<boolean>(false);
  const [slashStart, setSlashStart] = useState<number | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(0);

  const addToast = useToastStore((s) => s.addToast);
  const templates = useStudioStore((s) => s.templates);
  const startDraft = useTemplateDraftStore((s) => s.startDraft);
  const openBranchPicker = useTemplateDraftStore((s) => s.openBranchPicker);
  const chatSlice = useCaseChatStore((s) => s.byCase[caseId] ?? EMPTY_CASE_CHAT_SLICE);
  const sendChatMessage = useCaseChatStore((s) => s.sendMessage);
  const cancelChatStream = useCaseChatStore((s) => s.cancelStream);
  const chatSession = chatSlice.session;
  const isChatStreaming = chatSlice.isStreaming;

  // Production-ready templates: agent_config saved, active, not child-only.
  const productionTemplates: SlashTemplate[] = useMemo(
    () =>
      templates
        .filter(
          (t) =>
            t.agent_config !== null &&
            t.is_active &&
            t.bundle_role !== 'child_only',
        )
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((t) => ({ id: t.id, name: t.name })),
    [templates],
  );

  // Slash query = everything typed after the `/`. Spaces are part of the
  // query so "/ex parte motion" filters templates by the full phrase.
  // Slash mode is a takeover: once active, the entire trailing input is
  // the command. User exits via Esc, Backspace past the `/`, or by
  // selecting a template.
  const slashQuery = useMemo(() => {
    if (slashStart === null) return null;
    return draft.slice(slashStart + 1);
  }, [draft, slashStart]);

  const isSlashActive = slashQuery !== null;

  const filteredSlash = useMemo(() => {
    if (!isSlashActive) return [];
    const q = (slashQuery ?? '').toLowerCase();
    return productionTemplates.filter((t) => t.name.toLowerCase().includes(q));
  }, [productionTemplates, slashQuery, isSlashActive]);

  // Reset highlight whenever the filtered list changes.
  useEffect(() => {
    setHighlightedIndex(0);
  }, [filteredSlash.length, isSlashActive]);

  const closeSlash = (): void => setSlashStart(null);

  const fireGenerateNoop = (template: SlashTemplate): void => {
    if (!caseId) {
      addToast('Select a case before drafting.', 'warning');
      return;
    }
    setDraft('');
    closeSlash();

    // Branch-companion pre-flight: look the full template up so we can read
    // its bundle_companions list.
    const fullTemplate = templates.find((t) => t.id === template.id);
    const branchCount = (fullTemplate?.bundle_companions ?? []).filter(
      (c) => c.kind === 'branch',
    ).length;
    if (fullTemplate?.bundle_role === 'parent' && branchCount > 0) {
      openBranchPicker({
        templateId: template.id,
        caseId,
        templateName: template.name,
        companions: fullTemplate.bundle_companions ?? [],
      });
      return;
    }

    addToast(`Drafting ${template.name}…`, 'info');
    void (async () => {
      const result = await startDraft(
        {
          template_id: template.id,
          case_id: caseId,
          bundle_picks: null,
        },
        { templateNameHint: template.name },
      );
      if (result.success) return;
      if (result.code === 'DUPLICATE_DRAFT_IN_FLIGHT') {
        addToast(result.error ?? 'A draft is already running for this template.', 'warning');
        return;
      }
      addToast(result.error ?? 'Failed to start draft', 'error');
    })();
  };

  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>): void => {
    const value = event.target.value;
    const cursor = event.target.selectionStart;
    setDraft(value);

    // Currently active: close if the `/` was deleted or cursor moved before it.
    if (slashStart !== null) {
      if (cursor <= slashStart || value[slashStart] !== '/') {
        setSlashStart(null);
      }
      return;
    }

    // Not active: detect a newly-typed `/` at start-of-string or after whitespace.
    if (cursor > 0 && value[cursor - 1] === '/') {
      const charBefore = cursor >= 2 ? value[cursor - 2] : '';
      if (charBefore === '' || /\s/.test(charBefore)) {
        setSlashStart(cursor - 1);
      }
    }
  };

  const submitChatMessage = (): void => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    if (!chatSession) {
      addToast('Chat session is not ready yet.', 'warning');
      return;
    }
    if (isChatStreaming) return;
    setDraft('');
    void sendChatMessage(caseId, trimmed);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (isSlashActive) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setHighlightedIndex((index) => Math.min(index + 1, Math.max(filteredSlash.length - 1, 0)));
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        setHighlightedIndex((index) => Math.max(index - 1, 0));
      } else if (event.key === 'Enter' && !event.shiftKey) {
        if (filteredSlash.length > 0) {
          event.preventDefault();
          const picked = filteredSlash[highlightedIndex] ?? filteredSlash[0];
          if (picked) fireGenerateNoop(picked);
        }
      } else if (event.key === 'Escape') {
        event.preventDefault();
        closeSlash();
      } else if (event.key === 'Tab' && filteredSlash.length > 0) {
        event.preventDefault();
        const picked = filteredSlash[highlightedIndex] ?? filteredSlash[0];
        if (picked) fireGenerateNoop(picked);
      }
      return;
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submitChatMessage();
    }
  };

  return (
    <div className="border-t border-border bg-surface px-6 py-4">
      <div className="relative mx-auto max-w-3xl">
        {isSlashActive && (
          <div
            role="listbox"
            aria-label="Template slash menu"
            className="absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-xl border border-border bg-surface shadow-[0_18px_42px_-18px_rgba(15,23,42,0.28)]"
          >
            <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-muted/60 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
              <span>Documents available to draft</span>
              <span className="shrink-0">
                {filteredSlash.length} {filteredSlash.length === 1 ? 'match' : 'matches'}
                {slashQuery ? ` for "${slashQuery}"` : ''}
              </span>
            </div>
            {filteredSlash.length === 0 ? (
              <div className="px-3 py-4 text-center text-xs text-muted">
                No documents match. Open Template Studio to publish one.
              </div>
            ) : (
              <ul className="max-h-64 overflow-y-auto py-1">
                {filteredSlash.map((t, index) => {
                  const isHighlighted = index === highlightedIndex;
                  return (
                    <li key={t.id}>
                      <button
                        type="button"
                        // onMouseDown (not onClick) fires before textarea blur,
                        // so the click registers even though the textarea is
                        // about to lose focus.
                        onMouseDown={(event) => {
                          event.preventDefault();
                          fireGenerateNoop(t);
                        }}
                        onMouseEnter={() => setHighlightedIndex(index)}
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
                          isHighlighted
                            ? 'bg-app-accent-soft text-app-accent-text'
                            : 'text-text-secondary hover:bg-surface-muted'
                        }`}
                      >
                        <LuFilePlus
                          className={`h-4 w-4 shrink-0 ${
                            isHighlighted ? 'text-app-accent-text' : 'text-muted'
                          }`}
                          aria-hidden="true"
                        />
                        <span className="flex-1 truncate font-medium">{t.name}</span>
                        {isHighlighted && (
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
                            ⏎
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="flex items-center justify-between border-t border-border bg-surface-muted/40 px-3 py-1 text-[10px] text-subtle">
              <span>↑↓ navigate · ⏎ select · esc close</span>
              <span className="font-mono">/{slashQuery}</span>
            </div>
          </div>
        )}

        {isSlashActive && (
          <div
            className="mb-2 flex items-center justify-between gap-3 rounded-lg border border-app-accent-soft bg-app-accent-soft/40 px-3 py-2"
            role="status"
            aria-live="polite"
          >
            <div className="flex min-w-0 items-center gap-2">
              <span className="inline-flex items-center rounded-md bg-app-accent-soft px-2 py-0.5 font-mono text-xs font-semibold text-app-accent-text">
                /
              </span>
              <span className="truncate text-xs font-medium text-app-accent-text">
                {slashQuery || (
                  <span className="italic text-app-accent-text/70">
                    keep typing to filter — spaces allowed
                  </span>
                )}
              </span>
              <span className="inline-block h-3 w-px animate-pulse bg-app-accent-text" aria-hidden="true" />
            </div>
            <button
              type="button"
              onClick={closeSlash}
              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-app-accent-text/80 hover:bg-app-accent-soft hover:text-app-accent-text"
              title="Exit template mode (Esc)"
              aria-label="Exit template mode"
            >
              <span>Esc</span>
              <span aria-hidden="true">×</span>
            </button>
          </div>
        )}

        <div
          className={`flex items-end gap-2 rounded-xl border bg-surface px-4 py-3 shadow-sm transition-colors ${
            isSlashActive
              ? 'border-app-accent ring-2 ring-app-accent-soft'
              : 'border-border focus-within:border-app-accent focus-within:ring-2 focus-within:ring-app-accent-soft'
          }`}
        >
          <textarea
            rows={1}
            value={draft}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={
              isSlashActive
                ? 'Type to filter documents — spaces allowed'
                : 'Message the assistant — type / to draft from a template'
            }
            className="min-h-[24px] max-h-32 flex-1 resize-none bg-transparent text-sm text-text-secondary placeholder:text-subtle focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setIsMotionsModalOpen(true)}
            aria-haspopup="dialog"
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-md border border-app-accent-soft px-3 text-xs font-semibold text-app-accent-text transition-colors hover:bg-app-accent-soft focus:outline-none focus-visible:ring-2 focus-visible:ring-app-accent-soft"
          >
            <LuFilePlus className="h-4 w-4" aria-hidden="true" />
            Draft pleadings
          </button>
          {isChatStreaming ? (
            <button
              type="button"
              onClick={() => cancelChatStream(caseId)}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-rose-600 text-white shadow-sm transition hover:bg-rose-700"
              title="Stop"
              aria-label="Stop assistant"
            >
              <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="1.5" />
              </svg>
            </button>
          ) : (
            <button
              type="button"
              onClick={submitChatMessage}
              disabled={!draft.trim() || !chatSession || isSlashActive}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-indigo-600 text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
              title="Send"
              aria-label="Send message"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>
      <TemplateDraftModal
        isOpen={isMotionsModalOpen}
        onClose={() => setIsMotionsModalOpen(false)}
      />
      <TemplateDraftInputModal />
      <TemplateDraftExistingModal />
      <TemplateDraftDocumentViewer />
      <TemplateDraftCancelConfirmModal />
      <TemplateDraftBranchPickerModal />
    </div>
  );
};

const PDFEmptyState: React.FC<{ message: string }> = ({ message }) => (
  <div className="flex h-full flex-col items-center justify-center gap-3 bg-page p-6 text-center">
    <div className="aspect-[8.5/11] w-full max-w-sm rounded-md border border-dashed border-border bg-surface" />
    <p className="text-sm font-medium text-text-secondary">Petition PDF</p>
    <p className="text-xs text-muted">{message}</p>
  </div>
);

interface PDFPaneProps {
  caseId: string;
}

const PDFPane: React.FC<PDFPaneProps> = ({ caseId }) => {
  const pdfKey = buildPdfCacheKey(caseId);
  const selectedCase = useStudioStore((s) => s.cases.find((c) => c.id === caseId) ?? null);
  const slice = usePDFStore((s) => s.byKey[pdfKey] ?? EMPTY_PDF_SLICE);
  const { isLoadingPDF, pdf: currentPDF } = slice;

  if (isLoadingPDF) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-page px-8 text-center">
        <Lottie
          animationData={petitionLoadingAnimation}
          loop
          autoplay
          className="h-56 w-full max-w-sm"
        />
        <p className="text-base font-semibold text-text-secondary">Loading petition…</p>
        <p className="max-w-md text-sm text-muted">Parsing the PDF. Just a moment.</p>
      </div>
    );
  }
  if (!selectedCase?.petition_pdf_url || !currentPDF) {
    return <PDFEmptyState message="Could not load this petition. Try selecting the case again." />;
  }
  return <PDFViewer pdfKey={pdfKey} />;
};

interface ChatPaneProps {
  caseId: string;
}

const ChatPane: React.FC<ChatPaneProps> = ({ caseId }) => {
  const slice = useCaseChatStore((s) => s.byCase[caseId] ?? EMPTY_CASE_CHAT_SLICE);
  return (
    <div className="flex h-full flex-col bg-page">
      {slice.error && (
        <div className="border-b border-rose-300 bg-rose-50 px-6 py-2 text-xs text-rose-800">
          {slice.error}
        </div>
      )}
      <MessageList messages={slice.messages} isLoadingHistory={slice.isLoadingHistory} />
      <Composer caseId={caseId} />
    </div>
  );
};

interface CaseWorkspacePaneProps {
  caseId: string;
  /** Primary = URL-bound left pane. Drives `studioStore.selectedCaseId`. */
  isPrimary: boolean;
  /** Whether the secondary pane is currently rendered. Affects the drop label. */
  hasSplit: boolean;
  onClose?: () => void;
  onCaseDropped: (caseId: string, target: 'primary' | 'secondary') => void;
}

const CaseWorkspacePane: React.FC<CaseWorkspacePaneProps> = ({
  caseId,
  isPrimary,
  hasSplit,
  onClose,
  onCaseDropped,
}) => {
  const [view, setView] = useState<View>('chat');
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const dragDepthRef = useRef<number>(0);

  const cases = useStudioStore((s) => s.cases);
  const refreshCasePetitionUrl = useStudioStore((s) => s.refreshCasePetitionUrl);
  const loadPDFFromUrl = usePDFStore((s) => s.loadPDFFromUrl);
  const clearPDF = usePDFStore((s) => s.clearPDF);
  const loadOrCreateChatSession = useCaseChatStore((s) => s.loadOrCreateSession);
  const setFocusedPane = useWorkspaceSplitStore((s) => s.setFocusedPane);
  const { user: authUser } = useAuthSession();

  const paneRole: 'primary' | 'secondary' = isPrimary ? 'primary' : 'secondary';
  const markFocused = useCallback(() => {
    setFocusedPane(paneRole);
  }, [paneRole, setFocusedPane]);

  // Chat-session lifecycle: resolve or auto-create the canonical session
  // for (user, case) on selection, then hydrate history.
  useEffect(() => {
    if (!authUser?.id) return;
    if (!caseId || caseId.startsWith('untitled-')) return;
    void loadOrCreateChatSession(caseId);
  }, [authUser?.id, caseId, loadOrCreateChatSession]);

  // Drive the PDF viewer's slice for this case. Pre-signed URLs are
  // re-signed on a 1h TTL — if loadPDFFromUrl fails, re-sign once via
  // `refreshCasePetitionUrl` and retry. Cache key is namespaced under
  // `case-` so it never collides with session-keyed entries.
  useEffect(() => {
    if (!caseId || caseId.startsWith('untitled-')) {
      return;
    }
    const selectedCase = cases.find((c) => c.id === caseId);
    const petitionUrl = selectedCase?.petition_pdf_url;
    const pdfKey = buildPdfCacheKey(caseId);
    if (!petitionUrl) {
      clearPDF(pdfKey);
      return;
    }
    let cancelled = false;
    const displayName = `Petition — ${caseId}`;
    void (async () => {
      const ok = await loadPDFFromUrl(pdfKey, petitionUrl, displayName);
      if (ok || cancelled) return;
      // Fallback: probably an expired pre-signed URL. Re-sign + retry once.
      const fresh = await refreshCasePetitionUrl(caseId);
      if (cancelled || !fresh) return;
      await loadPDFFromUrl(pdfKey, fresh, displayName);
    })();
    return () => {
      cancelled = true;
    };
  }, [caseId, cases, loadPDFFromUrl, clearPDF, refreshCasePetitionUrl]);

  // Cleanup of orphaned chat/PDF slices is intentionally NOT done on
  // unmount — pane caseId changes (e.g. swapping left↔right) remount
  // this component, and an unmount cleanup would wipe state we're
  // about to need on the other side. The page-level × button does the
  // cleanup explicitly when the user closes the secondary pane.

  const handleDragEnter = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer.types.includes(SIDEBAR_CASE_MIME)) return;
    dragDepthRef.current += 1;
    setIsDragOver(true);
  }, []);

  const handleDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    if (!event.dataTransfer.types.includes(SIDEBAR_CASE_MIME)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const handleDragLeave = useCallback(() => {
    dragDepthRef.current = Math.max(dragDepthRef.current - 1, 0);
    if (dragDepthRef.current === 0) setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      dragDepthRef.current = 0;
      setIsDragOver(false);
      const droppedId = event.dataTransfer.getData(SIDEBAR_CASE_MIME);
      if (!droppedId) return;
      // Only treat as a case drop if the id resolves to a real case;
      // ignores the sidebar's own row-reorder drags that bubble out.
      if (!cases.some((c) => c.id === droppedId)) return;
      onCaseDropped(droppedId, isPrimary ? 'primary' : 'secondary');
    },
    [cases, isPrimary, onCaseDropped],
  );

  return (
    <div
      className="relative flex h-full min-w-0 flex-1 flex-col"
      onPointerDownCapture={markFocused}
      onFocusCapture={markFocused}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <PaneHeader
        caseId={caseId}
        view={view}
        onViewChange={setView}
        onClose={onClose}
      />
      <div className="min-h-0 flex-1">
        {view === 'chat' && <ChatPane caseId={caseId} />}
        {view === 'pdf' && <PDFPane caseId={caseId} />}
        {view === 'split' && (
          <div className="flex h-full">
            <div className="min-w-0 flex-1 border-r border-border">
              <ChatPane caseId={caseId} />
            </div>
            <div className="min-w-0 flex-1">
              <PDFPane caseId={caseId} />
            </div>
          </div>
        )}
      </div>
      {isDragOver && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-2 z-20 flex items-center justify-center rounded-xl border-2 border-dashed border-app-accent bg-app-accent-soft/50 backdrop-blur-[1px]"
        >
          <div className="rounded-full bg-app-accent px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-white shadow-lg">
            {isPrimary && !hasSplit
              ? 'Drop to open in split'
              : 'Drop to replace or swap'}
          </div>
        </div>
      )}
    </div>
  );
};

export const CaseWorkspacePage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { caseId: urlCaseId } = useParams<{ caseId: string }>();
  const isNewCaseRoute = location.pathname === '/case/new';

  // Note: useStudioStore.loadCases() is bootstrapped by DashboardLayout's
  // mount-effect so the RootRedirect at `/` has cases available. The page
  // doesn't refetch on mount — the list is fresh.
  const loadTemplates = useStudioStore((s) => s.loadTemplates);
  const selectedCaseId = useStudioStore((s) => s.selectedCaseId);
  const cases = useStudioStore((s) => s.cases);
  const selectCase = useStudioStore((s) => s.selectCase);
  const pendingCase = useStudioStore((s) => s.pendingCase);
  const startNewCase = useStudioStore((s) => s.startNewCase);
  const submitNewCase = useStudioStore((s) => s.submitNewCase);
  const submitNewCaseByCaseNumber = useStudioStore((s) => s.submitNewCaseByCaseNumber);
  const cancelNewCase = useStudioStore((s) => s.cancelNewCase);
  const addToast = useToastStore((s) => s.addToast);
  const { user: authUser } = useAuthSession();
  const loadActiveTasks = useTemplateDraftStore((s) => s.loadActive);
  const resetAllChat = useCaseChatStore((s) => s.resetAll);
  const resetCaseChat = useCaseChatStore((s) => s.resetCase);
  const clearPDF = usePDFStore((s) => s.clearPDF);

  // Right (secondary) pane lives in a tiny dedicated store so the
  // sidebar can highlight the right-pane case without prop drilling.
  // In-memory only, no URL sync; cleared on reload by design.
  const secondaryCaseId = useWorkspaceSplitStore((s) => s.secondaryCaseId);
  const setSecondaryCaseId = useWorkspaceSplitStore((s) => s.setSecondaryCaseId);
  const closeSecondaryPane = useWorkspaceSplitStore((s) => s.closeSecondary);

  // Auto-collapse the sidebar while the split is open so both panes
  // get more horizontal room. Remember the pre-split collapsed state
  // so we can restore it on close without fighting a user who had the
  // sidebar collapsed already.
  const setSidebarCollapsed = useUIStore((s) => s.setSidebarCollapsed);
  const preSplitSidebarCollapsedRef = useRef<boolean | null>(null);
  useEffect(() => {
    if (secondaryCaseId) {
      if (preSplitSidebarCollapsedRef.current === null) {
        preSplitSidebarCollapsedRef.current = useUIStore.getState().isSidebarCollapsed;
        setSidebarCollapsed(true);
      }
      return;
    }
    if (preSplitSidebarCollapsedRef.current !== null) {
      setSidebarCollapsed(preSplitSidebarCollapsedRef.current);
      preSplitSidebarCollapsedRef.current = null;
    }
  }, [secondaryCaseId, setSidebarCollapsed]);

  // Defensive: if the left pane navigates to the same case the right
  // pane was holding, collapse the duplicate.
  useEffect(() => {
    if (secondaryCaseId && selectedCaseId === secondaryCaseId) {
      setSecondaryCaseId(null);
    }
  }, [selectedCaseId, secondaryCaseId, setSecondaryCaseId]);

  // v2 template-draft lifecycle: hydrate active tasks once + open the SSE stream.
  // Stream stays open across case switches (the strip filters by selectedCaseId).
  useEffect(() => {
    if (!authUser?.id) return;
    void loadActiveTasks();
    startTemplateDraftEventStream();
    return () => {
      stopTemplateDraftEventStream();
    };
  }, [authUser?.id, loadActiveTasks]);

  // Drop all per-case chat state on logout.
  useEffect(() => {
    if (!authUser?.id) {
      resetAllChat();
    }
  }, [authUser?.id, resetAllChat]);

  // Don't fire cancelNewCase if we're unmounting *because* the upload
  // succeeded — by then the store has already cleared pendingCase and
  // bumped selectedCaseId to the real id, and our store→URL effect is
  // navigating to /case/<real>. The succeeded flag protects against
  // that race.
  const succeededRef = useRef<boolean>(false);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  // /new lifecycle: arm the placeholder on entry; tear it down on exit
  // unless we just succeeded (in which case the store already swapped
  // the placeholder for the real case).
  useEffect(() => {
    if (!isNewCaseRoute) return;
    if (!useStudioStore.getState().pendingCase) {
      startNewCase();
    }
    return () => {
      if (succeededRef.current) {
        succeededRef.current = false;
        return;
      }
      const current = useStudioStore.getState().pendingCase;
      if (current && !current.isUploading) {
        cancelNewCase();
      }
    };
  }, [isNewCaseRoute, startNewCase, cancelNewCase]);

  // URL ↔ store sync. Each effect runs only when ITS source-of-truth
  // changes — re-running on the opposite side's change is what caused
  // the previous bounce-back (URL→store firing on a sidebar click would
  // snap the store back to the stale URL before the URL had a chance
  // to update).
  //
  // 1. URL → store. Re-runs ONLY when the URL caseId changes (initial
  //    deep-link, browser back/forward, or after our own navigate).
  //    Reads the current store value imperatively so it doesn't fight
  //    sidebar-driven store updates.
  useEffect(() => {
    if (!urlCaseId) return;
    if (urlCaseId !== useStudioStore.getState().selectedCaseId) {
      selectCase(urlCaseId);
    }
  }, [urlCaseId, selectCase]);

  // 2. Store → URL. Re-runs when the store's selectedCaseId changes
  //    (sidebar click, auto-select). `replace: true` on the cold-entry
  //    auto-select so the back stack stays clean. Synthetic
  //    `untitled-*` ids belong to the /new placeholder and are filtered
  //    out — they never represent a real case URL.
  useEffect(() => {
    if (!selectedCaseId) return;
    if (selectedCaseId.startsWith('untitled-')) return;
    if (selectedCaseId !== urlCaseId) {
      navigate(`/case/${selectedCaseId}`, { replace: !urlCaseId });
    }
    // urlCaseId intentionally excluded — see effect 1 comment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId, navigate]);

  // 3. Cold landing on `/case` with no URL caseId and no selection —
  //    auto-pick the first (newest) case once the list loads. Skip
  //    entirely on `/case/new` so the page doesn't yank the user out of
  //    the upload surface.
  useEffect(() => {
    if (isNewCaseRoute) return;
    if (!urlCaseId && !selectedCaseId && cases.length > 0) {
      selectCase(cases[0]!.id);
    }
  }, [isNewCaseRoute, urlCaseId, cases, selectedCaseId, selectCase]);

  const handleNewCaseSubmit = async (file: File): Promise<boolean> => {
    const result = await submitNewCase(file);
    if (result.success && result.data) {
      const { case: created, case_file_chunks_indexed, gmail_emails_indexed, courtdrive_emails_indexed } =
        result.data;
      addToast(
        `Case ${created.case_number} ingested · ${case_file_chunks_indexed} PDF chunks · ${gmail_emails_indexed} Gmail · ${courtdrive_emails_indexed} Court Drive`,
        'success',
      );
      succeededRef.current = true;
      navigate(`/case/${created.id}`, { replace: true });
      return true;
    }
    addToast(result.error ?? 'Failed to create case', 'error');
    return false;
  };

  const handleNewCaseSubmitByCaseNumber = async (caseNumber: string): Promise<boolean> => {
    const result = await submitNewCaseByCaseNumber(caseNumber);
    if (result.success && result.data) {
      const { case: created, case_file_chunks_indexed, gmail_emails_indexed, courtdrive_emails_indexed } =
        result.data;
      addToast(
        `Case ${created.case_number} ingested · ${case_file_chunks_indexed} PDF chunks · ${gmail_emails_indexed} Gmail · ${courtdrive_emails_indexed} Court Drive`,
        'success',
      );
      succeededRef.current = true;
      navigate(`/case/${created.id}`, { replace: true });
      return true;
    }
    addToast(result.error ?? 'Failed to extract petition', 'error');
    return false;
  };

  // Drop-target callback wired into both panes. Behaviour:
  //  - Drop the same case the target already shows → no-op.
  //  - Primary pane drop, no split yet → open the dropped case in a
  //    new right pane. User gets to keep what they had.
  //  - Primary pane drop, dropped case === secondary's case → SWAP
  //    panes (interchange position). Same for secondary ← primary.
  //  - Primary pane drop, dropped case is neither pane's → replace
  //    primary (same as a sidebar click).
  //  - Secondary pane drop, dropped case is neither pane's → replace
  //    secondary in place.
  const handleCaseDropped = useCallback(
    (droppedCaseId: string, target: 'primary' | 'secondary') => {
      if (target === 'primary') {
        if (droppedCaseId === selectedCaseId) return;
        // Swap: dropping the secondary's case onto primary flips them.
        if (secondaryCaseId && droppedCaseId === secondaryCaseId && selectedCaseId) {
          const previousPrimary = selectedCaseId;
          setSecondaryCaseId(previousPrimary);
          selectCase(droppedCaseId);
          return;
        }
        if (!secondaryCaseId) {
          setSecondaryCaseId(droppedCaseId);
          return;
        }
        selectCase(droppedCaseId);
        return;
      }
      // target === 'secondary'
      if (droppedCaseId === secondaryCaseId) return;
      // Swap: dropping the primary's case onto secondary flips them.
      if (droppedCaseId === selectedCaseId && secondaryCaseId) {
        const previousSecondary = secondaryCaseId;
        setSecondaryCaseId(selectedCaseId);
        selectCase(previousSecondary);
        return;
      }
      // Dropping primary's case onto secondary with no split open is a
      // no-op (you can't split with yourself).
      if (droppedCaseId === selectedCaseId) return;
      setSecondaryCaseId(droppedCaseId);
    },
    [selectedCaseId, secondaryCaseId, selectCase, setSecondaryCaseId],
  );

  // Explicit close (× button) — wipe the secondary's chat/PDF state so
  // we don't leak it. Swaps and replacements re-use slices and so
  // intentionally don't clean up.
  const handleCloseSecondary = useCallback(() => {
    if (secondaryCaseId) {
      resetCaseChat(secondaryCaseId);
      clearPDF(buildPdfCacheKey(secondaryCaseId));
    }
    closeSecondaryPane();
  }, [secondaryCaseId, resetCaseChat, clearPDF, closeSecondaryPane]);

  // Closing the primary pane while a split is open promotes the
  // secondary into the primary slot (VSCode-style: closing one half
  // doesn't leave you with nothing). The old primary's chat/PDF
  // slices get wiped since it's no longer rendered anywhere.
  const handleClosePrimary = useCallback(() => {
    if (!secondaryCaseId || !selectedCaseId) return;
    const promoteToPrimary = secondaryCaseId;
    const orphanedPrimary = selectedCaseId;
    closeSecondaryPane();
    resetCaseChat(orphanedPrimary);
    clearPDF(buildPdfCacheKey(orphanedPrimary));
    selectCase(promoteToPrimary);
  }, [
    secondaryCaseId,
    selectedCaseId,
    closeSecondaryPane,
    resetCaseChat,
    clearPDF,
    selectCase,
  ]);

  // Resizable divider between the two panes. Ratio = primary pane's
  // share of the row (clamped so neither pane collapses below 20%).
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const [splitRatio, setSplitRatio] = useState<number>(0.5);
  const handleDividerPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      const container = splitContainerRef.current;
      if (!container) return;
      const containerRect = container.getBoundingClientRect();
      const minRatio = 0.2;
      const maxRatio = 0.8;

      const onMove = (moveEvent: PointerEvent) => {
        const offset = moveEvent.clientX - containerRect.left;
        const next = Math.max(
          minRatio,
          Math.min(maxRatio, offset / containerRect.width),
        );
        setSplitRatio(next);
      };
      const onUp = () => {
        window.removeEventListener('pointermove', onMove);
        window.removeEventListener('pointerup', onUp);
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
      };
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'col-resize';
      window.addEventListener('pointermove', onMove);
      window.addEventListener('pointerup', onUp);
    },
    [],
  );

  if (isNewCaseRoute) {
    // /new is a focused task — single linear job (upload PDF or enter a
    // case number). Drop the status strip and workspace header so the
    // user has one stage, one task. (Architect: "Modals are for
    // interruptions; this is the primary task at this moment.")
    return (
      <SidebarLayout contentClassName="overflow-hidden relative h-full">
        <div className="flex h-full min-w-0 flex-1 flex-col">
          <NewCaseHeader />
          <NewCaseTabs
            onSubmitFile={handleNewCaseSubmit}
            onSubmitCaseNumber={handleNewCaseSubmitByCaseNumber}
            isUploading={pendingCase?.isUploading ?? false}
          />
        </div>
      </SidebarLayout>
    );
  }

  if (!selectedCaseId) {
    return (
      <SidebarLayout contentClassName="overflow-hidden relative h-full">
        <div className="flex h-full min-w-0 flex-1 flex-col">
          <TemplateDraftStatusStrip />
          <div className="flex flex-1 items-center justify-center bg-page p-6 text-center text-sm text-muted">
            Pick a case from the sidebar to start.
          </div>
        </div>
      </SidebarLayout>
    );
  }

  return (
    <SidebarLayout contentClassName="overflow-hidden relative h-full">
      <div className="flex h-full min-w-0 flex-1 flex-col">
        <TemplateDraftStatusStrip />
        <div ref={splitContainerRef} className="flex min-h-0 flex-1">
          <div
            className="flex min-w-0"
            style={
              secondaryCaseId
                ? { flexBasis: `${splitRatio * 100}%` }
                : { flex: 1 }
            }
          >
            <CaseWorkspacePane
              key={selectedCaseId}
              caseId={selectedCaseId}
              isPrimary
              hasSplit={secondaryCaseId !== null}
              onClose={secondaryCaseId ? handleClosePrimary : undefined}
              onCaseDropped={handleCaseDropped}
            />
          </div>
          {secondaryCaseId && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize split panes"
              onPointerDown={handleDividerPointerDown}
              className="group relative w-px shrink-0 cursor-col-resize bg-border transition-colors hover:bg-app-accent"
            >
              {/* Wider invisible hit area so the 1px divider is easy to grab. */}
              <div className="absolute inset-y-0 -left-1.5 -right-1.5" aria-hidden="true" />
            </div>
          )}
          {secondaryCaseId && (
            <div
              className="flex min-w-0"
              style={{ flexBasis: `${(1 - splitRatio) * 100}%` }}
            >
              <CaseWorkspacePane
                key={secondaryCaseId}
                caseId={secondaryCaseId}
                isPrimary={false}
                hasSplit
                onClose={handleCloseSecondary}
                onCaseDropped={handleCaseDropped}
              />
            </div>
          )}
        </div>
      </div>
    </SidebarLayout>
  );
};

export default CaseWorkspacePage;
