import type { ReactElement } from 'react';
import { VariableReferenceInput } from './VariableReferenceInput';
import { MultiSelectSharedFields } from './MultiSelectSharedFields';
import type { MultiSelectFromCaseVectorSourceParams } from '@/types/studio';

interface MultiSelectEditorProps {
  value: MultiSelectFromCaseVectorSourceParams;
  onChange: (next: MultiSelectFromCaseVectorSourceParams) => void;
}

export const MultiSelectEditor = ({
  value,
  onChange,
}: MultiSelectEditorProps): ReactElement => {
  const patch = (next: Partial<MultiSelectFromCaseVectorSourceParams>): void => {
    onChange({ ...value, ...next });
  };

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-dashed border-border bg-surface-muted/40 px-3 py-2 text-xs text-muted">
        Pre-fetched at draft time. The BE searches case PDFs with{' '}
        <span className="font-mono">text_query</span>, extracts up to 20 distinct
        options matching <span className="font-mono">example_formats</span>, and
        the user picks one or more in a multi-select card UI.
      </div>

      <div>
        <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-muted">
          Text query *
        </label>
        <VariableReferenceInput
          value={value.text_query}
          onChange={(v) => patch({ text_query: v })}
          placeholder='Schedule A/B (Real and Personal Property) — every real property and every vehicle the debtor owns; skip household goods'
          ariaLabel="Multi-select text_query"
        />
        <p className="mt-1 text-[10px] text-subtle">
          Drives both passes: vector search of the case docs AND a "where to
          look" locator for the petition-PDF vision fallback. Write as
          section + topic prose so the LLM knows which schedule to read
          (e.g. <span className="font-mono">Schedule A/B</span>,
          <span className="font-mono"> Schedule D</span>) and which categories
          to include or exclude.
        </p>
      </div>

      <MultiSelectSharedFields value={value} onChange={onChange} />
    </div>
  );
};

export default MultiSelectEditor;
