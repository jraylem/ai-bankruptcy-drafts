/**
 * Shape of the shared fields between MultiSelectFromCaseVectorSourceParams
 * and MultiSelectFromGmailSourceParams. The two variants differ only in
 * their query inputs (text_query vs subject_query/body_query/scope), so
 * everything else lives here for reuse.
 */
export interface MultiSelectShared {
  label: string;
  instruction?: string | null;
  example_formats: string[];
  min_picks?: number;
  max_picks?: number | null;
  list_joiner?: string;
  oxford?: boolean;
}

import type { ReactElement } from 'react';

interface MultiSelectSharedFieldsProps<T extends MultiSelectShared> {
  value: T;
  onChange: (next: T) => void;
}

export function MultiSelectSharedFields<T extends MultiSelectShared>({
  value,
  onChange,
}: MultiSelectSharedFieldsProps<T>): ReactElement {
  const patch = (next: Partial<T>): void => {
    onChange({ ...value, ...next });
  };

  return (
    <>
      <div>
        <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-muted">
          Label *
        </label>
        <input
          type="text"
          value={value.label}
          onChange={(e) => patch({ label: e.target.value } as Partial<T>)}
          placeholder="e.g. Select Assets for Reaffirmation"
          className="w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        />
      </div>

      <div>
        <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-muted">
          Instruction
        </label>
        <input
          type="text"
          value={value.instruction ?? ''}
          onChange={(e) => patch({ instruction: e.target.value || null } as Partial<T>)}
          placeholder="e.g. Select the items you want to mention in the motion."
          className="w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        />
      </div>

      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Example formats *
          </label>
          <span className="text-[10px] text-subtle">(one or more shapes)</span>
        </div>
        <div className="space-y-2">
          {(value.example_formats ?? []).length === 0 && (
            <p className="rounded-md border border-dashed border-border bg-surface-muted/40 px-3 py-2 text-xs text-muted">
              No example formats. Click "+ Add format" — the LLM extracts options matching ANY of these shapes.
            </p>
          )}
          {(value.example_formats ?? []).map((fmt, idx) => (
            <div key={idx} className="flex items-start gap-2">
              <div className="flex-1">
                <input
                  type="text"
                  value={fmt}
                  onChange={(e) => {
                    const next = [...(value.example_formats ?? [])];
                    next[idx] = e.target.value;
                    patch({ example_formats: next } as Partial<T>);
                  }}
                  placeholder='e.g. 2018 Mercedes G-Wagon, VIN# X ("Vehicle")'
                  className="w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                />
              </div>
              <div className="flex flex-col gap-1">
                <button
                  type="button"
                  onClick={() => {
                    const next = [...(value.example_formats ?? [])];
                    if (idx === 0) return;
                    [next[idx - 1], next[idx]] = [next[idx]!, next[idx - 1]!];
                    patch({ example_formats: next } as Partial<T>);
                  }}
                  disabled={idx === 0}
                  aria-label={`Move format ${idx + 1} up`}
                  className="rounded border border-transparent px-1.5 py-0.5 text-xs text-muted hover:border-border hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-30"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const next = [...(value.example_formats ?? [])];
                    if (idx === next.length - 1) return;
                    [next[idx + 1], next[idx]] = [next[idx]!, next[idx + 1]!];
                    patch({ example_formats: next } as Partial<T>);
                  }}
                  disabled={idx === (value.example_formats?.length ?? 0) - 1}
                  aria-label={`Move format ${idx + 1} down`}
                  className="rounded border border-transparent px-1.5 py-0.5 text-xs text-muted hover:border-border hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-30"
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const next = (value.example_formats ?? []).filter((_, i) => i !== idx);
                    patch({ example_formats: next } as Partial<T>);
                  }}
                  aria-label={`Remove format ${idx + 1}`}
                  className="rounded border border-transparent px-1.5 py-0.5 text-xs text-muted hover:border-app-warning-soft hover:bg-app-warning-soft hover:text-app-warning-text"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => {
              patch({ example_formats: [...(value.example_formats ?? []), ''] } as Partial<T>);
            }}
            className="inline-flex items-center gap-1 rounded-md border border-dashed border-border bg-surface px-3 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-app-accent-soft hover:text-app-accent-text"
          >
            + Add format
          </button>
        </div>
        <p className="mt-2 text-[10px] text-subtle">
          Add multiple shapes when one source produces options of different forms (e.g. vehicles AND properties in one asset picker). Multi-line entries (using <span className="font-mono">\n</span>) render as multi-line cards at draft time.
        </p>
      </div>

      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">Selection bounds</div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-0.5 block text-[10px] text-muted">Min picks</label>
            <input
              type="number"
              min={0}
              value={value.min_picks ?? 1}
              onChange={(e) => {
                const n = parseInt(e.target.value, 10);
                patch({ min_picks: Number.isFinite(n) ? Math.max(0, n) : 0 } as Partial<T>);
              }}
              className="w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-secondary focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] text-muted">
              Max picks <span className="text-subtle">(empty = unbounded)</span>
            </label>
            <input
              type="number"
              min={value.min_picks ?? 0}
              value={value.max_picks ?? ''}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === '') {
                  patch({ max_picks: null } as Partial<T>);
                  return;
                }
                const n = parseInt(raw, 10);
                patch({ max_picks: Number.isFinite(n) ? n : null } as Partial<T>);
              }}
              className="w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-secondary focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
          </div>
        </div>
      </div>

      <div>
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted">Join style</div>
        <p className="mb-2 text-[10px] text-subtle">
          Picked options are joined into one prose string for the docx slot. Oxford-comma renders 1/2/3+ picks as 'A', 'A and B', 'A, B, and C'.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-0.5 flex items-center gap-1.5 text-[10px] text-muted">
              <input
                type="checkbox"
                checked={value.oxford ?? true}
                onChange={(e) => patch({ oxford: e.target.checked } as Partial<T>)}
                className="h-3 w-3 rounded border-border text-app-accent focus:ring-app-accent-soft"
              />
              Oxford-comma
            </label>
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] text-muted">List joiner</label>
            <input
              type="text"
              value={value.list_joiner ?? ', '}
              onChange={(e) => patch({ list_joiner: e.target.value } as Partial<T>)}
              placeholder=", "
              className="w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
          </div>
        </div>
      </div>
    </>
  );
}
