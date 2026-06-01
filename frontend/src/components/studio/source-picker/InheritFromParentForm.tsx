import { type ReactElement } from 'react';
import type { InheritFromParentSourceParams, SourceParams } from '@/types/studio';

// Phase 1B "Inherit from Parent" source-params form.
//
// The child-side form is intentionally minimal — this variable is just a
// SLOT marker. Each parent template that attaches this child fills the
// slot via per-companion slot_configurations on its own Bundling tab. The
// only authored field on the child side is an optional fallback_value
// shown when the child is dry-run alone (no parent attached).

interface InheritFromParentFormProps {
  variableName: string;
  sourceParams: SourceParams | null;
  onChange: (params: SourceParams) => void;
}

export const InheritFromParentForm = ({
  variableName,
  sourceParams,
  onChange,
}: InheritFromParentFormProps): ReactElement => {
  const params = (sourceParams ?? {}) as InheritFromParentSourceParams;
  const fallbackValue = params.fallback_value ?? '';

  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-border bg-surface p-5">
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-indigo-100 text-indigo-700"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              viewBox="0 0 24 24"
            >
              <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
              <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-text-secondary">
              This variable is a slot
            </h3>
            <p className="mt-0.5 text-xs text-muted">
              Slot name:{' '}
              <code className="rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[11px] text-text-secondary">
                {variableName}
              </code>
            </p>
            <p className="mt-2 text-sm leading-relaxed text-text-secondary">
              The value will be filled by whichever{' '}
              <strong className="font-semibold">parent template</strong> attaches
              this child at draft time. The filling configuration lives on the
              parent&rsquo;s{' '}
              <strong className="font-semibold">Bundle Companion</strong>, not
              here — so the same child can be attached to many parents and have
              its slots filled differently for each attachment.
            </p>
            <p className="mt-3 text-xs leading-relaxed text-muted">
              On each parent&rsquo;s Bundling tab, the author picks how to fill
              this slot — typically a{' '}
              <em className="not-italic font-medium">parent variable</em>{' '}
              (case_number, debtor_name, etc.) or an{' '}
              <em className="not-italic font-medium">extraction from the parent&rsquo;s draft content</em>{' '}
              (the filed motion title, etc.) — but in principle any source the
              parent can resolve is fair game.
            </p>
          </div>
        </div>
      </div>

      <div className="border-t border-dashed border-border pt-4">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-text-secondary">
          Fallback value (optional)
        </label>
        <p className="mb-1 text-[11px] leading-snug text-subtle">
          Shown only when this child is dry-run alone (no parent attached).
          Useful for studio iteration before a real parent is wired up.
        </p>
        <input
          type="text"
          value={fallbackValue}
          onChange={(e) => {
            const next = e.target.value;
            onChange({ fallback_value: next.length > 0 ? next : null } as SourceParams);
          }}
          placeholder="e.g. [no parent attached]"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        />
      </div>

      <div className="rounded-lg border border-border bg-surface-muted px-3 py-2.5">
        <p className="flex items-start gap-2 text-[11px] leading-snug text-muted">
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-app-accent-text"
          >
            <path
              fillRule="evenodd"
              d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z"
              clipRule="evenodd"
            />
          </svg>
          <span>
            Whatever the parent fills this slot with, the resolved value still
            passes through this template&rsquo;s standard heal pass against the{' '}
            <code className="rounded bg-surface px-1 py-0.5 font-mono text-[10px]">
              [[placeholder]]
            </code>{' '}
            format — casing, punctuation, suffixes, tense. Filling strategy is
            parent-defined; output shape is child-defined.
          </span>
        </p>
      </div>
    </div>
  );
};

export default InheritFromParentForm;
