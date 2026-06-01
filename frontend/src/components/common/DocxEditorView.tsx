import {
  useState,
  useEffect,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { registerLicense } from '@syncfusion/ej2-base';
import {
  DocumentEditorContainerComponent,
  Toolbar,
} from '@syncfusion/ej2-react-documenteditor';
import type { ServiceFailureArgs } from '@syncfusion/ej2-documenteditor';
import '@syncfusion/ej2-base/styles/material.css';
import '@syncfusion/ej2-buttons/styles/material.css';
import '@syncfusion/ej2-inputs/styles/material.css';
import '@syncfusion/ej2-popups/styles/material.css';
import '@syncfusion/ej2-lists/styles/material.css';
import '@syncfusion/ej2-navigations/styles/material.css';
import '@syncfusion/ej2-splitbuttons/styles/material.css';
import '@syncfusion/ej2-dropdowns/styles/material.css';
import '@syncfusion/ej2-react-documenteditor/styles/material.css';
import { Spinner } from '@/components/common';
import { useToastStore } from '@/stores/useToastStore';
import { withCacheBuster } from '@/utils/cache';
import { withCookieCredentials } from '@/features/auth/auth.requests';

DocumentEditorContainerComponent.Inject(Toolbar);
const syncfusionLicenseKey = import.meta.env.VITE_SYNCFUSION_LICENSE_KEY;
if (syncfusionLicenseKey) {
  registerLicense(syncfusionLicenseKey);
}

export type DocxSaveMode = 'autosave' | 'manual' | 'flush';

export type DocxSaveCallback = (
  buffer: ArrayBuffer,
  options: { mode: DocxSaveMode; regeneratePDF: boolean },
) => Promise<{ error?: string }>;

interface DocxEditorViewProps {
  docxUrl: string | undefined;
  onSave: DocxSaveCallback;
  onSaveStatusChange: (hasUnsaved: boolean) => void;
  onAutoSaveStateChange?: (state: 'idle' | 'dirty' | 'saving' | 'saved' | 'error', savedAt?: number) => void;
}

export interface DocxEditorViewRef {
  save: () => Promise<boolean>;
  flushAutosave: () => Promise<boolean>;
}

const AUTO_SAVE_DEBOUNCE_MS = 2000;
const AUTO_SAVE_MAX_WAIT_MS = 15000;

const getDocxFilename = (docxUrl: string) => {
  try {
    const normalizedUrl = docxUrl.startsWith('http')
      ? docxUrl
      : `http://localhost${docxUrl.startsWith('/') ? docxUrl : `/${docxUrl}`}`;
    const url = new URL(normalizedUrl);
    const pathnameFilename = url.pathname.split('/').pop() || '';

    if (pathnameFilename.toLowerCase().endsWith('.docx')) {
      return pathnameFilename;
    }

    const motionType = url.searchParams.get('motion_type');
    if (motionType) {
      return `${motionType}.docx`;
    }
  } catch {
    const fallbackFilename = docxUrl.split('/').pop() || '';
    if (fallbackFilename.toLowerCase().endsWith('.docx')) {
      return fallbackFilename;
    }
  }

  return 'document.docx';
};

export const DocxEditorView = forwardRef<DocxEditorViewRef, DocxEditorViewProps>(
  ({ docxUrl, onSave, onSaveStatusChange, onAutoSaveStateChange }, ref) => {
    const { addToast } = useToastStore();
    const editorRef = useRef<DocumentEditorContainerComponent | null>(null);
    const lastLoadedUrlRef = useRef<string | null>(null);
    const autosaveDebounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const autosaveMaxWaitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const isContentChangeSuppressedRef = useRef(false);
    const hasPendingChangesRef = useRef(false);
    const queuedSaveRef = useRef(false);
    const activeSavePromiseRef = useRef<Promise<boolean> | null>(null);
    const changeVersionRef = useRef(0);
    const savedVersionRef = useRef(0);
    const isUnmountedRef = useRef(false);

    const [isFetching, setIsFetching] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [isEditorReady, setIsEditorReady] = useState(false);
    const [hasLoadedDocument, setHasLoadedDocument] = useState(false);

    const emitAutoSaveState = useCallback(
      (state: 'idle' | 'dirty' | 'saving' | 'saved' | 'error', savedAt?: number) => {
        onAutoSaveStateChange?.(state, savedAt);
      },
      [onAutoSaveStateChange]
    );

    const clearAutosaveTimers = useCallback(() => {
      if (autosaveDebounceTimerRef.current) {
        clearTimeout(autosaveDebounceTimerRef.current);
        autosaveDebounceTimerRef.current = null;
      }
      if (autosaveMaxWaitTimerRef.current) {
        clearTimeout(autosaveMaxWaitTimerRef.current);
        autosaveMaxWaitTimerRef.current = null;
      }
    }, []);

    const performSave = useCallback(
      async (mode: 'autosave' | 'manual' | 'flush' = 'autosave'): Promise<boolean> => {
        if (!editorRef.current?.documentEditor || !docxUrl) return false;

        const hasPendingChanges = changeVersionRef.current > savedVersionRef.current;
        if (!hasPendingChanges && mode !== 'manual') {
          return true;
        }

        if (activeSavePromiseRef.current) {
          queuedSaveRef.current = true;
          return activeSavePromiseRef.current;
        }

        clearAutosaveTimers();
        if (!isUnmountedRef.current) {
          setIsSaving(true);
        }
        emitAutoSaveState('saving');

        const saveSnapshotVersion = changeVersionRef.current;
        const savePromise = (async () => {
          let didSucceed = false;
          try {
            const blob = await editorRef.current!.documentEditor.saveAsBlob('Docx');
            const buffer = await blob.arrayBuffer();
            const shouldRegeneratePDF = mode !== 'autosave';
            const { error } = await onSave(buffer, {
              mode,
              regeneratePDF: shouldRegeneratePDF,
            });
            if (error) throw new Error(error);

            didSucceed = true;
            savedVersionRef.current = Math.max(savedVersionRef.current, saveSnapshotVersion);
            const stillHasPendingChanges = changeVersionRef.current > savedVersionRef.current;
            hasPendingChangesRef.current = stillHasPendingChanges;
            onSaveStatusChange(stillHasPendingChanges);

            if (!stillHasPendingChanges) {
              emitAutoSaveState('saved', Date.now());
            } else {
              emitAutoSaveState('dirty');
            }

            if (mode === 'manual') {
              addToast('Document saved successfully', 'success');
            }

            return true;
          } catch (err) {
            console.error('Error saving document:', err);
            hasPendingChangesRef.current = changeVersionRef.current > savedVersionRef.current;
            onSaveStatusChange(hasPendingChangesRef.current);
            emitAutoSaveState('error');

            if (mode !== 'autosave') {
              addToast('Failed to save document', 'error');
            }
            return false;
          } finally {
            activeSavePromiseRef.current = null;
            if (!isUnmountedRef.current) {
              setIsSaving(false);
            }

            const shouldRunQueuedSave = queuedSaveRef.current;
            queuedSaveRef.current = false;

            if (
              shouldRunQueuedSave &&
              changeVersionRef.current > savedVersionRef.current &&
              !isUnmountedRef.current
            ) {
              void performSave('autosave');
            } else if (!didSucceed && changeVersionRef.current > savedVersionRef.current) {
              emitAutoSaveState('dirty');
            }
          }
        })();

        activeSavePromiseRef.current = savePromise;
        return savePromise;
      },
      [addToast, clearAutosaveTimers, docxUrl, emitAutoSaveState, onSave, onSaveStatusChange]
    );

    const scheduleAutosave = useCallback(() => {
      if (autosaveDebounceTimerRef.current) {
        clearTimeout(autosaveDebounceTimerRef.current);
      }

      autosaveDebounceTimerRef.current = setTimeout(() => {
        void performSave('autosave');
      }, AUTO_SAVE_DEBOUNCE_MS);

      if (!autosaveMaxWaitTimerRef.current) {
        autosaveMaxWaitTimerRef.current = setTimeout(() => {
          autosaveMaxWaitTimerRef.current = null;
          void performSave('autosave');
        }, AUTO_SAVE_MAX_WAIT_MS);
      }
    }, [performSave]);

    const fetchAndOpenDocx = useCallback(
      async (url: string) => {
        if (!editorRef.current?.documentEditor) return;

        clearAutosaveTimers();
        queuedSaveRef.current = false;
        activeSavePromiseRef.current = null;
        hasPendingChangesRef.current = false;
        changeVersionRef.current = 0;
        savedVersionRef.current = 0;
        isContentChangeSuppressedRef.current = true;
        onSaveStatusChange(false);
        emitAutoSaveState('idle');

        setIsFetching(true);
        try {
          // Absolute URLs (e.g. presigned R2 URLs from v2) are fetched as-is
          // — prepending the API base or appending a cache-buster would either
          // produce a malformed URL or invalidate the URL's signature. R2
          // also doesn't want our session cookies (the URL signature is the
          // auth), so we skip withCookieCredentials for that branch.
          const isAbsolute = /^https?:\/\//i.test(url);
          const response = isAbsolute
            ? await fetch(url, { cache: 'no-store' })
            : await fetch(
                `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${withCacheBuster(url)}`,
                withCookieCredentials({
                  cache: 'no-store',
                  headers: {
                    'Cache-Control': 'no-cache',
                    Pragma: 'no-cache',
                  },
                }),
              );
          if (!response.ok) throw new Error(`Failed to fetch DOCX: ${response.status}`);

          const blob = await response.blob();
          editorRef.current.documentEditor.open(
            new File([blob], getDocxFilename(url), {
              type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            })
          );
          window.setTimeout(() => {
            isContentChangeSuppressedRef.current = false;
          }, 300);
          setHasLoadedDocument(true);
        } catch (error) {
          console.error('Error fetching DOCX:', error);
          addToast('Failed to load document for editing', 'error');
          setHasLoadedDocument(false);
        } finally {
          setIsFetching(false);
        }
      },
      [addToast, clearAutosaveTimers, emitAutoSaveState, onSaveStatusChange]
    );

    useEffect(() => {
      if (
        !docxUrl ||
        !isEditorReady ||
        !editorRef.current?.documentEditor ||
        docxUrl === lastLoadedUrlRef.current
      ) {
        return;
      }

      lastLoadedUrlRef.current = docxUrl;
      setHasLoadedDocument(false);
      void fetchAndOpenDocx(docxUrl);
    }, [docxUrl, fetchAndOpenDocx, isEditorReady]);

    const handleSave = useCallback(async () => {
      return performSave('manual');
    }, [performSave]);

    const flushAutosave = useCallback(async () => {
      clearAutosaveTimers();

      if (activeSavePromiseRef.current) {
        const inflightResult = await activeSavePromiseRef.current;
        if (changeVersionRef.current <= savedVersionRef.current) {
          return inflightResult;
        }
      }

      if (changeVersionRef.current <= savedVersionRef.current) {
        return true;
      }

      return performSave('flush');
    }, [clearAutosaveTimers, performSave]);

    useImperativeHandle(
      ref,
      () => ({
        save: handleSave,
        flushAutosave,
      }),
      [flushAutosave, handleSave]
    );

    const handleContentChange = useCallback(() => {
      if (isContentChangeSuppressedRef.current) return;

      changeVersionRef.current += 1;
      hasPendingChangesRef.current = true;
      onSaveStatusChange(true);
      emitAutoSaveState('dirty');
      scheduleAutosave();
    }, [emitAutoSaveState, onSaveStatusChange, scheduleAutosave]);

    const handleServiceFailure = useCallback(
      (args: ServiceFailureArgs) => {
        console.error('Syncfusion document service failed:', args);
        addToast('Syncfusion document service failed while loading the editor', 'error');
      },
      [addToast]
    );

    useEffect(() => {
      isUnmountedRef.current = false;
      return () => {
        isUnmountedRef.current = true;
        clearAutosaveTimers();
      };
    }, [clearAutosaveTimers]);

    if (!docxUrl) {
      return (
        <div className="flex flex-1 items-center justify-center bg-surface-muted text-muted">
          <p>No document loaded</p>
        </div>
      );
    }

    return (
      <div className="relative flex h-full min-h-0 flex-1 overflow-hidden bg-surface">
        {isFetching && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface/60">
            <Spinner size="lg" />
          </div>
        )}
        {isSaving && (
          <div className="pointer-events-none absolute right-4 top-4 z-10 rounded-full bg-surface/90 px-3 py-1 text-xs text-muted shadow-sm">
            Saving...
          </div>
        )}

        {!hasLoadedDocument && !isFetching && (
          <div className="absolute inset-0 z-[1] flex items-center justify-center bg-surface-muted text-muted">
            <p>Loading document editor...</p>
          </div>
        )}

        <DocumentEditorContainerComponent
          ref={editorRef}
          id="pleading-docx-editor"
          className="h-full w-full"
          height="100%"
          width="100%"
          style={{ height: '100%', width: '100%' }}
          enableToolbar={true}
          showPropertiesPane={false}
          serviceUrl={import.meta.env.VITE_SYNCFUSION_SERVER_URL}
          created={() => {
            setIsEditorReady(true);
            editorRef.current?.showHidePropertiesPane?.(false);
          }}
          contentChange={handleContentChange}
          serviceFailure={handleServiceFailure}
        />
      </div>
    );
  }
);

DocxEditorView.displayName = 'DocxEditorView';
