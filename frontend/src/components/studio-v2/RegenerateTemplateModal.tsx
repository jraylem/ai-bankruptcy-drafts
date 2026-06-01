import { useEffect, useMemo, useState } from 'react';
import {
  FiAlertTriangle,
  FiLayers,
  FiRefreshCw,
  FiX,
} from 'react-icons/fi';
import { Modal } from '@/components/common';
import { cn } from '@/utils';
import type { MergeOperationV2 } from '@/types/studio-v2';
import type { StudioVariable } from './types';
import { RunningAnimation } from './RunningAnimation';

interface RegenerateTemplateModalProps {
  isOpen: boolean;
  templateName: string;
  variables: StudioVariable[];
  busy: boolean;
  onConfirm: (payload: {
    ignored_texts: string[];
    merges: MergeOperationV2[];
    regeneration_instruction: string | null;
  }) => Promise<void>;
  onClose: () => void;
}

interface RowState {
  variable: StudioVariable;
  ignored: boolean;
  mergeGroup: number | null;
}

const GROUP_PALETTE: Array<{ border: string; bg: string; text: string; dot: string }> = [
  { border: 'border-indigo-300', bg: 'bg-indigo-50', text: 'text-indigo-700', dot: 'bg-indigo-500' },
  { border: 'border-emerald-300', bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
  { border: 'border-sky-300', bg: 'bg-sky-50', text: 'text-sky-700', dot: 'bg-sky-500' },
  { border: 'border-rose-300', bg: 'bg-rose-50', text: 'text-rose-700', dot: 'bg-rose-500' },
  { border: 'border-amber-300', bg: 'bg-amber-50', text: 'text-amber-900', dot: 'bg-amber-500' },
  { border: 'border-violet-300', bg: 'bg-violet-50', text: 'text-violet-700', dot: 'bg-violet-500' },
];

const groupStyle = (group: number) => GROUP_PALETTE[(group - 1) % GROUP_PALETTE.length];

const buildInitialRows = (variables: StudioVariable[]): RowState[] =>
  variables.map((v) => ({ variable: v, ignored: false, mergeGroup: null }));

const collectMerges = (rows: RowState[]): MergeOperationV2[] => {
  const byGroup = new Map<number, RowState[]>();
  for (const r of rows) {
    if (r.mergeGroup === null) continue;
    const list = byGroup.get(r.mergeGroup) ?? [];
    list.push(r);
    byGroup.set(r.mergeGroup, list);
  }
  const merges: MergeOperationV2[] = [];
  for (const [, rs] of byGroup) {
    if (rs.length < 2) continue;
    const source_variables = rs.map((r) => r.variable.template_variable);
    // Sensible default name — paralegal can override after the regenerate
    // lands by re-naming via the wizard. The agent uses this name verbatim
    // for the merged variable's template_variable field.
    const new_variable_name = source_variables.join('_and_');
    merges.push({ new_variable_name, source_variables });
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

export const RegenerateTemplateModal = ({
  isOpen,
  templateName,
  variables,
  busy,
  onConfirm,
  onClose,
}: RegenerateTemplateModalProps) => {
  const [rows, setRows] = useState<RowState[]>(() => buildInitialRows(variables));
  const [instruction, setInstruction] = useState('');

  useEffect(() => {
    if (isOpen) {
      setRows(buildInitialRows(variables));
      setInstruction('');
    }
  }, [isOpen, variables]);

  // Available group numbers in the dropdown: every group currently in
  // use, PLUS one empty next group so the paralegal can always reach a
  // fresh group number without hunting for a "new group" button. e.g.
  // no rows grouped → [1]; one row in group 1 → [1, 2]; rows in 1 and
  // 3 → [1, 2, 3, 4]. We fill the gaps so the numbering stays dense.
  const availableGroups = useMemo(() => {
    const used = new Set(rows.map((r) => r.mergeGroup).filter((g): g is number => g !== null));
    const max = used.size > 0 ? Math.max(...used) : 0;
    return Array.from({ length: max + 1 }, (_, i) => i + 1);
  }, [rows]);

  const merges = useMemo(() => collectMerges(rows), [rows]);
  const ignoredCount = useMemo(() => rows.filter((r) => r.ignored).length, [rows]);
  const inGroupCount = useMemo(
    () => rows.filter((r) => r.mergeGroup !== null).length,
    [rows],
  );
  const trimmedInstruction = instruction.trim();
  const hasChanges =
    ignoredCount > 0 || merges.length > 0 || trimmedInstruction.length > 0;

  const toggleIgnored = (idx: number): void =>
    setRows((prev) =>
      prev.map((r, i) =>
        i === idx
          ? { ...r, ignored: !r.ignored, mergeGroup: !r.ignored ? null : r.mergeGroup }
          : r,
      ),
    );

  const setMergeGroup = (idx: number, group: number | null): void =>
    setRows((prev) =>
      prev.map((r, i) =>
        i === idx
          ? { ...r, mergeGroup: group, ignored: group !== null ? false : r.ignored }
          : r,
      ),
    );

  const handleSubmit = async (): Promise<void> => {
    if (!hasChanges || busy) return;
    await onConfirm({
      ignored_texts: collectIgnoredTexts(rows),
      merges,
      regeneration_instruction:
        trimmedInstruction.length > 0 ? trimmedInstruction : null,
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="3xl"
      closeOnBackdropClick={false}
    >
      <div className="flex max-h-[min(85vh,780px)] flex-col">
        <header className="shrink-0 border-b border-border px-6 py-5 pr-12">
          <p className="text-xs font-semibold uppercase tracking-wider text-app-accent-text">
            {busy ? 'Re-reading template' : 'Re-read this template'}
          </p>
          <h2
            className="mt-1 truncate text-lg font-semibold text-text-secondary"
            title={templateName}
          >
            {templateName}
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {busy
              ? 'This usually takes 15–60 seconds. You can keep this window open, or hide it — the agent keeps running and the variable list will refresh automatically when it finishes.'
              : "Have the AI re-scan the original document with your guidance. Use this when the AI missed something, picked up boilerplate it shouldn't have, or split a single value into too many fields."}
          </p>
        </header>

        {busy && (
          <>
            <div className="flex min-h-[360px] flex-1 flex-col items-center justify-center bg-surface-muted/30 px-6 py-10">
              <RunningAnimation
                phase="re_reading"
                caseLabel={templateName}
                size="md"
              />
            </div>
            <footer className="flex shrink-0 items-center justify-end gap-3 border-t border-border bg-surface px-6 py-4">
              <button
                type="button"
                onClick={onClose}
                className="cursor-pointer rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-semibold text-text-secondary hover:bg-surface-muted"
              >
                Hide — keep running
              </button>
            </footer>
          </>
        )}

        {!busy && (
          <>
        {/* idle body opens below — closing tags balance after the original
            scroll-pane + footer, see the closing `</>` further down. */}

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <div className="flex items-start gap-2.5 rounded-lg border border-amber-300 bg-amber-50 px-3.5 py-2.5 text-xs text-amber-900">
            <FiAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p className="leading-relaxed">
              Re-reading the template <span className="font-semibold">replaces the
              variable list</span>. Settings you've already saved on variables
              that stay around (same name) are kept. New variables start
              unconfigured.
            </p>
          </div>

          <section className="mt-5">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-app-accent-text">
              Step 1 · Tell the AI what to do differently
              <span className="ml-2 text-[10px] font-medium normal-case tracking-normal text-subtle">
                optional but recommended
              </span>
            </h3>
            <p className="mt-1 text-[11px] text-subtle">
              Plain English is fine. The AI treats this as binding — it follows
              your instruction exactly, even if it overrides the default rules.
            </p>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              rows={5}
              placeholder={`e.g. "Split the case number into a civil case number and a bankruptcy case number" — or — "Don't extract the firm address at the bottom — it's boilerplate" — or — "The debtor's name should be one variable, not two"`}
              disabled={busy}
              className="mt-2 min-h-[110px] w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm leading-relaxed text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-50"
            />
          </section>

          <section className="mt-6">
            <div className="flex items-baseline justify-between">
              <div>
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-app-accent-text">
                  Step 2 · Skip or group variables
                  <span className="ml-2 text-[10px] font-medium normal-case tracking-normal text-subtle">
                    optional
                  </span>
                </h3>
                <p className="mt-1 text-[11px] text-subtle">
                  Check <strong>Skip</strong> to drop a variable from the
                  re-read. Pick the same <strong>Group</strong> for two or
                  more variables to merge them into one.
                </p>
              </div>
              <span className="rounded-full bg-surface-muted px-2 py-0.5 text-[10px] font-semibold text-subtle">
                {rows.length} total
              </span>
            </div>

            {rows.length === 0 ? (
              <div className="mt-3 rounded-xl border border-dashed border-border bg-surface-muted/50 px-4 py-8 text-center">
                <p className="text-sm text-subtle">No variables to adjust yet.</p>
              </div>
            ) : (
              <ul className="mt-3 space-y-2">
                {rows.map((r, idx) => {
                  const style = r.mergeGroup !== null ? groupStyle(r.mergeGroup) : null;
                  return (
                    <li
                      key={r.variable.template_variable}
                      className={cn(
                        'flex flex-col gap-3 rounded-xl border px-3.5 py-2.5 transition sm:flex-row sm:flex-wrap sm:items-start',
                        r.ignored && 'border-border bg-surface-muted/60',
                        !r.ignored && style && `${style.border} ${style.bg}`,
                        !r.ignored && !style && 'border-border bg-surface',
                      )}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <code
                            className={cn(
                              'inline-block max-w-full break-all rounded-md bg-slate-900 px-2 py-0.5 font-mono text-[11px] font-medium text-slate-100',
                              r.ignored && 'line-through opacity-60',
                            )}
                          >
                            [[{r.variable.template_variable}]]
                          </code>
                          {r.ignored && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
                              Skipping
                            </span>
                          )}
                          {style && (
                            <span
                              className={cn(
                                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
                                style.border,
                                style.text,
                                style.bg,
                              )}
                            >
                              <span className={cn('h-1.5 w-1.5 rounded-full', style.dot)} />
                              Group {r.mergeGroup}
                            </span>
                          )}
                        </div>
                        {r.variable.template_identifying_text_match && (
                          <p
                            className="mt-1 truncate text-[11px] italic text-subtle"
                            title={r.variable.template_identifying_text_match}
                          >
                            “{r.variable.template_identifying_text_match}”
                          </p>
                        )}
                      </div>

                      <div className="flex shrink-0 items-center gap-3">
                        <label className="inline-flex cursor-pointer items-center gap-1.5 select-none">
                          <input
                            type="checkbox"
                            checked={r.ignored}
                            onChange={() => toggleIgnored(idx)}
                            disabled={busy}
                            className="h-3.5 w-3.5 rounded border-border text-app-danger-text focus:ring-app-danger-text/30 disabled:opacity-50"
                          />
                          <span className="text-xs font-medium text-text-secondary">Skip</span>
                        </label>
                        <div
                          className={cn(r.ignored && 'pointer-events-none opacity-50')}
                          title="Pick the same group for two or more variables to merge them into one"
                        >
                          <select
                            value={r.mergeGroup === null ? '' : String(r.mergeGroup)}
                            onChange={(e) =>
                              setMergeGroup(idx, e.target.value === '' ? null : Number(e.target.value))
                            }
                            disabled={busy}
                            className="rounded-md border border-border bg-surface px-2 py-1 text-xs font-medium text-text-secondary focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft disabled:opacity-50"
                          >
                            <option value="">No group</option>
                            {availableGroups.map((gi) => (
                              <option key={gi} value={String(gi)}>
                                Group {gi}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}

            <p className="mt-2 text-[10px] italic text-subtle">
              Tip: rows in the same group get merged into ONE variable
              when re-read. For multiple separate merges, pick different
              group numbers (e.g. Group 1 for two rows, Group 2 for
              another pair).
            </p>
          </section>
        </div>

        <footer className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border bg-surface-muted/60 px-6 py-4">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-text-secondary">
            <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 ring-1 ring-inset ring-border">
              <FiX className="h-2.5 w-2.5 text-app-danger-text" />
              {ignoredCount} skipped
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 ring-1 ring-inset ring-border">
              <FiLayers className="h-2.5 w-2.5 text-app-accent-text" />
              {merges.length} group
              {merges.length === 1 ? '' : 's'}
              {inGroupCount > 0 && (
                <span className="ml-0.5 text-subtle">({inGroupCount} vars)</span>
              )}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 ring-1 ring-inset ring-border">
              <FiRefreshCw className="h-2.5 w-2.5 text-app-accent-text" />
              {trimmedInstruction.length > 0 ? '1' : '0'} instruction
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="cursor-pointer rounded-lg border border-border bg-surface px-3.5 py-2 text-sm font-semibold text-text-secondary transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={busy || !hasChanges}
              title={
                !hasChanges
                  ? 'Add an instruction, skip at least one variable, or group some variables to re-read the template.'
                  : undefined
              }
              className={cn(
                'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-opacity',
                hasChanges && !busy
                  ? 'cursor-pointer bg-app-accent text-white hover:opacity-90'
                  : 'cursor-not-allowed bg-surface-muted text-subtle',
              )}
            >
              <FiRefreshCw className="h-3.5 w-3.5" />
              Re-read template
            </button>
          </div>
        </footer>
          </>
        )}
      </div>
    </Modal>
  );
};
