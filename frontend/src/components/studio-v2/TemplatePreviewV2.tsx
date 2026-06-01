import { useEffect, useMemo, useRef, useState } from 'react';
import { registerLicense } from '@syncfusion/ej2-base';
import {
  DocumentEditorContainerComponent,
  Toolbar,
} from '@syncfusion/ej2-react-documenteditor';
import {
  FiActivity,
  FiAlertCircle,
  FiCheckCircle,
  FiDownload,
  FiFileText,
  FiLayers,
} from 'react-icons/fi';
import type { StudioTemplate } from './types';
import type { DryRunResponseV2 } from '@/types/studio-v2';
import { cn } from '@/utils';
import { ResolutionLogPane } from './ResolutionLogPane';

DocumentEditorContainerComponent.Inject(Toolbar);
const syncfusionLicenseKey = import.meta.env.VITE_SYNCFUSION_LICENSE_KEY;
if (syncfusionLicenseKey) {
  registerLicense(syncfusionLicenseKey);
}

export type PreviewTab =
  | { kind: 'template' }
  | { kind: 'draft' }
  | { kind: 'companion'; index: number }
  | { kind: 'log' };

interface TemplatePreviewV2Props {
  template: StudioTemplate;
  templateDocUrl?: string | null;
  onSelectVariable: (variableName: string) => void;
  dryRunResult?: DryRunResponseV2 | null;
  activeTab?: PreviewTab;
  onTabChange?: (tab: PreviewTab) => void;
  /** Bumps when the docx CONTENT changed server-side (composer
   * generate / regenerate writes a new file to the same R2 path).
   * Included in the load-effect's renderKey so the editor actually
   * re-fetches even though the path didn't change. Field PATCH does
   * NOT bump this — params edits leave the docx untouched. */
  docContentVersion?: number;
}

const tabKey = (t: PreviewTab): string => {
  if (t.kind === 'companion') return `companion:${t.index}`;
  return t.kind;
};

const PLACEHOLDER_REGEX = /\[\[([a-z_][a-z0-9_]*)\]\]/g;

const humanize = (snake: string): string =>
  snake.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

// Filename used for the File wrapper around the fetched blob. This is a
// transport label only — Syncfusion's /api/documenteditor/Import has been
// observed to silently drop or mis-render files whose name contains
// slashes, hyphens, spaces, or other punctuation. The editor's user-facing
// header pulls the display name from React state, not from the File, so
// we use a fixed safe label here.
const SYNCFUSION_UPLOAD_FILENAME = 'template.docx';

const buildSampleDocument = (template: StudioTemplate): string => {
  const ph = (name: string): string => `[[${name}]]`;

  // Phase 1 synthetic preview: render the template's ACTUAL variables
  // as a structured list instead of the prior hardcoded 341(a) prose.
  // The real .docx is downloadable via the header — this preview is
  // for variable discovery / click-to-edit, not WYSIWYG fidelity.
  const paragraphs: string[] = [];

  paragraphs.push(`${template.name}`);
  paragraphs.push('');
  paragraphs.push(
    'Synthetic preview — each variable from your uploaded .docx appears as a clickable yellow placeholder below. Click any [[placeholder]] to configure it. The actual rendered .docx is available via the Download button in the header.',
  );
  paragraphs.push('');

  if (template.variables.length === 0) {
    paragraphs.push('No variables extracted from this template yet.');
    return paragraphs.join('\n');
  }

  paragraphs.push('Template variables (in document order):');
  paragraphs.push('');

  for (const variable of template.variables) {
    const label = humanize(variable.template_variable);
    const marker = variable.template_property_marker
      ? ` — original value: "${variable.template_property_marker}"`
      : '';
    paragraphs.push(`• ${label}: ${ph(variable.template_variable)}${marker}`);
    if (variable.description) {
      paragraphs.push(`    ${variable.description}`);
    }
    paragraphs.push('');
  }

  return paragraphs.join('\n');
};

const TEMPLATE_TAB: PreviewTab = { kind: 'template' };

export const TemplatePreviewV2 = ({
  template,
  templateDocUrl,
  onSelectVariable,
  dryRunResult,
  activeTab,
  onTabChange,
  docContentVersion = 0,
}: TemplatePreviewV2Props) => {
  const editorRef = useRef<DocumentEditorContainerComponent | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [licenseWarning, setLicenseWarning] = useState<string | null>(null);
  const [loadState, setLoadState] = useState<'idle' | 'loading' | 'ready' | 'error'>(
    'idle',
  );

  // If the page doesn't own the tab state, fall back to internal state so
  // the editor still works standalone (Phase 1 callers don't pass tabs).
  const [internalTab, setInternalTab] = useState<PreviewTab>(TEMPLATE_TAB);
  const effectiveTab: PreviewTab = activeTab ?? internalTab;
  const setTab = (next: PreviewTab): void => {
    setInternalTab(next);
    onTabChange?.(next);
  };
  // If the result disappears (paralegal closed it), force back to template.
  useEffect(() => {
    if (!dryRunResult && effectiveTab.kind !== 'template') {
      setTab(TEMPLATE_TAB);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dryRunResult]);

  // Resolve the active tab to a docx URL + display label.
  // Log tab has no docx — `url` stays null and the render path swaps
  // the Syncfusion canvas for the ResolutionLogPane.
  const activeView = useMemo(() => {
    if (effectiveTab.kind === 'template') {
      return {
        url: templateDocUrl ?? null,
        label: `${template.name}.docx`,
        highlight: true,
      };
    }
    if (effectiveTab.kind === 'draft') {
      return {
        url: dryRunResult?.generated_doc_url ?? null,
        label: `${template.name} — draft`,
        highlight: false,
      };
    }
    if (effectiveTab.kind === 'log') {
      return {
        url: null,
        label: 'Resolution log',
        highlight: false,
      };
    }
    const child = dryRunResult?.children[effectiveTab.index] ?? null;
    return {
      url: child?.finalized.generated_doc_url ?? null,
      label: child ? `${child.template_name}` : 'Companion',
      highlight: false,
    };
  }, [effectiveTab, templateDocUrl, dryRunResult, template.name]);

  const activeDocUrl = activeView.url;
  const activeDocLabel = activeView.label;
  const shouldHighlightPlaceholders = activeView.highlight;

  // For Draft / companion tabs we highlight the RESOLVED VALUES instead
  // of [[placeholders]] so paralegals can spot where each variable landed.
  // Build the list once per tab+result change; the load effect reads it
  // via the ref so the stable documentChange handler can see the latest.
  const activeResolvedTargets = useMemo<Array<{ name: string; needle: string }>>(() => {
    if (!dryRunResult) return [];
    if (effectiveTab.kind === 'draft') {
      return dryRunResult.resolved_values
        .filter((rv) => rv.value && rv.value.trim().length > 0)
        .map((rv) => ({ name: rv.template_variable, needle: rv.value }));
    }
    if (effectiveTab.kind === 'companion') {
      const child = dryRunResult.children[effectiveTab.index];
      if (!child) return [];
      return child.finalized.resolved_values
        .filter((rv) => rv.value && rv.value.trim().length > 0)
        .map((rv) => ({ name: rv.template_variable, needle: rv.value }));
    }
    return [];
  }, [effectiveTab, dryRunResult]);
  const activeResolvedTargetsRef = useRef(activeResolvedTargets);
  activeResolvedTargetsRef.current = activeResolvedTargets;
  // Track placeholders inserted at load-time so selectionChange can pop the wizard.
  const placeholderNamesRef = useRef<Set<string>>(new Set());
  const lastFiredVarRef = useRef<string | null>(null);
  // True while the document is being rebuilt (template switch). Suppresses
  // the selectionChange→openWizard handler so the spurious selection moves
  // triggered by insertBookmark / moveToDocumentStart don't auto-open the
  // wizard for whichever placeholder we happen to land on.
  const isRebuildingRef = useRef(false);

  // Strip the query string from the R2 presigned URL so the load effect
  // doesn't re-fire just because the BE re-signed (different `X-Amz-Signature`
  // for the same object). Without this, every template select triggered a
  // double load: first the URL from the list response, then the URL from
  // the lazy GET /templates/{id} refetch — both pointing to the same R2
  // object with different signatures. We keep the full signed `activeDocUrl`
  // for the actual fetch call, but use the path-only form as the effect dep.
  const activeDocPath = useMemo(() => {
    if (!activeDocUrl) return null;
    try {
      const u = new URL(activeDocUrl);
      return `${u.origin}${u.pathname}`;
    } catch {
      return activeDocUrl;
    }
  }, [activeDocUrl]);

  // Derive a stable string from only the fields that affect when we
  // need to RE-FETCH the docx. Three signals:
  //   - template id (different template → different docx)
  //   - template name + role (cosmetic but cheap to include)
  //   - docContentVersion (composer write bumped this — content of
  //     same R2 path actually changed)
  //
  // DELIBERATELY EXCLUDED:
  //   - `template.variables` — the BE list endpoint returns
  //     `fields: []` while the single-template endpoint returns the
  //     full array. Including variables in the key would mean every
  //     select triggers TWO loads: (1) initial render with empty
  //     vars, (2) lazy /templates/{id} fills vars → renderKey changes
  //     → second load. The variables-driven re-highlight effect
  //     below handles "vars updated, re-apply highlights" without a
  //     re-fetch.
  //   - `variable.params` — params edits don't change the docx, no
  //     re-render needed.
  const renderKey = useMemo(
    () =>
      [
        template.id,
        template.name,
        template.config.role,
        docContentVersion,
      ].join('|'),
    [template.id, template.name, template.config.role, docContentVersion],
  );

  // Keep an up-to-date ref to the latest template so the rebuild effect (which
  // is now keyed off the stable renderKey) can still access current field
  // values when it fires.
  const templateRef = useRef(template);
  templateRef.current = template;

  // Show a notice if the Syncfusion license key is missing — without it
  // the editor renders a license-required banner on top of the canvas.
  useEffect(() => {
    if (!syncfusionLicenseKey) {
      setLicenseWarning(
        'VITE_SYNCFUSION_LICENSE_KEY not set — the editor will show a license banner.',
      );
    }
  }, []);

  // After the .docx loads, search the document for each `needle` string
  // and apply a yellow highlight + bookmark wrapping every occurrence.
  // Used for two cases:
  //   - Template tab: needle = `[[var]]` placeholder string
  //   - Draft / companion tab: needle = the resolved VALUE text, so the
  //     paralegal can see where each variable landed in the filled doc
  const applyHighlights = (
    documentEditor: DocumentEditorContainerComponent['documentEditor'],
    targets: Array<{ name: string; needle: string }>,
  ): void => {
    if (!documentEditor) return;
    const placeholderNames = new Set<string>(targets.map((t) => t.name));
    placeholderNamesRef.current = placeholderNames;
    lastFiredVarRef.current = null;

    try {
      isRebuildingRef.current = true;
      documentEditor.isReadOnly = false;
      const editor = documentEditor.editor;
      for (const { name, needle } of targets) {
        if (!needle) continue;
        try {
          documentEditor.search.findAll(needle, 'None');
          const length = documentEditor.search.searchResults?.length ?? 0;
          for (let i = 0; i < length; i += 1) {
            documentEditor.search.searchResults.index = i;
            editor.toggleHighlightColor('Yellow');
            const bookmarkName = `field_${name}_${i}`;
            try {
              editor.insertBookmark(bookmarkName);
            } catch (err) {
              console.warn('[TemplatePreviewV2] insertBookmark failed', bookmarkName, err);
            }
          }
          documentEditor.search.searchResults?.clear();
        } catch {
          /* search failures are non-fatal */
        }
      }
      documentEditor.selection.moveToDocumentStart();
      // Always open at 100% — don't auto-stretch to fit the editor width.
      // FitPageWidth scaled small documents up to fill the canvas and
      // made line heights inconsistent across templates. 100% gives a
      // predictable rendering across every template + every viewport.
      documentEditor.fitPage('None');
      documentEditor.zoomFactor = 1.0;
      documentEditor.isReadOnly = true;
    } catch (err) {
      console.warn('[TemplatePreviewV2] highlight pass failed', err);
    } finally {
      requestAnimationFrame(() => {
        isRebuildingRef.current = false;
        lastFiredVarRef.current = null;
      });
    }
  };

  // Convenience wrappers for the two call sites.
  const applyPlaceholderHighlights = (
    documentEditor: DocumentEditorContainerComponent['documentEditor'],
    variableNames: string[],
  ): void => {
    applyHighlights(
      documentEditor,
      variableNames.map((name) => ({ name, needle: `[[${name}]]` })),
    );
  };
  const applyResolvedValueHighlights = (
    documentEditor: DocumentEditorContainerComponent['documentEditor'],
  ): void => {
    const targets = activeResolvedTargetsRef.current;
    applyHighlights(documentEditor, targets);
  };

  // Re-load whenever the selected template OR the docx URL changes.
  // Companion config changes (the busy keystroke source) don't bump
  // `renderKey`, so we avoid an expensive Syncfusion rebuild per
  // keystroke in the companions modal.
  const isReadyRef = useRef(isReady);
  isReadyRef.current = isReady;

  // Track the URL that the editor is currently expected to contain (or
  // has loaded). `pendingUrlRef` is the most recent URL we issued an
  // `open(file)` for — the stable documentChange handler below uses it
  // to decide whether the load completion belongs to the current request
  // or to a stale one. `loadedUrlRef` is the URL whose highlights we've
  // already applied (prevents redundant highlight passes if documentChange
  // fires multiple times for the same load).
  const pendingUrlRef = useRef<string | null>(null);
  const loadedUrlRef = useRef<string | null>(null);
  const variableNamesRef = useRef<string[]>([]);
  variableNamesRef.current = template.variables.map((v) => v.template_variable);

  // Track whether the currently-loading document should get placeholder
  // highlights. We can't read shouldHighlightPlaceholders directly from
  // the stable documentChange handler (closures over state), so mirror it
  // into a ref that gets updated alongside the load.
  const highlightOnLoadRef = useRef<boolean>(true);

  // Set to the URL we MOST RECENTLY asked the editor to open. Cleared
  // on effect cleanup so stale `documentChange` fires from a load that
  // got superseded (fast tab / template switch) don't poison
  // `loadedUrlRef` before the real-current load's documentChange fires.
  // Without this, the race was: A's load fires documentChange while
  // pendingUrlRef has already moved to B → handler sees expected=B,
  // marks loadedUrlRef=B → B's actual documentChange later sees
  // loadedUrlRef=B and skips → no highlights for the visible doc.
  const expectedHighlightUrlRef = useRef<string | null>(null);

  // Stable documentChange handler — attached ONCE via the component prop.
  // SIMPLIFIED: this handler ONLY promotes load state. Highlights are
  // applied exclusively by the single highlight effect below.
  //
  // Why: `editor.toggleHighlightColor('Yellow')` is a TOGGLE — calling
  // it twice on the same text removes the highlight. The prior design
  // had both this handler AND a separate re-highlight effect calling
  // applyHighlights independently, leading to the "highlights flash
  // on then disappear" symptom whenever both fired against the same
  // (doc, vars) state.
  const handleDocumentChange = (): void => {
    const expected = expectedHighlightUrlRef.current;
    if (!expected) return; // openBlank / cleared / stale fire
    if (loadedUrlRef.current === expected) return; // already promoted
    loadedUrlRef.current = expected;
    setLoadState('ready');
  };
  const handleDocumentChangeRef = useRef(handleDocumentChange);
  handleDocumentChangeRef.current = handleDocumentChange;

  // Re-load whenever the selected template OR the docx URL changes.
  // Companion config changes (the busy keystroke source) don't bump
  // `renderKey`, so we avoid an expensive Syncfusion rebuild per
  // keystroke in the companions modal.
  useEffect(() => {
    if (!isReady) return;
    const container = editorRef.current;
    if (!container?.documentEditor) return;
    const documentEditor = container.documentEditor;

    // Clear the editor immediately on every render-key change so the
    // PREVIOUS template's content doesn't sit visible during the new
    // fetch. Loaded/pending/expected refs reset too — any in-flight
    // documentChange from the prior load is now a no-op (expected is
    // null until we explicitly call open() for the new URL).
    expectedHighlightUrlRef.current = null;
    try {
      isRebuildingRef.current = true;
      documentEditor.isReadOnly = false;
      documentEditor.openBlank();
    } catch (err) {
      console.warn('[TemplatePreviewV2] failed to clear editor on template switch', err);
    }
    loadedUrlRef.current = null;
    pendingUrlRef.current = null;

    if (!activeDocUrl) {
      // No real URL available for this tab. For the template tab we fall
      // back to a synthetic variable list so paralegals can still click
      // placeholders. For draft/companion tabs there's nothing to render
      // — leave the editor blank.
      if (!shouldHighlightPlaceholders) {
        setLoadState('ready');
        return;
      }
      const text = buildSampleDocument(templateRef.current);
      const synthesizedNames = new Set<string>();
      for (const match of text.matchAll(PLACEHOLDER_REGEX)) {
        synthesizedNames.add(match[1]);
      }
      try {
        isRebuildingRef.current = true;
        documentEditor.isReadOnly = false;
        documentEditor.openBlank();
        const editor = documentEditor.editor;
        const lines = text.split('\n');
        lines.forEach((line, idx) => {
          if (line.length > 0) editor.insertText(line);
          if (idx < lines.length - 1) editor.insertText('\n');
        });
        // Mark this synthetic doc as "loaded" with a sentinel URL so
        // the highlight effect (which watches loadState + needs a
        // loaded doc) fires for it. buildSampleDocument iterates
        // template.variables, so the unified effect's run with
        // template.variables will produce the right highlights.
        const syntheticUrl = `synthetic:${templateRef.current.id}`;
        loadedUrlRef.current = syntheticUrl;
        expectedHighlightUrlRef.current = syntheticUrl;
        // Silence the unused synthesizedNames lint warning — kept the
        // extraction above as a sanity check that buildSampleDocument
        // produced placeholders matching template.variables.
        void synthesizedNames;
        setLoadState('ready');
      } catch (err) {
        console.warn('[TemplatePreviewV2] synthetic fallback failed', err);
        setLoadState('error');
      }
      return;
    }

    setLoadState('loading');
    let cancelled = false;
    pendingUrlRef.current = activeDocUrl;
    highlightOnLoadRef.current = shouldHighlightPlaceholders;

    // Fire-and-forget docx load. documentChange (attached as a stable
    // prop on the editor) drives highlight application. An 8s stuck
    // guard treats "documentChange never fired" as SUCCESS (release the
    // overlay + run highlights anyway) — v1 has used this pattern for
    // months without false negatives. We only show the error overlay
    // when the fetch itself fails or open() throws.
    const stuckGuard = window.setTimeout(() => {
      if (cancelled) return;
      if (loadedUrlRef.current === activeDocUrl) return;
      console.warn('[TemplatePreviewV2] documentChange never fired in 8s; promoting anyway');
      loadedUrlRef.current = activeDocUrl;
      expectedHighlightUrlRef.current = activeDocUrl;
      setLoadState('ready');
      // The single highlight effect will fire on loadState='ready'
      // and apply highlights — no need to do it here.
    }, 8000);

    void (async () => {
      try {
        const response = await fetch(activeDocUrl);
        if (cancelled) return;
        if (!response.ok) {
          window.clearTimeout(stuckGuard);
          console.warn('[TemplatePreviewV2] failed to fetch template.docx', response.status);
          setLoadState('error');
          return;
        }
        const blob = await response.blob();
        if (cancelled) return;
        if (blob.size === 0) {
          window.clearTimeout(stuckGuard);
          console.warn('[TemplatePreviewV2] template.docx blob was empty');
          setLoadState('error');
          return;
        }
        console.info(
          '[TemplatePreviewV2] fetched',
          templateRef.current.name,
          `${blob.size}B`,
        );
        const file = new File(
          [blob],
          SYNCFUSION_UPLOAD_FILENAME,
          { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
        );
        if (cancelled) return;
        isRebuildingRef.current = true;
        // Set expected RIGHT BEFORE open() so the next documentChange
        // fire is unambiguously associated with THIS load. Effects that
        // got cleaned up before reaching this line never set expected
        // (it stays null), so their stale documentChange events are
        // ignored by the handler.
        expectedHighlightUrlRef.current = activeDocUrl;
        documentEditor.open(file);
      } catch (err) {
        if (cancelled) return;
        window.clearTimeout(stuckGuard);
        console.warn('[TemplatePreviewV2] real .docx load failed', err);
        setLoadState('error');
      }
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(stuckGuard);
      // Clear expected so any in-flight documentChange from the load
      // we're abandoning is treated as stale by the handler.
      expectedHighlightUrlRef.current = null;
    };
   
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, renderKey, activeDocPath, tabKey(effectiveTab)]);

  // ─── Re-highlight WITHOUT re-fetching ────────────────────────────
  //
  // The load effect above no longer depends on `template.variables`
  // (would cause a double load because the BE list endpoint returns
  // empty fields while the single-template endpoint returns the full
  // array — see renderKey comment). The trade-off is: when variables
  // change AFTER the initial load (e.g. the lazy /templates/{id} fetch
  // fills them in), the placeholders in the editor never get
  // highlighted/bookmarked because the load-time pass ran against an
  // empty `variableNamesRef`. This effect fixes that — it re-runs
  // `applyPlaceholderHighlights` against the already-loaded doc
  // whenever the variable name signature changes.
  //
  // Guards:
  //   - Only fires on the Template tab (Draft / companion / log have
  // ─── SINGLE highlight source of truth ──────────────────────────────
  //
  // ONE effect, ONE call site for `applyHighlights`. The load effect's
  // documentChange handler + stuck-guard no longer apply highlights
  // (they just promote `loadState`).
  //
  // Why: `editor.toggleHighlightColor('Yellow')` is a TOGGLE. The
  // prior design had documentChange apply highlights, then a separate
  // re-highlight effect apply them again when vars filled — the
  // second pass toggled the first pass's highlights OFF, producing
  // the "highlights flash on then disappear" symptom.
  //
  // Dedupe via `appliedSigRef`: a per-(URL, vars, tab) string that
  // marks what we've already highlighted. We never re-apply for the
  // same sig — if React fires this effect multiple times for the
  // same state (e.g. unrelated re-render), we no-op.
  //
  // Reset triggers (set sig back to ''):
  //   - activeDocPath changes (new docx → blank slate)
  //   - tab changes (different highlight kind / clear)
  //   - loadState transitions away from 'ready' (load effect just
  //     fired openBlank, so prior highlights are gone — next ready
  //     should re-apply)
  const variableNamesSig = useMemo(
    () =>
      template.variables
        .map((v) => v.template_variable)
        .sort()
        .join('|'),
    [template.variables],
  );
  const resolvedTargetsSig = useMemo(
    () =>
      activeResolvedTargets
        .map((t) => `${t.name}=${t.needle}`)
        .sort()
        .join('|'),
    [activeResolvedTargets],
  );
  const effectiveTabKey = tabKey(effectiveTab);
  const appliedSigRef = useRef<string>('');

  // Reset bookkeeping whenever the underlying doc / tab changes, OR
  // when the load effect kicks off a fresh load (loadState !== 'ready'
  // means we either just started fetching or aren't loaded).
  useEffect(() => {
    appliedSigRef.current = '';
  }, [activeDocPath, effectiveTabKey]);
  useEffect(() => {
    if (loadState !== 'ready') {
      appliedSigRef.current = '';
    }
  }, [loadState]);

  useEffect(() => {
    if (!isReady) return;
    if (loadState !== 'ready') return;
    const container = editorRef.current;
    if (!container?.documentEditor) return;

    // Compose the sig that uniquely identifies the highlight target
    // for the current (doc, vars, tab) state.
    const sig = shouldHighlightPlaceholders
      ? `tpl:${activeDocPath ?? 'syn'}:${variableNamesSig}`
      : `val:${activeDocPath ?? '-'}:${effectiveTabKey}:${resolvedTargetsSig}`;
    if (appliedSigRef.current === sig) return;
    // Skip empty work — no vars / no targets means nothing to mark.
    if (shouldHighlightPlaceholders && variableNamesRef.current.length === 0) {
      return;
    }
    if (!shouldHighlightPlaceholders && activeResolvedTargetsRef.current.length === 0) {
      return;
    }
    appliedSigRef.current = sig;
    try {
      if (shouldHighlightPlaceholders) {
        applyPlaceholderHighlights(
          container.documentEditor,
          variableNamesRef.current,
        );
      } else {
        applyResolvedValueHighlights(container.documentEditor);
      }
    } catch (err) {
      console.warn('[TemplatePreviewV2] highlight pass failed', err);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isReady,
    loadState,
    shouldHighlightPlaceholders,
    variableNamesSig,
    resolvedTargetsSig,
    activeDocPath,
    effectiveTabKey,
  ]);

  // Keep the latest onSelectVariable callback in a ref so the
  // selectionChange wiring effect below doesn't re-attach when the page
  // re-renders with a new inline arrow (every keystroke in any modal).
  const onSelectVariableRef = useRef(onSelectVariable);
  onSelectVariableRef.current = onSelectVariable;

  // Click-to-edit only fires on the Template tab. On Draft / companion
  // tabs the bookmarks still exist (so the highlight pass can place them),
  // but clicks are inspection-only.
  const allowVariableClicksRef = useRef<boolean>(true);
  allowVariableClicksRef.current = effectiveTab.kind === 'template';

  // Wire selectionChange to detect placeholder clicks/cursor moves.
  useEffect(() => {
    if (!isReady) return;
    const container = editorRef.current;
    if (!container?.documentEditor) return;
    const documentEditor = container.documentEditor;

    const handleSelectionChange = (): void => {
      // Ignore selection events fired during a programmatic doc rebuild —
      // insertBookmark / moveToDocumentStart shouldn't pop the wizard.
      if (isRebuildingRef.current) return;
      // Inspection-only on Draft / companion tabs — don't open wizard.
      if (!allowVariableClicksRef.current) return;
      try {
        // Read bookmarks at the cursor. We wrapped each [[placeholder]] in a
        // bookmark named `field_<var>_<idx>` at load time, so a click that
        // lands the cursor inside a placeholder gives us the field name here.
        const bookmarks: string[] = documentEditor.selection.bookmarks ?? [];
        let matchedVar: string | null = null;
        for (const bm of bookmarks) {
          const m = bm.match(/^field_(.+)_\d+$/);
          if (m && placeholderNamesRef.current.has(m[1])) {
            matchedVar = m[1];
            break;
          }
        }
        if (!matchedVar) {
          lastFiredVarRef.current = null;
          return;
        }
        if (lastFiredVarRef.current === matchedVar) return;
        lastFiredVarRef.current = matchedVar;
        onSelectVariableRef.current(matchedVar);
      } catch {
        // Selection access can throw transiently during load — ignore.
      }
    };

    documentEditor.selectionChange = handleSelectionChange;
    return () => {
      try {
        documentEditor.selectionChange = (): void => {};
      } catch {
        void 0;
      }
    };
  }, [isReady]);

  const hasResult = dryRunResult !== null && dryRunResult !== undefined;
  const childCount = dryRunResult?.children.length ?? 0;
  const downloadUrl = activeDocUrl ?? templateDocUrl ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-border bg-surface overflow-hidden">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border bg-surface-muted/40 px-3 py-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <FiFileText className="h-4 w-4 shrink-0 text-app-accent-text" />
          <span className="truncate text-xs font-semibold text-text-secondary">
            {activeDocLabel}
          </span>
          {effectiveTab.kind === 'template' && (
            <span className="ml-2 shrink-0 rounded-full bg-app-accent-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
              Live preview
            </span>
          )}
          {effectiveTab.kind !== 'template' && (
            <span className="ml-2 shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-800">
              Dry-run
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {effectiveTab.kind === 'template' && (
            <p className="text-[11px] italic text-subtle">
              Click any yellow{' '}
              <span className="rounded border border-amber-300 bg-amber-50 px-1 font-mono text-[10px] text-amber-900">
                [[placeholder]]
              </span>{' '}
              to configure.
            </p>
          )}
          {downloadUrl && (
            <a
              href={downloadUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[11px] font-semibold text-text-secondary hover:bg-surface-muted/50"
              title="Download this docx"
            >
              <FiDownload className="h-3 w-3" />
              Download .docx
            </a>
          )}
        </div>
      </div>

      {hasResult && (
        <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-surface-muted/30 px-3 py-1.5">
          <TabButton
            active={effectiveTab.kind === 'template'}
            onClick={() => setTab(TEMPLATE_TAB)}
            icon={<FiFileText className="h-3 w-3" />}
          >
            Template
          </TabButton>
          <TabButton
            active={effectiveTab.kind === 'draft'}
            onClick={() => setTab({ kind: 'draft' })}
            icon={<FiCheckCircle className="h-3 w-3" />}
          >
            Draft
          </TabButton>
          <TabButton
            active={effectiveTab.kind === 'log'}
            onClick={() => setTab({ kind: 'log' })}
            icon={<FiActivity className="h-3 w-3" />}
          >
            Resolution log
          </TabButton>
          {dryRunResult?.children.map((child, index) => (
            <TabButton
              key={`${child.template_id}-${index}`}
              active={
                effectiveTab.kind === 'companion' &&
                effectiveTab.index === index
              }
              onClick={() => setTab({ kind: 'companion', index })}
              icon={<FiLayers className="h-3 w-3" />}
              title={`${child.template_name} — ${child.companion_label}`}
            >
              <span className="max-w-[10rem] truncate">
                {child.template_name}
              </span>
            </TabButton>
          ))}
          {childCount > 0 && (
            <span className="ml-1 text-[10px] text-subtle">
              ({childCount} companion{childCount === 1 ? '' : 's'})
            </span>
          )}
        </div>
      )}

      {licenseWarning && (
        <div className="shrink-0 border-b border-amber-300 bg-amber-50 px-3 py-1.5 text-[11px] text-amber-900">
          {licenseWarning}
        </div>
      )}

      <div className="studio-v2-doc-editor relative min-h-0 flex-1">
        {/* Syncfusion stays mounted across tab swaps so we don't lose
            the loaded docx when the paralegal pops over to the log
            tab. When the log tab is active we hide the editor visually
            (visibility, not display:none — display:none would cause
            Syncfusion to lose its layout calculations). */}
        <div
          className={cn(
            'absolute inset-0',
            effectiveTab.kind === 'log' && 'invisible',
          )}
        >
          <DocumentEditorContainerComponent
            ref={editorRef}
            height="100%"
            enableToolbar={false}
            showPropertiesPane={false}
            serviceUrl={import.meta.env.VITE_SYNCFUSION_SERVER_URL}
            created={() => setIsReady(true)}
            documentChange={() => handleDocumentChangeRef.current()}
          />
        </div>
        {effectiveTab.kind === 'log' && dryRunResult && (
          <div className="absolute inset-0">
            <ResolutionLogPane result={dryRunResult} />
          </div>
        )}
        {effectiveTab.kind !== 'log' && loadState === 'loading' && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-surface/80">
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary shadow-sm">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-app-accent/30 border-t-app-accent" />
              Loading {activeDocLabel}…
            </span>
          </div>
        )}
        {loadState === 'error' && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface/95 px-6">
            <div className="max-w-md rounded-lg border border-app-danger-text/30 bg-app-danger-text/5 p-4 text-center">
              <FiAlertCircle className="mx-auto mb-2 h-5 w-5 text-app-danger-text" />
              <p className="text-sm font-semibold text-app-danger-text">
                Preview failed to load
              </p>
              <p className="mt-1 text-xs text-text-secondary">
                The docx couldn't be rendered. Try the Download button above to
                inspect the file directly.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const TabButton = ({
  active,
  onClick,
  icon,
  children,
  title,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
  title?: string;
}) => (
  <button
    type="button"
    onClick={onClick}
    title={title}
    className={
      'inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors ' +
      (active
        ? 'bg-surface text-app-accent-text shadow-sm'
        : 'text-subtle hover:bg-surface hover:text-text-secondary')
    }
  >
    {icon}
    {children}
  </button>
);

