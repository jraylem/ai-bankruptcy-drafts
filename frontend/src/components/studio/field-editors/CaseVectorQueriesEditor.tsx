import type { ReactElement } from 'react';
import { VariableReferenceInput } from './VariableReferenceInput';
import type { CaseVectorQueryEntry } from '@/types/studio';

interface CaseVectorQueriesEditorProps {
  value: CaseVectorQueryEntry[];
  onChange: (next: CaseVectorQueryEntry[]) => void;
}

export const CaseVectorQueriesEditor = ({
  value,
  onChange,
}: CaseVectorQueriesEditorProps): ReactElement => {
  const addEntry = (): void => {
    onChange([...value, { label: '', text_query: '' }]);
  };

  const updateEntry = (idx: number, patch: Partial<CaseVectorQueryEntry>): void => {
    onChange(value.map((entry, i) => (i === idx ? { ...entry, ...patch } : entry)));
  };

  const removeEntry = (idx: number): void => {
    onChange(value.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-2">
      {value.length === 0 && (
        <p className="rounded-md border border-dashed border-border bg-surface-muted/40 px-3 py-2 text-xs text-muted">
          No retrievals. Click "+ Add retrieval" to compose case-file chunks
          (e.g. Schedule I/J, Chapter 13 plan) into the chip generator's context.
        </p>
      )}
      {value.map((entry, idx) => (
        <div
          key={idx}
          className="rounded-lg border border-border bg-surface p-2 space-y-2"
        >
          <div className="flex items-start gap-2">
            <div className="flex-1 space-y-2">
              <div>
                <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-muted">
                  Label
                </label>
                <input
                  type="text"
                  value={entry.label}
                  onChange={(e) => updateEntry(idx, { label: e.target.value })}
                  placeholder="e.g. Current Schedule I & J"
                  className="w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
                />
              </div>
              <div>
                <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-muted">
                  Text query
                </label>
                <VariableReferenceInput
                  value={entry.text_query}
                  onChange={(v) => updateEntry(idx, { text_query: v })}
                  placeholder="Schedule I income Schedule J expenses"
                  ariaLabel={`Case vector query ${idx + 1} text_query`}
                />
              </div>
            </div>
            <button
              type="button"
              onClick={() => removeEntry(idx)}
              aria-label={`Remove retrieval ${idx + 1}`}
              className="mt-4 rounded-md border border-transparent px-2 py-1 text-sm text-muted hover:border-app-warning-soft hover:bg-app-warning-soft hover:text-app-warning-text"
            >
              ×
            </button>
          </div>
        </div>
      ))}
      <button
        type="button"
        onClick={addEntry}
        className="inline-flex items-center gap-1 rounded-md border border-dashed border-border bg-surface px-3 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-app-accent-soft hover:text-app-accent-text"
      >
        + Add retrieval
      </button>
    </div>
  );
};

export default CaseVectorQueriesEditor;
