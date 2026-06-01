import { useEffect, useMemo, useState, type ReactElement } from 'react';
import Lottie from 'lottie-react';
import { SelectDropdown } from '@/components/common';
import { TemplatePreview } from '@/components/studio/TemplatePreview';
import { useStudioStore } from '@/stores/useStudioStore';
import { useToastStore } from '@/stores/useToastStore';
import type { MergeOperation, TemplateVariable } from '@/types/studio';
import dryRunAnimation from '@/assets/lottie/dry-run.json';

const REGENERATE_PHRASES: Array<[string, string]> = [
  ['Re-examining', 'the record'],
  ['Re-extracting', 'the variables'],
  ['Reparsing', 'the document'],
  ['Reconsidering', 'the clauses'],
  ['Recomputing', 'the mappings'],
  ['Refreshing', 'the spec'],
  ['Realigning', 'the fragments'],
  ['Recalibrating', 'the agent'],
];

interface RegenerateTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface RowState {
  variable: TemplateVariable;
  ignored: boolean;
  mergeGroup: number | null;
}

const buildInitialRows = (spec: TemplateVariable[]): RowState[] =>
  spec.map((v) => ({ variable: v, ignored: false, mergeGroup: null }));

const collectMerges = (rows: RowState[]): MergeOperation[] => {
  const byGroup = new Map<number, string[]>();
  for (const r of rows) {
    if (r.mergeGroup === null) continue;
    const list = byGroup.get(r.mergeGroup) ?? [];
    list.push(r.variable.template_variable);
    byGroup.set(r.mergeGroup, list);
  }
  const merges: MergeOperation[] = [];
  for (const vars of byGroup.values()) {
    if (vars.length >= 2) merges.push({ source_variables: vars });
  }
  return merges;
};

const collectIgnoredTexts = (rows: RowState[]): string[] => {
  const texts: string[] = [];
  for (const r of rows) {
    if (!r.ignored) continue;
    const fragment = r.variable.template_identifying_text_match?.trim();
    if (fragment) texts.push(fragment);
  }
  return texts;
};

const GROUP_PALETTE: Array<{ ring: string; bg: string; text: string; dot: string }> = [
  { ring: 'ring-indigo-300', bg: 'bg-app-accent-soft', text: 'text-app-accent-text', dot: 'bg-indigo-500' },
  { ring: 'ring-emerald-300', bg: 'bg-app-success-soft', text: 'text-app-success-text', dot: 'bg-emerald-500' },
  { ring: 'ring-sky-300', bg: 'bg-sky-50', text: 'text-sky-700', dot: 'bg-sky-500' },
  { ring: 'ring-rose-300', bg: 'bg-rose-50', text: 'text-rose-700', dot: 'bg-rose-500' },
  { ring: 'ring-violet-300', bg: 'bg-violet-50', text: 'text-violet-700', dot: 'bg-violet-500' },
  { ring: 'ring-amber-300', bg: 'bg-app-warning-soft', text: 'text-app-warning-text', dot: 'bg-amber-500' },
];

const groupStyle = (group: number) => GROUP_PALETTE[(group - 1) % GROUP_PALETTE.length];

export const RegenerateTemplateModal = ({
  isOpen,
  onClose,
}: RegenerateTemplateModalProps): ReactElement | null => {
  const templateSpec = useStudioStore((s) => s.templateSpec);
  const originalDocUrl = useStudioStore((s) => s.originalDocUrl);
  const regenerateTemplate = useStudioStore((s) => s.regenerateTemplate);
  const isUploadingTemplate = useStudioStore((s) => s.isUploadingTemplate);
  const clearRegenerateDiff = useStudioStore((s) => s.clearRegenerateDiff);
  const addToast = useToastStore((s) => s.addToast);

  const [rows, setRows] = useState<RowState[]>(() => buildInitialRows(templateSpec));
  const [regenerationInstruction, setRegenerationInstruction] = useState<string>('');
  const [groupCursor, setGroupCursor] = useState<number>(1);
  const [verbIndex, setVerbIndex] = useState<number>(0);
  const [previewTab, setPreviewTab] = useState<'template' | 'original'>('template');

  useEffect(() => {
    if (isOpen) {
      setRows(buildInitialRows(templateSpec));
      setRegenerationInstruction('');
      setGroupCursor(1);
      // Drop any stale diff from a prior regenerate when the user
      // re-opens the modal to author a fresh pass — the summary only
      // makes sense for the just-completed run.
      clearRegenerateDiff();
    }
  }, [isOpen, templateSpec, clearRegenerateDiff]);

  useEffect(() => {
    if (!isUploadingTemplate) return;
    setVerbIndex(0);
    const id = window.setInterval(() => {
      setVerbIndex((i) => (i + 1) % REGENERATE_PHRASES.length);
    }, 1800);
    return () => window.clearInterval(id);
  }, [isUploadingTemplate]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape' && !isUploadingTemplate) onClose();
    };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [isOpen, isUploadingTemplate, onClose]);

  const merges = useMemo((): MergeOperation[] => collectMerges(rows), [rows]);
  const ignoredCount = useMemo(
    (): number => rows.filter((r) => r.ignored).length,
    [rows]
  );
  const inGroupCount = useMemo(
    (): number => rows.filter((r) => r.mergeGroup !== null).length,
    [rows]
  );
  const trimmedInstruction = regenerationInstruction.trim();

  if (!isOpen) return null;

  const toggleIgnored = (idx: number): void =>
    setRows((prev) =>
      prev.map((r, i) =>
        i === idx
          ? { ...r, ignored: !r.ignored, mergeGroup: !r.ignored ? null : r.mergeGroup }
          : r
      )
    );

  const setMergeGroup = (idx: number, group: number | null): void =>
    setRows((prev) =>
      prev.map((r, i) =>
        i === idx ? { ...r, mergeGroup: group, ignored: group !== null ? false : r.ignored } : r
      )
    );

  const startNewGroup = (): void => {
    setGroupCursor((g) => g + 1);
  };

  const hasChanges =
    ignoredCount > 0 || merges.length > 0 || trimmedInstruction.length > 0;

  const handleSubmit = async (): Promise<void> => {
    const ignoredTexts = collectIgnoredTexts(rows);
    const result = await regenerateTemplate(
      ignoredTexts,
      merges,
      trimmedInstruction.length > 0 ? trimmedInstruction : null,
    );
    if (!result.success) {
      addToast(result.error ?? 'Regenerate failed', 'error');
      return;
    }
    addToast(
      'Template regenerated — agent config cleared. Re-save configuration when ready.',
      'success'
    );
    // Close the modal. The diff summary (staged in the store) renders
    // as a banner on the studio page above Bundle Settings so the user
    // sees the changes immediately without the modal in the way.
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay px-4 py-8 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="regenerate-modal-title"
    >
      <div className="flex max-h-[min(92vh,900px)] w-full max-w-7xl flex-col overflow-hidden rounded-2xl bg-surface shadow-[0_24px_60px_-12px_rgba(15,23,42,0.25)] ring-1 ring-black/5">
        <header className="flex items-start gap-4 border-b border-border px-6 py-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-app-accent-soft text-app-accent-text ring-1 ring-inset ring-indigo-100">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="regenerate-modal-title" className="text-lg font-semibold tracking-tight text-text-secondary">
              Regenerate template
            </h2>
            <p className="mt-0.5 text-sm leading-relaxed text-muted">
              Re-run extraction on the same source document with author-specified ignored
              fragments and variable merges.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isUploadingTemplate}
            className="rounded-lg p-1.5 text-subtle transition hover:bg-surface-muted hover:text-text-secondary focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-40"
            aria-label="Close"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        {isUploadingTemplate ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-8">
            <Lottie
              animationData={dryRunAnimation}
              loop
              autoplay
              className="h-64 w-full"
            />
            <p
              key={verbIndex}
              className="animate-verb-in text-lg font-semibold text-text-secondary"
            >
              {REGENERATE_PHRASES[verbIndex][0]} {REGENERATE_PHRASES[verbIndex][1]}…
            </p>
            <p className="text-sm text-muted">
              Re-running extraction on the source document — this can take a moment.
            </p>
          </div>
        ) : (
        <>
        {/* Two-column body: left = controls (scrollable), right = live
           template preview (Syncfusion). Stacks vertically on smaller
           screens (lg:flex-row) so mobile keeps the existing flow. */}
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        {/* Left column: original scroll area carrying diff summary,
           warning, variables list, regeneration instruction. */}
        <div className="flex min-h-0 flex-col overflow-hidden lg:w-[520px] lg:shrink-0">
        <div className="flex-1 overflow-y-auto">
        {/* Diff summary moved out of the modal — renders as a banner on the
           studio page above Bundle Settings via <RegenerateDiffSummary /> in
           pages/studio/index.tsx. The modal closes on success so the user
           sees the diff immediately on the workspace. */}
        <div className="mx-6 mt-4 flex items-start gap-2.5 rounded-lg border border-app-warning-soft bg-app-warning-soft/60 px-3.5 py-2.5 text-xs text-amber-900">
          <svg className="mt-0.5 h-4 w-4 shrink-0 text-app-warning-text" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
            />
          </svg>
          <p className="leading-relaxed">
            Regeneration <span className="font-semibold">clears the saved agent config</span>.
            You'll need to re-save configuration after the new variable set lands.
          </p>
        </div>

        <div className="px-6 py-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              Existing variables
            </h3>
            <span className="text-[11px] text-subtle">
              {rows.length} total
            </span>
          </div>

          {rows.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-surface-muted/50 px-4 py-8 text-center">
              <p className="text-sm text-muted">No variables in the current spec.</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {rows.map((r, idx) => {
                const style = r.mergeGroup !== null ? groupStyle(r.mergeGroup) : null;
                return (
                  <li
                    key={r.variable.template_variable}
                    className={`group flex flex-col gap-3 rounded-xl border px-4 py-3 transition sm:flex-row sm:flex-wrap sm:items-start ${
                      r.ignored
                        ? 'border-border bg-surface-muted/60'
                        : style
                          ? `border-transparent ring-1 ring-inset ${style.ring} ${style.bg}`
                          : 'border-border bg-surface hover:border-border'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <code
                          className={`inline-block max-w-full break-all rounded-md bg-slate-900 px-2 py-0.5 font-mono text-[11px] font-medium text-slate-100 ${
                            r.ignored ? 'line-through opacity-60' : ''
                          }`}
                        >
                          [[{r.variable.template_variable}]]
                        </code>
                        {r.ignored && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
                            Ignored
                          </span>
                        )}
                        {style && (
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${style.text} ${style.bg} ring-1 ring-inset ${style.ring}`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                            Merge {r.mergeGroup}
                          </span>
                        )}
                      </div>
                      {r.variable.template_identifying_text_match && (
                        <p
                          className="mt-1.5 truncate text-xs text-muted"
                          title={r.variable.template_identifying_text_match}
                        >
                          &ldquo;{r.variable.template_identifying_text_match}&rdquo;
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-3">
                      <label className="inline-flex cursor-pointer items-center gap-1.5 select-none">
                        <input
                          type="checkbox"
                          checked={r.ignored}
                          onChange={() => toggleIgnored(idx)}
                          className="h-3.5 w-3.5 rounded border-border text-text-secondary focus:ring-slate-400"
                        />
                        <span className="text-xs font-medium text-muted">Ignore</span>
                      </label>
                      <div
                        className={r.ignored ? 'pointer-events-none opacity-50' : ''}
                        title="Assign this variable to a merge group — variables in the same group are merged into one"
                      >
                        <SelectDropdown
                          value={r.mergeGroup === null ? '' : String(r.mergeGroup)}
                          onChange={(v) => setMergeGroup(idx, v === '' ? null : Number(v))}
                          options={[
                            { label: 'No merge', value: '' },
                            ...Array.from({ length: groupCursor }).map((_, gi) => ({
                              label: `Merge ${gi + 1}`,
                              value: String(gi + 1),
                            })),
                          ]}
                          className="w-36"
                          buttonClassName="flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-left text-xs font-medium text-text-secondary transition hover:border-border focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                        />
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <button
            type="button"
            onClick={startNewGroup}
            className="mt-3 inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold text-app-accent-text transition hover:bg-app-accent-soft hover:text-indigo-800"
          >
            <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New merge group
          </button>

          <div className="mt-6 mb-2 flex items-baseline justify-between">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              Regeneration instruction
            </h3>
            <span className="text-[11px] text-subtle">optional</span>
          </div>
          <textarea
            value={regenerationInstruction}
            onChange={(e) => setRegenerationInstruction(e.target.value)}
            rows={6}
            placeholder="Free-form steering for the template agent (e.g. 'Merge claim_no and claim_no_title', 'Don't extract the clerk address')."
            className="min-h-[140px] w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm leading-relaxed text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
          <p className="mt-1 text-[10px] text-subtle">
            Threaded into the template agent's extract prompt as a high-priority directive
            alongside the ignored fragments and merge groups above.
          </p>
        </div>
        </div>{/* end left-column scroll area */}
        </div>{/* end left column */}

        {/* Right column: live template preview. Reuses the Syncfusion-
           based <TemplatePreview /> from the studio page, locked to
           template mode. Hidden on smaller breakpoints to keep the
           single-column flow intact below the lg threshold. */}
        <div className="flex min-h-[55vh] flex-col overflow-hidden border-t border-border bg-surface-muted lg:min-h-0 lg:flex-1 lg:border-l lg:border-t-0">
          <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface px-4 py-3">
            <svg
              className="h-4 w-4 text-app-accent-text"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <p className="text-sm font-semibold text-text-secondary">
              {previewTab === 'original' ? 'Original source preview' : 'Template preview'}
            </p>
            <p className="ml-auto text-[11px] text-subtle">
              Reference while authoring merges / ignores
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1 border-b border-border bg-surface-muted/60 px-4 py-1">
            <div className="inline-flex flex-wrap gap-1 rounded-lg border border-border bg-surface p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setPreviewTab('template')}
                title="Show the extracted template with placeholder variables"
                className={`rounded-md px-3 py-1 font-semibold transition-colors ${
                  previewTab === 'template'
                    ? 'bg-surface-muted text-app-accent-text shadow-sm'
                    : 'text-muted hover:text-text-secondary'
                }`}
              >
                Template
              </button>
              <button
                type="button"
                onClick={() => setPreviewTab('original')}
                disabled={!originalDocUrl}
                title={
                  originalDocUrl
                    ? 'Show the original uploaded .docx (pre-extraction source)'
                    : 'No original source available yet'
                }
                className={`rounded-md px-3 py-1 font-semibold transition-colors ${
                  previewTab === 'original'
                    ? 'bg-surface-muted text-app-accent-text shadow-sm'
                    : 'text-muted hover:text-text-secondary disabled:cursor-not-allowed disabled:text-subtle disabled:hover:text-subtle'
                }`}
              >
                Original
              </button>
            </div>
          </div>
          <div className="relative min-h-0 flex-1 overflow-hidden">
            <TemplatePreview
              mode={previewTab}
              onExport={() => {}}
            />
          </div>
        </div>
        </div>{/* end 2-column body */}

        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface-muted/70 px-6 py-4">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-muted">
            <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 ring-1 ring-inset ring-slate-200">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
              {ignoredCount} ignored
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 ring-1 ring-inset ring-slate-200">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
              {trimmedInstruction.length > 0 ? '1' : '0'} instruction
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 ring-1 ring-inset ring-slate-200">
              <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
              {merges.length} merge{merges.length === 1 ? '' : 's'}
              {inGroupCount > 0 && (
                <span className="ml-0.5 text-subtle">({inGroupCount} vars)</span>
              )}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isUploadingTemplate}
              className="rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-semibold text-text-secondary transition hover:bg-surface-muted focus:outline-none focus:ring-2 focus:ring-slate-200 disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={isUploadingTemplate || !hasChanges}
              title={
                !hasChanges
                  ? 'Ignore at least one variable, add a merge group, or paste a fragment to regenerate'
                  : undefined
              }
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-1 disabled:cursor-not-allowed disabled:bg-indigo-400"
            >
              {isUploadingTemplate && (
                <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {isUploadingTemplate ? 'Regenerating…' : 'Regenerate template'}
            </button>
          </div>
        </footer>
        </>
        )}
      </div>
    </div>
  );
};

export default RegenerateTemplateModal;
