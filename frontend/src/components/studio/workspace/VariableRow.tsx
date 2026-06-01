import { useEffect, useRef, useState, type ReactElement } from 'react';
import { Tooltip } from '@/components/common';
import { useStudioStore } from '@/stores/useStudioStore';
import { humanizeIdentifier } from '@/utils';
import { LuLink } from 'react-icons/lu';
import { SOURCE_ICON_COMPONENTS } from '@/utils/studio/sourceIconMap';
import { familyOf, findFamily, patternOf } from '@/utils/studio/sourceConfig';
import type {
  FieldSource,
  ResolvedTemplateValue,
  TemplateVariable,
} from '@/types/studio';

type VariableRowVariant = 'standalone' | 'parent' | 'child';

interface VariableRowProps {
  variable: TemplateVariable;
  resolvedValue?: ResolvedTemplateValue;
  isHighlighted?: boolean;
  onClick: () => void;
  variant?: VariableRowVariant;
  
  childCount?: number;
  
  parentName?: string;
}

type Confidence = ResolvedTemplateValue['confidence'];

const svgBase = {
  fill: 'none',
  stroke: 'currentColor',
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  strokeWidth: 2,
  viewBox: '0 0 24 24',
};

const IconSliders = ({ className = 'h-4 w-4' }: { className?: string }): ReactElement => (
  <svg {...svgBase} className={className}>
    <line x1="4" y1="21" x2="4" y2="14" />
    <line x1="4" y1="10" x2="4" y2="3" />
    <line x1="12" y1="21" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12" y2="3" />
    <line x1="20" y1="21" x2="20" y2="16" />
    <line x1="20" y1="12" x2="20" y2="3" />
    <line x1="1" y1="14" x2="7" y2="14" />
    <line x1="9" y1="8" x2="15" y2="8" />
    <line x1="17" y1="16" x2="23" y2="16" />
  </svg>
);
const IconChevron = ({ className = 'h-3.5 w-3.5' }: { className?: string }): ReactElement => (
  <svg {...svgBase} className={className}>
    <polyline points="6 9 12 15 18 9" />
  </svg>
);
const IconSparkle = ({ className = 'h-3.5 w-3.5' }: { className?: string }): ReactElement => (
  <svg {...svgBase} className={className}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" />
  </svg>
);
const IconAlert = ({ className = 'h-3.5 w-3.5' }: { className?: string }): ReactElement => (
  <svg {...svgBase} className={className}>
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);
const IconGrid = ({ className = 'h-3.5 w-3.5' }: { className?: string }): ReactElement => (
  <svg {...svgBase} className={className}>
    <rect x="3" y="3" width="7" height="7" />
    <rect x="14" y="3" width="7" height="7" />
    <rect x="14" y="14" width="7" height="7" />
    <rect x="3" y="14" width="7" height="7" />
  </svg>
);
const IconLock = ({ className = 'h-3.5 w-3.5' }: { className?: string }): ReactElement => (
  <svg {...svgBase} className={className}>
    <rect x="4" y="11" width="16" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 1 1 8 0v4" />
  </svg>
);

const SOURCE_ICONS = SOURCE_ICON_COMPONENTS;

const DEFAULT_SOURCE_ICON = IconGrid;

const CONFIDENCE_STYLES: Record<
  Confidence,
  {
    pill: string;
    dot: string;
    label: string;
    reasoningPanel: string;
    reasoningText: string;
    reasoningToggle: string;
  }
> = {
  high: {
    pill: 'bg-app-success-soft text-app-success-text ring-app-success-soft',
    dot: 'bg-emerald-500',
    label: 'High confidence',
    reasoningPanel: 'border-app-success-soft bg-app-success-soft/50',
    reasoningText: 'text-app-success-text',
    reasoningToggle: 'text-app-success-text hover:bg-app-success-soft',
  },
  medium: {
    pill: 'bg-app-warning-soft text-app-warning-text ring-app-warning-soft',
    dot: 'bg-amber-500',
    label: 'Medium confidence',
    reasoningPanel: 'border-app-warning-soft bg-app-warning-soft/50',
    reasoningText: 'text-app-warning-text',
    reasoningToggle: 'text-app-warning-text hover:bg-app-warning-soft',
  },
  low: {
    pill: 'bg-app-danger-soft text-app-danger-text ring-app-danger-soft',
    dot: 'bg-rose-500',
    label: 'Low confidence',
    reasoningPanel: 'border-app-danger-soft bg-app-danger-soft/50',
    reasoningText: 'text-app-danger-text',
    reasoningToggle: 'text-app-danger-text hover:bg-app-danger-soft',
  },
};

const summarizeParams = (
  variable: TemplateVariable,
  lookupConstantLabel: (shortCode: string) => string | null
): string | null => {
  const { source, source_params } = variable;
  if (!source) return null;
  if (source === 'case_vector') return 'auto-derived from variable name';
  if (!source_params) return null;
  switch (source) {
    case 'gmail':
    case 'court_drive': {
      const subject = 'subject_query' in source_params ? source_params.subject_query : null;
      const body = 'body_query' in source_params ? source_params.body_query : null;
      const parts: string[] = [];
      if (subject && subject.trim()) parts.push(`subject: ${subject.trim()}`);
      if (body && body.trim()) parts.push(`body: ${body.trim()}`);
      return parts.length > 0 ? parts.join(' · ') : null;
    }
    case 'law_practice_vector':
      return 'text_query' in source_params ? (source_params.text_query ?? null) : null;
    case 'constants': {
      if (!('short_code' in source_params) || !source_params.short_code) return null;
      return lookupConstantLabel(source_params.short_code) ?? source_params.short_code;
    }
    case 'dependent_on_variable': {
      if (!('rule_effect_value' in source_params)) return null;
      const p = source_params as { dependent_variable?: string; rule_effect?: string; rule_effect_value?: string | null };
      const parent = p.dependent_variable;
      const effect = p.rule_effect;
      const amount = p.rule_effect_value;
      if (!parent) return null;
      if (effect === 'format_only' || !amount) return `derives from ${parent}`;
      return `${parent} ${effect?.replace(/_/g, ' ')} ${amount}`;
    }
    case 'system_generated': {
      if (!('type' in source_params)) return null;
      return source_params.type ? source_params.type.replace(/_/g, ' ') : null;
    }
    case 'multi_select_from_case_vector': {
      if (!('text_query' in source_params)) return null;
      const minP = (source_params as { min_picks?: number }).min_picks ?? 1;
      const maxP = (source_params as { max_picks?: number | null }).max_picks ?? null;
      let range: string;
      if (maxP === null || maxP === undefined) {
        range = minP > 0 ? `${minP}+` : 'any';
      } else if (minP === maxP) {
        range = `exactly ${minP}`;
      } else {
        range = `${minP}–${maxP}`;
      }
      return `pick ${range} from list`;
    }
    case 'auto_derived_from_variable': {
      const dep = (source_params as { dependent_variable?: string }).dependent_variable;
      if (!dep) return null;
      return `derived from ${dep}`;
    }
  }
  return null;
};

export const VariableRow = ({
  variable,
  resolvedValue,
  isHighlighted = false,
  onClick,
  variant = 'standalone',
  childCount,
  parentName,
}: VariableRowProps): ReactElement => {
  const referenceData = useStudioStore((state) => state.referenceData);
  const connectors = useStudioStore((state) => state.connectors);

  const [showReasoning, setShowReasoning] = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isHighlighted && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [isHighlighted]);

  const lookupConstantLabel = (shortCode: string): string | null => {
    const match = referenceData.find((r) => r.short_code === shortCode);
    return match ? match.display_name : null;
  };

  const lookupSourceLabel = (source: FieldSource): string => {
    
    const family = findFamily(familyOf(source));
    const patternKey = patternOf(source);
    const pattern = family && patternKey
      ? family.patterns.find((p) => p.key === patternKey)
      : null;
    if (pattern) return pattern.label;
    const connector = connectors.find((c) => c.source === source);
    return connector?.display_name ?? humanizeIdentifier(source);
  };

  const isParent = variant === 'parent';
  const isVirtual = variable.kind === 'virtual' || variable.template_variable_string === null;
  const isReadOnly = variant === 'child' || variable.read_only === true;
  const isMapped =
    variable.source !== null &&
    (variable.source === 'case_vector' || variable.source_params !== null);
  const humanName = humanizeIdentifier(variable.template_variable);
  const summary = summarizeParams(variable, lookupConstantLabel);
  const fallbackSubtitle = isParent
    ? `Group parent · feeds ${childCount ?? 0} field${childCount === 1 ? '' : 's'}`
    : `Placeholder [[${variable.template_variable}]]`;
  const subtitle =
    variable.description ||
    variable.template_identifying_text_match ||
    fallbackSubtitle;

  const SourceIcon = variable.source
    ? (SOURCE_ICONS[variable.source] ?? DEFAULT_SOURCE_ICON)
    : null;
  const confidence = resolvedValue?.confidence;
  const confidenceStyle = confidence ? CONFIDENCE_STYLES[confidence] : null;

  const cardSurfaceClass = isReadOnly
    ? 'bg-surface-muted/60 border-dashed opacity-75'
    : 'bg-surface';
  const ariaProps = isReadOnly
    ? {
        'aria-disabled': true,
        'aria-describedby': parentName
          ? `vrow-readonly-${variable.template_variable}`
          : undefined,
      }
    : {};

  return (
    <div
      ref={ref}
      className={`group @container/varrow overflow-hidden rounded-xl border shadow-sm transition-all duration-300 ${cardSurfaceClass} ${
        isHighlighted
          ? 'border-indigo-400 ring-2 ring-indigo-200'
          : isReadOnly
            ? 'border-border'
            : 'border-border hover:border-app-accent-soft hover:shadow-md'
      }`}
      role={variant === 'child' ? 'listitem' : undefined}
    >
      <button
        type="button"
        onClick={isReadOnly ? undefined : onClick}
        disabled={isReadOnly}
        className={`flex w-full flex-col items-stretch gap-2 px-4 py-3.5 text-left @sm/varrow:flex-row @sm/varrow:items-start @sm/varrow:gap-3 ${
          isReadOnly ? 'cursor-not-allowed' : ''
        }`}
        {...ariaProps}
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-text-secondary">{humanName}</h3>
            {!isVirtual && variable.template_variable_string && (
              <code className="inline-flex items-center rounded-md bg-surface-muted px-1.5 py-0.5 font-mono text-[10px] text-muted ring-1 ring-inset ring-border">
                {variable.template_variable_string}
              </code>
            )}
            {isParent && (
              <span className="inline-flex items-center gap-1 rounded-md bg-indigo-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-indigo-700 ring-1 ring-inset ring-indigo-200">
                Group parent
              </span>
            )}
          </div>
          <p className="mt-1 break-words text-xs leading-relaxed text-muted">
            {subtitle}
          </p>
          {isReadOnly && parentName && (
            <p
              id={`vrow-readonly-${variable.template_variable}`}
              className="mt-1 text-[11px] italic text-muted"
            >
              Read-only · auto-derived from {humanizeIdentifier(parentName)}
            </p>
          )}
        </div>

        <div className="flex min-w-0 max-w-full flex-col items-start gap-1 @sm/varrow:items-end">
          {isReadOnly ? (
            <Tooltip
              side="left"
              label={
                parentName
                  ? `Locked — this value is auto-derived from "${humanizeIdentifier(parentName)}". Edit that field instead and this one will update.`
                  : 'Locked — this value is auto-derived and updates automatically. It cannot be edited directly.'
              }
            >
              <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-xs font-semibold text-muted ring-1 ring-inset ring-border">
                <LuLink className="h-3 w-3" aria-hidden="true" />
                Auto-derived
              </span>
            </Tooltip>
          ) : isMapped && variable.source && SourceIcon ? (
            <>
              <span className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-app-accent-soft px-2.5 py-1 text-xs font-semibold text-app-accent-text ring-1 ring-inset ring-indigo-200">
                <SourceIcon />
                <span className="truncate">{lookupSourceLabel(variable.source)}</span>
              </span>
              {summary && (
                <span
                  className="max-w-[220px] truncate text-[11px] text-muted"
                  title={summary}
                >
                  {summary}
                </span>
              )}
            </>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-amber-300 bg-app-warning-soft px-2.5 py-1 text-xs font-semibold text-amber-800">
              <IconAlert className="h-3 w-3" />
              Not mapped
            </span>
          )}
        </div>

        <div
          className="hidden h-7 w-7 shrink-0 items-center justify-center rounded-md text-subtle opacity-0 transition-all group-hover:opacity-100 group-hover:text-app-accent-text @sm/varrow:flex"
          aria-hidden="true"
          title={isReadOnly ? 'Read-only — auto-derived' : undefined}
        >
          {isReadOnly ? <IconLock className="h-4 w-4" /> : <IconSliders className="h-4 w-4" />}
        </div>
      </button>

      {resolvedValue && confidenceStyle && (
        <div className="border-t border-border bg-gradient-to-b from-surface-muted/80 to-surface px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                Resolved value
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${confidenceStyle.pill}`}
                title={`Confidence: ${confidence}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${confidenceStyle.dot}`} />
                {confidenceStyle.label}
              </span>
            </div>
          </div>

          <p
            className={`mt-1.5 break-words text-[15px] font-medium leading-tight ${
              resolvedValue.value ? 'text-text-secondary' : 'italic text-subtle'
            }`}
          >
            {resolvedValue.value || '(empty)'}
          </p>

          {resolvedValue.reasoning && (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setShowReasoning((s) => !s)}
                aria-expanded={showReasoning}
                className={`inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[11px] font-medium ${confidenceStyle.reasoningToggle}`}
              >
                <IconSparkle className="h-3 w-3" />
                <span>AI reasoning</span>
                <IconChevron
                  className={`h-3 w-3 transition-transform ${showReasoning ? 'rotate-180' : ''}`}
                />
              </button>
              {showReasoning && (
                <div className={`mt-2 rounded-lg border px-3 py-2.5 ${confidenceStyle.reasoningPanel}`}>
                  <p className={`text-xs leading-relaxed ${confidenceStyle.reasoningText}`}>
                    {resolvedValue.reasoning}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default VariableRow;
