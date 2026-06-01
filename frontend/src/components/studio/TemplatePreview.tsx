import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { registerLicense } from '@syncfusion/ej2-base';
import {
  DocumentEditorContainerComponent,
  Toolbar,
} from '@syncfusion/ej2-react-documenteditor';
import Lottie from 'lottie-react';
import templateLoadingAnimation from '@/assets/lottie/upload-search.json';
import { useStudioStore } from '@/stores/useStudioStore';

DocumentEditorContainerComponent.Inject(Toolbar);
const syncfusionLicenseKey = import.meta.env.VITE_SYNCFUSION_LICENSE_KEY;
if (syncfusionLicenseKey) {
  registerLicense(syncfusionLicenseKey);
}

export type PreviewMode =
  | 'template'
  | 'original'
  | 'draft'
  | { kind: 'companion'; index: number };

interface TemplatePreviewProps {
  mode: PreviewMode;
  onExport: (exporter: () => void) => void;
  suppressLoadingOverlay?: boolean;
  onDocumentLoaded?: (url: string) => void;
}

const isCompanionMode = (
  mode: PreviewMode,
): mode is { kind: 'companion'; index: number } =>
  typeof mode === 'object' && mode.kind === 'companion';

const DOCX_MIME =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

const fetchDocxAsBlob = async (url: string): Promise<Blob> => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download document (HTTP ${response.status})`);
  }
  return response.blob();
};

const downloadBlob = (blob: Blob, filename: string): void => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const IconFileText = ({ className = 'h-12 w-12' }: { className?: string }): ReactElement => (
  <svg
    className={className}
    fill="none"
    stroke="currentColor"
    strokeLinecap="round"
    strokeLinejoin="round"
    strokeWidth={1.5}
    viewBox="0 0 24 24"
  >
    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="9" y1="13" x2="15" y2="13" />
    <line x1="9" y1="17" x2="15" y2="17" />
  </svg>
);

const IconAlert = (): ReactElement => (
  <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M5.07 19h13.86a2 2 0 001.74-3L13.73 4a2 2 0 00-3.46 0l-7.14 12a2 2 0 001.74 3z" />
  </svg>
);

type FindOption = 'None' | 'WholeWord' | 'CaseSensitive' | 'CaseSensitiveWholeWord';

const highlightStringsInEditor = (
  editor: DocumentEditorContainerComponent['documentEditor'],
  searchStrings: string[],
  findOption: FindOption,
): boolean => {
  if (!editor.search || !editor.editor) {
    console.warn('[TemplatePreview] highlight skipped — modules unavailable', {
      hasSearch: !!editor.search,
      hasEditor: !!editor.editor,
    });
    return false;
  }
  let totalHits = 0;
  let totalApplied = 0;
  
  const unique = Array.from(new Set(searchStrings.filter((s) => s.length >= 2)));
  const tryFindAll = (needle: string, option: FindOption): number => {
    try {
      editor.search.findAll(needle, option);
    } catch (err) {
      console.warn('[TemplatePreview] findAll threw for', needle, err);
      return 0;
    }
    return editor.search.searchResults?.length ?? 0;
  };
  // Grammar/tone healing on the BE may strip trailing punctuation (e.g. "$18,752.00." → "$18,752.00")
  // or attach it to the value. Strip a trailing dot/comma/semicolon before fallback.
  const stripTrailingPunct = (s: string): string => s.replace(/[.,;:]+$/, '');
  for (const needle of unique) {
    let length = tryFindAll(needle, findOption);
    if (length === 0 && findOption !== 'None') {
      length = tryFindAll(needle, 'None');
    }
    if (length === 0) {
      const trimmed = stripTrailingPunct(needle);
      if (trimmed.length >= 2 && trimmed !== needle) {
        length = tryFindAll(trimmed, 'None');
      }
    }
    if (length === 0) continue;
    totalHits += length;
    for (let i = length - 1; i >= 0; i -= 1) {
      try {
        editor.search.searchResults.index = i;
        
        const currentColor = editor.selection?.characterFormat?.highlightColor;
        if (currentColor === 'Yellow') continue;
        editor.editor.toggleHighlightColor('Yellow');
        totalApplied += 1;
      } catch (err) {
        console.warn('[TemplatePreview] apply threw at', needle, i, err);
      }
    }
  }
  try {
    editor.search.searchResults?.clear();
    // Intentionally do NOT call selection.moveToDocumentStart() here —
    // it scrolls the editor viewport to the top, fighting the user's
    // scroll position every time this function re-runs (which the
    // polling interval triggers on every 300ms tick until success).
  } catch {
    void 0;
  }
  console.info('[TemplatePreview] highlight pass complete', {
    totalHits,
    totalApplied,
    needleCount: unique.length,
  });
  // Use `totalHits` (matches found this pass) instead of `totalApplied`
  // (new highlights applied) — re-runs are idempotent: matches that are
  // already Yellow get skipped, so totalApplied=0 on re-passes. Returning
  // true when totalHits>0 lets the polling interval mark the URL as
  // highlighted and clear itself.
  return totalHits > 0;
};

export const TemplatePreview = ({
  mode,
  onExport,
  suppressLoadingOverlay = false,
  onDocumentLoaded,
}: TemplatePreviewProps): ReactElement => {
  const templateDocUrl = useStudioStore((state) => state.templateDocUrl);
  const originalDocUrl = useStudioStore((state) => state.originalDocUrl);
  const dryRunResult = useStudioStore((state) => state.dryRunResult);
  const draftResult = useStudioStore((state) => state.draftResult);
  const templateSpec = useStudioStore((state) => state.templateSpec);

  const editorRef = useRef<DocumentEditorContainerComponent | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lastLoadedUrlRef = useRef<string | null>(null);
  // Signature = `${activeUrl}|${needle1}${needle2}...` — guards against
  // re-running the search loop only when BOTH the URL and the needle set are
  // unchanged. Using URL alone (the old behavior) blocked highlight refresh
  // whenever the user edited variables on the same template, leaving the
  // preview stuck with stale highlights.
  // What the editor has ACTUALLY rendered, promoted only from
  // `documentChange` (or the 8s stuck-guard fallback). `lastLoadedUrlRef`
  // is set sync right after `editor.open(file)`, but open() is sync-call /
  // async-effect: the editor keeps showing the previous doc for hundreds
  // of ms while it parses the new one. Gating highlights on
  // `lastLoadedUrlRef` would run findAll against stale content during
  // that swap window and toggle highlight colors on text that's about
  // to be discarded — the visible "flash on previous template" during
  // a switch.
  const lastRenderedUrlRef = useRef<string | null>(null);
  const lastHighlightedSignatureRef = useRef<string | null>(null);
  
  const expectingDocumentChangeRef = useRef<boolean>(false);
  const [isEditorReady, setIsEditorReady] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const draftSource = draftResult ?? dryRunResult;

  let activeUrl: string | null = templateDocUrl;
  if (isCompanionMode(mode)) {
    activeUrl = draftSource?.children?.[mode.index]?.generated_doc_url ?? null;
  } else if (mode === 'draft' && draftSource) {
    activeUrl = draftSource.generated_doc_url;
  } else if (mode === 'original') {
    activeUrl = originalDocUrl;
  }

  const activeFileName = useMemo(() => {
    if (isCompanionMode(mode)) {
      const child = draftSource?.children?.[mode.index];
      return child ? `${child.template_name}.docx` : 'companion.docx';
    }
    if (mode === 'draft') return draftResult ? 'draft.docx' : 'dry-run.docx';
    if (mode === 'original') return 'original.docx';
    return 'template.docx';
  }, [mode, draftResult, draftSource]);

  useEffect((): (() => void) | void => {
    if (!activeUrl || !isEditorReady || !editorRef.current?.documentEditor) {
      return;
    }
    if (activeUrl === lastLoadedUrlRef.current) return;

    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);
    
    lastHighlightedSignatureRef.current = null;

    const loadDocument = async (): Promise<void> => {
      try {
        const blob = await fetchDocxAsBlob(activeUrl);
        if (cancelled) return;
        const file = new File([blob], activeFileName, { type: DOCX_MIME });
        
        expectingDocumentChangeRef.current = true;
        editorRef.current!.documentEditor.open(file);
        lastLoadedUrlRef.current = activeUrl;
      } catch (err: unknown) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : 'Failed to load document');
          
          expectingDocumentChangeRef.current = false;
          setIsLoading(false);
        }
      }
    };

    void loadDocument();
    
    const stuckGuard = window.setTimeout(() => {
      if (!cancelled && expectingDocumentChangeRef.current) {
        console.warn('[TemplatePreview] documentChange never fired after open(); releasing overlay');
        expectingDocumentChangeRef.current = false;
        setIsLoading(false);
        // Mirror handleDocumentChange's promotion so highlight polling
        // isn't permanently blocked when Syncfusion doesn't fire the
        // documentChange event. `cancelled` would be true if the user
        // switched away mid-load, so we're not promoting a stale URL.
        lastRenderedUrlRef.current = activeUrl;
        onDocumentLoaded?.(activeUrl);
      }
    }, 8000);
    return (): void => {
      cancelled = true;
      window.clearTimeout(stuckGuard);
    };
  }, [activeUrl, isEditorReady, activeFileName, onDocumentLoaded]);

  const isApplyingHighlightsRef = useRef<boolean>(false);

  const tryApplyHighlightsRef = useRef<() => void>(() => {});
  tryApplyHighlightsRef.current = (): void => {

    if (isApplyingHighlightsRef.current) return;
    if (!activeUrl) return;
    if (lastRenderedUrlRef.current !== activeUrl) return;
    const editor = editorRef.current?.documentEditor;
    if (!editor) return;

    let needles: string[] = [];
    let findOption: FindOption = 'CaseSensitive';
    if (mode === 'template') {
      if (templateSpec.length === 0) return;
      needles = templateSpec
        .map((v) => v.template_variable)
        .filter((v): v is string => Boolean(v))
        .map((v) => `[[${v}]]`);
    } else {
      const source = draftSource;
      if (!source) return;
      needles = source.resolved_values
        .map((rv) => rv.value)
        .filter((v): v is string => typeof v === 'string' && v.trim().length >= 2);
      findOption = 'WholeWord';
    }
    if (needles.length === 0) return;

    // Skip if THIS exact URL + needle set has already been highlighted. The
    // signature combines both so editing variables on the same template still
    // triggers a re-run (previously a URL-only guard left highlights stale).
    const signature = `${activeUrl}|${needles.join('')}`;
    if (lastHighlightedSignatureRef.current === signature) return;

    isApplyingHighlightsRef.current = true;
    try {
      const ok = highlightStringsInEditor(editor, needles, findOption);
      if (ok) {
        lastHighlightedSignatureRef.current = signature;
      }
    } finally {
      isApplyingHighlightsRef.current = false;
    }
  };

  const handleDocumentChange = (): void => {

    if (expectingDocumentChangeRef.current) {
      expectingDocumentChangeRef.current = false;
      setIsLoading(false);
      // The editor confirmed the swap; promote so tryApplyHighlights
      // can now run against the new content.
      lastRenderedUrlRef.current = activeUrl;
      // Default zoom: fit page width so the layout fills the preview pane
      // instead of leaving a column of whitespace at default 100%.
      try {
        editorRef.current?.documentEditor?.fitPage('FitPageWidth');
      } catch {
        void 0;
      }
      // Defer caller notification (e.g. studio's hydration handoff) until
      // here so the outer Lottie stays up across the parse/paint window
      // instead of clearing the moment editor.open() returns.
      if (activeUrl) onDocumentLoaded?.(activeUrl);
    }
    tryApplyHighlightsRef.current();
  };

  const handleToolbarClick = (args: { item?: { id?: string } }): void => {
    const editor = editorRef.current?.documentEditor;
    if (!editor) return;
    switch (args.item?.id) {
      case 'fmt-bold':
        editor.editor?.toggleBold?.();
        break;
      case 'fmt-italic':
        editor.editor?.toggleItalic?.();
        break;
      case 'fmt-underline':
        editor.editor?.toggleUnderline?.('Single');
        break;
      default:
        break;
    }
  };

  useEffect((): (() => void) | void => {
    if (loadError) return;
    // Compute the same signature `tryApplyHighlightsRef` uses so the polling
    // interval clears as soon as this URL + needle set is fully highlighted,
    // and so spec edits (which keep the URL the same) still kick off a fresh
    // poll.
    let needles: string[] = [];
    if (mode === 'template') {
      needles = templateSpec
        .map((v) => v.template_variable)
        .filter((v): v is string => Boolean(v))
        .map((v) => `[[${v}]]`);
    } else if (draftSource) {
      needles = draftSource.resolved_values
        .map((rv) => rv.value)
        .filter((v): v is string => typeof v === 'string' && v.trim().length >= 2);
    }
    if (!activeUrl) return;
    // Bail when needles are empty — the previous logic computed a `${url}|`
    // signature and started an interval that could never clear
    // (tryApplyHighlights bails on empty needles without setting the ref),
    // leaving highlights stuck forever once templateSpec hydrated late.
    if (needles.length === 0) return;

    const signature = `${activeUrl}|${needles.join('')}`;
    if (lastHighlightedSignatureRef.current === signature) return;

    // Attempt immediately so the common case (document already loaded by
    // the time templateSpec hydrates) doesn't wait 300ms for the first tick.
    tryApplyHighlightsRef.current();
    if (lastHighlightedSignatureRef.current === signature) return;

    const id = window.setInterval(() => {
      tryApplyHighlightsRef.current();
      if (lastHighlightedSignatureRef.current === signature) {
        window.clearInterval(id);
      }
    }, 300);
    return (): void => {
      window.clearInterval(id);
    };
  }, [mode, loadError, templateSpec, draftSource, activeUrl]);

  // Keep the document fit to the pane width as the container resizes —
  // viewport/DevTools resize, the desktop split-drag, and (critically) the
  // tablet Workspace/Preview toggle. Syncfusion measures its container once;
  // when the pane is hidden (display:none → 0 width) at load time it fits the
  // page to the ~10% minimum and never recovers, so re-fit on width changes.
  // Re-fit only AFTER the resize settles (~150ms idle) so the document doesn't
  // jump/re-zoom continuously while the width is being dragged.
  useEffect((): (() => void) | void => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    let settleTimer = 0;
    let prevWidth = -1;
    const ro = new ResizeObserver((): void => {
      const width = el.clientWidth;
      if (width === 0 || width === prevWidth) return;
      prevWidth = width;
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout((): void => {
        const editor = editorRef.current?.documentEditor;
        if (!editor || el.clientWidth === 0) return;
        try {
          editor.resize();
          editor.fitPage('FitPageWidth');
        } catch {
          void 0;
        }
      }, 150);
    });
    ro.observe(el);
    return (): void => {
      window.clearTimeout(settleTimer);
      ro.disconnect();
    };
  }, [isEditorReady]);

  useEffect((): void => {
    onExport((): void => {
      const editor = editorRef.current?.documentEditor;
      if (!editor) return;
      void (async () => {
        try {
          const blob = await editor.saveAsBlob('Docx');
          downloadBlob(blob, activeFileName);
        } catch (err) {
          console.warn('Export failed', err);
          setLoadError(err instanceof Error ? err.message : 'Export failed');
        }
      })();
    });
  }, [onExport, activeFileName]);

  if (!activeUrl) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <IconFileText className="h-12 w-12 text-subtle" />
        <p className="text-sm text-muted">
          Upload a legal document to preview it here.
        </p>
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-w-0 flex-col overflow-hidden">
      {(isLoading || !isEditorReady) && !suppressLoadingOverlay && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-surface/85 px-8 text-center backdrop-blur-sm">
          <Lottie
            animationData={templateLoadingAnimation}
            loop
            autoplay
            className="h-48 w-full max-w-xs"
          />
          <p className="text-sm font-semibold text-text-secondary">Loading document…</p>
        </div>
      )}

      {loadError && (
        <div
          role="alert"
          className="absolute inset-x-4 top-4 z-20 flex items-start gap-2 rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-2 text-xs text-app-danger-text shadow-sm"
        >
          <IconAlert />
          <span>{loadError}</span>
        </div>
      )}

      <div ref={containerRef} className="h-full w-full min-w-0 flex-1 overflow-hidden">
        <DocumentEditorContainerComponent
          ref={editorRef}
          id="studio-template-preview"
          className="h-full w-full"
          height="100%"
          width="100%"
          style={{ height: '100%', width: '100%' }}
          enableToolbar
          toolbarItems={[
            'Undo',
            'Redo',
            'Separator',
            { prefixIcon: 'e-de-ctnr-bold e-icons',      tooltipText: 'Bold (Ctrl+B)',      id: 'fmt-bold'      },
            { prefixIcon: 'e-de-ctnr-italic e-icons',    tooltipText: 'Italic (Ctrl+I)',    id: 'fmt-italic'    },
            { prefixIcon: 'e-de-ctnr-underline e-icons', tooltipText: 'Underline (Ctrl+U)', id: 'fmt-underline' },
            'Separator',
            'Find',
          ]}
          toolbarClick={handleToolbarClick}
          showPropertiesPane={false}
          serviceUrl={import.meta.env.VITE_SYNCFUSION_SERVER_URL}
          documentChange={handleDocumentChange}
          created={() => {
            setIsEditorReady(true);
            editorRef.current?.showHidePropertiesPane?.(false);
          }}
        />
      </div>
    </div>
  );
};

export default TemplatePreview;
