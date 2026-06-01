import { cn } from '@/utils';
import { SOURCE_KINDS, PRESENTATION_SHAPES, type StudioVariable, type WizardSourceParams } from '../types';
import { SourceIcon } from '../SourceIcon';
import { MOCK_ATTORNEYS, MOCK_FIRM_CONSTANTS } from '../mockData';

interface PreviewStepProps {
  variable: StudioVariable;
  params: WizardSourceParams;
}

const SAMPLE_OPTIONS: Record<string, string[]> = {
  default: ['Acme Bank — $1,200', 'Genesis Finance — $8,500', 'OneMain Financial — $3,400'],
};

const ResolvedValuePreview = ({
  variable,
  params,
}: {
  variable: StudioVariable;
  params: WizardSourceParams;
}) => {
  if (params.source === 'current_date') {
    return <span className="font-mono">{new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}</span>;
  }
  if (params.source === 'constants') {
    const c = MOCK_FIRM_CONSTANTS.find(
      (k) => k.short_code === params.constants_short_code,
    );
    if (!c) {
      return <span className="font-mono italic">— constant not set —</span>;
    }
    return <span>{c.value}</span>;
  }
  if (params.source === 'attorney') {
    if (params.presentation_shape === 'raw') {
      const att = MOCK_ATTORNEYS.find((a) => a.id === params.attorney_id);
      return (
        <span className="font-mono">
          {att ? att.display_name : '— attorney not set —'}
        </span>
      );
    }
    return <span className="font-mono italic">→ paralegal picks at draft time</span>;
  }
  if (params.source === 'value_from_parent_bundle') {
    return <span className="font-mono italic">↑ inherited from parent ({params.parent_bundle_fallback ?? 'no fallback'})</span>;
  }
  if (params.source === 'derived_from_variable') {
    return <span className="font-mono italic">→ derived from {params.dependent_variable ?? '?'} </span>;
  }
  return <span className="font-mono">{variable.template_property_marker ?? '— example value —'}</span>;
};

const DraftTimePicker = ({
  variable,
  params,
}: {
  variable: StudioVariable;
  params: WizardSourceParams;
}) => {
  if (params.source === 'author_input') {
    if (params.author_input_kind === 'date') {
      return (
        <input
          type="date"
          disabled
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-secondary"
        />
      );
    }
    if (params.author_input_kind === 'with_docs') {
      return (
        <div className="flex flex-col gap-2 rounded-md border border-dashed border-border bg-surface-muted/40 p-3 text-xs italic text-subtle">
          <p>Drop files here or click to browse</p>
          <input
            type="text"
            disabled
            placeholder="And type the value…"
            className="rounded-md border border-border bg-surface px-2 py-1.5 text-sm"
          />
        </div>
      );
    }
    return (
      <input
        type="text"
        disabled
        placeholder={`Type ${variable.template_variable.replace(/_/g, ' ')}…`}
        className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-secondary"
      />
    );
  }

  if (params.presentation_shape === 'raw') return null;

  // Attorney source picks from the firm roster; everything else uses the
  // generic sample creditor options.
  const options =
    params.source === 'attorney'
      ? MOCK_ATTORNEYS.map((a) => `${a.display_name} · ${a.bar_number}`)
      : SAMPLE_OPTIONS.default;
  const label = params.label ?? `Pick ${variable.template_variable.replace(/_/g, ' ')}`;

  if (params.presentation_shape === 'dropdown') {
    return (
      <div className="space-y-2">
        <p className="text-xs font-semibold text-text-secondary">{label}</p>
        <div className="space-y-1">
          {options.map((opt, i) => (
            <label
              key={opt}
              className={cn(
                'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm',
                i === 0
                  ? 'border-app-accent bg-app-accent-soft/50 text-app-accent-text'
                  : 'border-border bg-surface text-text-secondary',
              )}
            >
              <input
                type="radio"
                checked={i === 0}
                readOnly
                className="accent-app-accent"
              />
              {opt}
            </label>
          ))}
        </div>
      </div>
    );
  }

  if (params.presentation_shape === 'chip') {
    return (
      <div className="space-y-2">
        <p className="text-xs font-semibold text-text-secondary">{label}</p>
        <div className="flex flex-wrap gap-1.5">
          {options.slice(0, 3).map((opt, i) => (
            <button
              key={opt}
              type="button"
              className={cn(
                'cursor-pointer rounded-full border px-3 py-1 text-xs',
                i === 0
                  ? 'border-app-accent bg-app-accent text-white'
                  : 'border-border bg-surface text-text-secondary',
              )}
            >
              {opt}
            </button>
          ))}
          <button className="cursor-pointer rounded-full border border-dashed border-border bg-surface px-3 py-1 text-xs text-subtle">
            Edit…
          </button>
        </div>
      </div>
    );
  }

  // multi_select
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-text-secondary">
        {label}{' '}
        <span className="text-subtle">
          (pick {params.min_picks}–{params.max_picks})
        </span>
      </p>
      <div className="space-y-1">
        {options.map((opt, i) => (
          <label
            key={opt}
            className={cn(
              'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm',
              i !== 1
                ? 'border-app-accent bg-app-accent-soft/50 text-app-accent-text'
                : 'border-border bg-surface text-text-secondary',
            )}
          >
            <input
              type="checkbox"
              checked={i !== 1}
              readOnly
              className="accent-app-accent"
            />
            {opt}
          </label>
        ))}
      </div>
    </div>
  );
};

export const PreviewStep = ({ variable, params }: PreviewStepProps) => {
  const sourceMeta = SOURCE_KINDS.find((s) => s.key === params.source);
  const shapeMeta = PRESENTATION_SHAPES.find((s) => s.key === params.presentation_shape);

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-text-secondary">Preview</h3>
        <p className="mt-1 text-sm text-subtle">
          Quick look at how this field will work. Click Save to confirm.
        </p>
      </div>

      <div className="space-y-4 rounded-xl border border-border bg-surface-muted/40 p-4">
        <div className="flex items-start gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-app-accent text-white">
            <SourceIcon source={params.source} className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-subtle">
              Coming from
            </p>
            <p className="text-sm font-semibold text-text-secondary">
              {sourceMeta?.label}
              {sourceMeta?.acceptsShape && params.presentation_shape !== 'raw' && (
                <span className="ml-2 rounded-full bg-app-accent-soft px-2 py-0.5 text-[10px] uppercase tracking-wider text-app-accent-text">
                  {shapeMeta?.label}
                </span>
              )}
            </p>
          </div>
        </div>

        {params.extraction_prompt && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-subtle">
              Instructions to the agent
            </p>
            <p className="mt-1 rounded-md border border-border bg-surface px-3 py-2 text-sm italic text-text-secondary">
              "{params.extraction_prompt}"
            </p>
          </div>
        )}
      </div>

      <div className="space-y-3 rounded-xl border border-border bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-app-accent-text">
          What you'll see when drafting
        </p>
        {params.source === 'author_input' ||
        (sourceMeta?.acceptsShape && params.presentation_shape !== 'raw') ? (
          <DraftTimePicker variable={variable} params={params} />
        ) : (
          <p className="text-xs italic text-subtle">
            Nothing — the agent fills this in for you automatically.
          </p>
        )}
      </div>

      <div className="space-y-2 rounded-xl border border-border bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-app-accent-text">
          Sample value to expect
        </p>
        <p className="rounded-md border border-border bg-surface-muted/40 px-3 py-2 text-sm text-text-secondary">
          <ResolvedValuePreview variable={variable} params={params} />
        </p>
        <p className="text-[11px] italic text-subtle">
          An example of what could land in the document at draft time —
          actual value depends on the case.
        </p>
      </div>
    </div>
  );
};
