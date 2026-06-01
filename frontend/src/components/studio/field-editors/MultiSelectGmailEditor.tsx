import type { ReactElement } from 'react';
import { VariableReferenceInput } from './VariableReferenceInput';
import { MultiSelectSharedFields } from './MultiSelectSharedFields';
import type { MultiSelectFromGmailSourceParams } from '@/types/studio';

interface MultiSelectGmailEditorProps {
  value: MultiSelectFromGmailSourceParams;
  onChange: (next: MultiSelectFromGmailSourceParams) => void;
}

export const MultiSelectGmailEditor = ({
  value,
  onChange,
}: MultiSelectGmailEditorProps): ReactElement => {
  const patch = (next: Partial<MultiSelectFromGmailSourceParams>): void => {
    onChange({ ...value, ...next });
  };

  const subjectValue = value.subject_query ?? '';
  const bodyValue = value.body_query ?? '';
  const hasQuery =
    (subjectValue.trim().length ?? 0) > 0 || (bodyValue.trim().length ?? 0) > 0;

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-dashed border-border bg-surface-muted/40 px-3 py-2 text-xs text-muted">
        Pre-fetched at draft time. The BE searches Gmail with{' '}
        <span className="font-mono">subject_query</span> /{' '}
        <span className="font-mono">body_query</span>, extracts up to 20
        distinct options matching <span className="font-mono">example_formats</span>,
        and the user picks one or more in a multi-select card UI. Use this when
        options live in case email correspondence (e.g. creditors from Proof
        of Claim filings).
      </div>

      {!hasQuery && (
        <div
          role="alert"
          className="rounded-lg border border-app-warning-soft bg-app-warning-soft px-3 py-2 text-xs text-app-warning-text"
        >
          <span className="font-semibold">At least one query is required.</span>{' '}
          Provide a Subject query, a Body query, or both so the agent knows where to look.
        </div>
      )}

      <div>
        <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-muted">
          Subject query
        </label>
        <VariableReferenceInput
          value={subjectValue}
          onChange={(v) => patch({ subject_query: v || null })}
          placeholder='e.g. Proof of Claim — type {{ to reference a variable'
          ariaLabel="Multi-select subject_query"
        />
      </div>

      <div>
        <label className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-muted">
          Body query
        </label>
        <VariableReferenceInput
          value={bodyValue}
          onChange={(v) => patch({ body_query: v || null })}
          placeholder="Optional — search the email body"
          ariaLabel="Multi-select body_query"
        />
      </div>

      <div>
        <label className="flex items-center gap-2 text-xs text-text-secondary">
          <input
            type="checkbox"
            checked={value.scope_to_current_case ?? true}
            onChange={(e) => patch({ scope_to_current_case: e.target.checked })}
          />
          <span>Scope to current case (default)</span>
        </label>
        <p className="mt-1 text-[10px] text-subtle">
          When checked, the BE adds the current case's number variants as an AND
          clause. Uncheck for cross-case templates that need to reach into
          another case's email thread (typically combined with
          {' '}<span className="font-mono">{`{{prior_case_number}}`}</span>{' '}
          in the query).
        </p>
      </div>

      <MultiSelectSharedFields value={value} onChange={onChange} />
    </div>
  );
};

export default MultiSelectGmailEditor;
