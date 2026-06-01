import { useCallback, useEffect, useRef, useState, type ReactElement } from 'react';

import { Modal } from '@/components/common';
import { DocxEditorView, type DocxEditorViewRef } from '@/components/common/DocxEditorView';
import { DownloadMenu } from '@/components/draft-v2/DownloadMenu';
import { RunningAnimation } from '@/components/studio-v2/RunningAnimation';
import {
  autosaveDocx,
  getCompletedDocumentEnvelope,
  type CompletedDocumentEnvelope,
} from '@/services/templateDraft.service';
import { useStudioStore } from '@/stores/useStudioStore';
import { useTemplateDraftStore } from '@/stores/useTemplateDraftStore';
import { useToastStore } from '@/stores/useToastStore';

/**
 * Full-screen Syncfusion docx viewer + editor for completed v2 drafts.
 *
 * Mirrors the legacy pleading `DocumentViewerModal` shell (tabs across the
 * top, Syncfusion editor body, autosave status), but reads its URLs from
 * the v2 `CompletedDocumentEnvelope` and autosaves through
 * `PUT /case-generation-logs/{log_id}/docx` (parent or child by index).
 */

type TabId = 'parent' | `child-${number}`;

interface AutosaveStatus {
  state: 'idle' | 'dirty' | 'saving' | 'saved' | 'error';
  savedAt: number | null;
}

function autosaveLabel(status: AutosaveStatus, hasUnsaved: boolean): string {
  if (status.state === 'saving') return 'Saving…';
  if (status.state === 'error') return 'Save failed';
  if (hasUnsaved || status.state === 'dirty') return 'Unsaved changes';
  if (status.state === 'saved' && status.savedAt) {
    const secondsAgo = Math.round((Date.now() - status.savedAt) / 1000);
    if (secondsAgo < 5) return 'Saved';
    if (secondsAgo < 60) return `Saved ${secondsAgo}s ago`;
    return `Saved ${Math.floor(secondsAgo / 60)}m ago`;
  }
  return 'Saved';
}

function autosaveToneClass(status: AutosaveStatus, hasUnsaved: boolean): string {
  if (status.state === 'error') return 'bg-red-50 text-red-700';
  if (status.state === 'saving') return 'bg-indigo-50 text-indigo-700';
  if (hasUnsaved || status.state === 'dirty') return 'bg-amber-50 text-amber-700';
  return 'bg-emerald-50 text-emerald-700';
}

export const TemplateDraftDocumentViewer = (): ReactElement | null => {
  const taskId = useTemplateDraftStore((s) => s.viewerTaskId);
  const task = useTemplateDraftStore((s) => (taskId ? s.tasks[taskId] : null));
  const closeDocumentViewer = useTemplateDraftStore((s) => s.closeDocumentViewer);
  const studioTemplates = useStudioStore((s) => s.templates);
  const addToast = useToastStore((s) => s.addToast);

  const [envelope, setEnvelope] = useState<CompletedDocumentEnvelope | null>(null);
  const [isLoadingEnvelope, setIsLoadingEnvelope] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('parent');
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const [autosave, setAutosave] = useState<AutosaveStatus>({ state: 'idle', savedAt: null });

  const editorRef = useRef<DocxEditorViewRef>(null);

  // Reset state every time the viewer opens for a different task.
  useEffect(() => {
    if (!task || task.status !== 'COMPLETED' || !task.log_id) {
      setEnvelope(null);
      setActiveTab('parent');
      setHasUnsaved(false);
      setAutosave({ state: 'idle', savedAt: null });
      return;
    }
    let cancelled = false;
    setIsLoadingEnvelope(true);
    setEnvelope(null);
    setActiveTab('parent');
    setHasUnsaved(false);
    setAutosave({ state: 'idle', savedAt: null });
    void (async () => {
      const result = await getCompletedDocumentEnvelope(task.log_id!);
      if (cancelled) return;
      setIsLoadingEnvelope(false);
      if (result.error) {
        addToast(result.error, 'error');
        return;
      }
      setEnvelope(result.data ?? null);
    })();
    return () => {
      cancelled = true;
    };
  }, [task?.task_id, task?.log_id, task?.status, addToast]);

  const activeTabIndex: number | null =
    activeTab === 'parent' ? null : Number(activeTab.slice('child-'.length));

  const activeDocxUrl =
    envelope == null
      ? undefined
      : activeTabIndex === null
        ? envelope.parent_url
        : envelope.children[activeTabIndex]?.url;

  const handleSave = useCallback(
    async (buffer: ArrayBuffer): Promise<{ error?: string }> => {
      if (!task?.log_id) return { error: 'Missing log id' };
      const result = await autosaveDocx(task.log_id, buffer, {
        childIndex: activeTabIndex ?? undefined,
      });
      return { error: result.error };
    },
    [task?.log_id, activeTabIndex],
  );

  const handleTabChange = useCallback(
    async (next: TabId): Promise<void> => {
      if (next === activeTab || isTransitioning) return;
      setIsTransitioning(true);
      try {
        if (hasUnsaved) {
          const ok = await editorRef.current?.flushAutosave();
          if (!ok) {
            addToast('Saving failed — staying on the current tab.', 'error');
            return;
          }
        }
        setActiveTab(next);
      } finally {
        setIsTransitioning(false);
      }
    },
    [activeTab, isTransitioning, hasUnsaved, addToast],
  );

  const handleClose = useCallback(async (): Promise<void> => {
    if (isTransitioning) return;
    if (hasUnsaved) {
      setIsTransitioning(true);
      try {
        const ok = await editorRef.current?.flushAutosave();
        if (!ok) {
          addToast('Saving failed — staying open.', 'error');
          return;
        }
      } finally {
        setIsTransitioning(false);
      }
    }
    closeDocumentViewer();
  }, [hasUnsaved, isTransitioning, addToast, closeDocumentViewer]);

  if (!task || task.status !== 'COMPLETED') return null;

  const liveTemplateName =
    studioTemplates.find((t) => t.id === task.template_id)?.name ?? task.template_name ?? task.template_id;
  const childrenList = envelope?.children ?? [];
  const showTabs = childrenList.length > 0;
  const activeTabName: string =
    activeTabIndex === null
      ? liveTemplateName
      : childrenList[activeTabIndex]?.template_name ?? liveTemplateName;

  return (
    <Modal
      isOpen
      onClose={() => void handleClose()}
      size="full"
      showCloseButton={false}
      glowingBorder={isLoadingEnvelope}
    >
      <div className="flex h-[90vh] flex-col" role="dialog" aria-labelledby="td-viewer-title">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="min-w-0">
            <h2 id="td-viewer-title" className="truncate text-lg font-semibold text-text-secondary">
              {liveTemplateName}
            </h2>
            {task.case_id && <p className="text-xs text-muted">Case {task.case_id}</p>}
          </div>
          <div className="flex items-center gap-2">
            {task.log_id && activeDocxUrl && (
              <DownloadMenu
                logId={task.log_id}
                filename={activeTabName}
                directUrl={activeDocxUrl}
                childIndex={activeTabIndex ?? undefined}
              />
            )}
            <button
              type="button"
              onClick={() => void handleClose()}
              disabled={isTransitioning}
              className="rounded-lg p-2 text-subtle transition-colors hover:bg-surface-muted hover:text-text-secondary disabled:opacity-50"
              aria-label="Close viewer"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Tabs (only for bundle children) */}
        {showTabs && (
          <div className="flex flex-wrap border-b border-border px-6">
            <button
              type="button"
              onClick={() => void handleTabChange('parent')}
              disabled={isTransitioning}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'parent'
                  ? 'border-app-accent text-app-accent-text'
                  : 'border-transparent text-muted hover:text-text-secondary'
              }`}
            >
              {liveTemplateName}
            </button>
            {childrenList.map((child, idx) => {
              const id: TabId = `child-${idx}`;
              return (
                <button
                  key={`${child.template_id}-${idx}`}
                  type="button"
                  onClick={() => void handleTabChange(id)}
                  disabled={isTransitioning}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === id
                      ? 'border-app-accent text-app-accent-text'
                      : 'border-transparent text-muted hover:text-text-secondary'
                  }`}
                  title={child.companion_label}
                >
                  {child.template_name}
                </button>
              );
            })}
          </div>
        )}

        {/* Autosave status bar */}
        <div className="flex items-center justify-between border-b border-border bg-surface-muted px-6 py-2">
          <span className="text-[11px] uppercase tracking-wider text-muted">
            {activeTab === 'parent'
              ? 'Parent document'
              : childrenList[activeTabIndex ?? -1]?.companion_label ?? 'Companion'}
          </span>
          <span
            className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${autosaveToneClass(autosave, hasUnsaved)}`}
          >
            {isTransitioning ? 'Syncing…' : autosaveLabel(autosave, hasUnsaved)}
          </span>
        </div>

        {/* Body */}
        <div className="relative flex min-h-0 flex-1 flex-col bg-surface">
          {isLoadingEnvelope && (
            <div className="flex flex-1 items-center justify-center px-6 py-10">
              <RunningAnimation phase="loading_document" size="xl" />
            </div>
          )}
          {!isLoadingEnvelope && envelope && activeDocxUrl && (
            <DocxEditorView
              ref={editorRef}
              key={activeTab /* force reset on tab swap so Syncfusion reloads cleanly */}
              docxUrl={activeDocxUrl}
              onSave={handleSave}
              onSaveStatusChange={setHasUnsaved}
              onAutoSaveStateChange={(state, savedAt) => {
                setAutosave({
                  state,
                  savedAt: typeof savedAt === 'number' ? savedAt : null,
                });
              }}
            />
          )}
          {!isLoadingEnvelope && !envelope && (
            <div className="flex flex-1 items-center justify-center text-sm text-red-600">
              Document could not be loaded.
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default TemplateDraftDocumentViewer;
