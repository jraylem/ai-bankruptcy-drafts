import { useMemo, useState } from 'react';
import {
  FiAlertTriangle,
  FiChevronDown,
  FiChevronRight,
  FiEdit3,
  FiFilter,
  FiLayers,
  FiSearch,
  FiX,
} from 'react-icons/fi';
import { cn } from '@/utils';
import type {
  BundleChildRunV2,
  DryRunResponseV2,
  GrammarRepairV2,
  ResolvedTemplateValueV2,
} from '@/types/studio-v2';

interface ResolutionLogPaneProps {
  result: DryRunResponseV2;
  /**
   * Highlight the matching placeholder/value in the Draft tab when the
   * paralegal clicks "Show in draft" on a row. v1.1 — wired by the
   * parent (TemplatePreviewV2) so the log can drive the editor pane.
   */
  onShowInDraft?: (variableName: string, childIndex: number | null) => void;
}

type ConfidenceFilter = 'all' | 'high' | 'medium' | 'low' | 'unresolved';

/**
 * Forensic log surface for a completed dry-run. Replaces the old
 * `DryRunResultModal` — same data, but rendered as a peer tab in
 * the editor area so paralegals can scan it as a first-class view
 * instead of a hidden popup.
 *
 * Layout:
 *   - Header row: per-template summary (resolved / unresolved counts)
 *   - Toolbar: filter pills (All / High / Med / Low / Unresolved /
 *     Warnings) + search input
 *   - Scrollable list: parent's resolved values grouped under a
 *     "Parent template" header; each companion's values grouped
 *     under a collapsible "Companion: <name>" header
 *   - Per-row: variable name (mono) + value + confidence badge,
 *     with note + raw_context details collapsed by default
 */
export const ResolutionLogPane = ({ result, onShowInDraft }: ResolutionLogPaneProps) => {
  const [filter, setFilter] = useState<ConfidenceFilter>('all');
  const [query, setQuery] = useState('');
  const [showWarnings, setShowWarnings] = useState(false);
  const [showGrammarRepairs, setShowGrammarRepairs] = useState(true);
  const [collapsedChildren, setCollapsedChildren] = useState<Set<number>>(
    new Set(),
  );

  const matchesFilter = (
    rv: ResolvedTemplateValueV2,
    isUnresolved: boolean,
  ): boolean => {
    if (filter === 'all') return true;
    if (filter === 'unresolved') return isUnresolved;
    return rv.confidence === filter;
  };
  const matchesQuery = (rv: ResolvedTemplateValueV2): boolean => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      rv.template_variable.toLowerCase().includes(q) ||
      rv.value.toLowerCase().includes(q) ||
      (rv.note ?? '').toLowerCase().includes(q)
    );
  };

  const unresolvedSet = useMemo(() => {
    const s = new Set<string>();
    for (const ph of result.unresolved) {
      // unresolved is `[[var]]` form — strip brackets for matching
      const m = ph.match(/^\[\[(.+?)\]\]$/);
      if (m) s.add(m[1]);
      else s.add(ph);
    }
    return s;
  }, [result.unresolved]);

  const parentRows = useMemo(
    () =>
      result.resolved_values
        .filter((rv) => matchesFilter(rv, unresolvedSet.has(rv.template_variable)))
        .filter(matchesQuery),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [result.resolved_values, filter, query, unresolvedSet],
  );

  const parentResolvedCount = result.resolved_values.filter((rv) => rv.value).length;
  const totalChildren = result.children.length;
  const totalWarnings =
    result.warnings.length +
    result.children.reduce((acc, c) => acc + c.finalized.warnings.length, 0);
  const totalGrammarRepairs =
    (result.grammar_repairs?.length ?? 0) +
    result.children.reduce(
      (acc, c) => acc + (c.finalized.grammar_repairs?.length ?? 0),
      0,
    );

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface-muted/30">
      <div className="shrink-0 border-b border-border bg-surface px-5 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-app-accent-text">
          Resolution log
        </p>
        <p className="mt-0.5 text-xs text-muted">
          {parentResolvedCount}/{result.resolved_values.length} resolved
          {result.unresolved.length > 0 && (
            <span className="text-app-danger-text">
              {' · '}
              {result.unresolved.length} unresolved
            </span>
          )}
          {totalChildren > 0 && (
            <span>
              {' · '}
              {totalChildren} companion{totalChildren === 1 ? '' : 's'}
            </span>
          )}
          {totalWarnings > 0 && (
            <span className="text-amber-700">
              {' · '}
              {totalWarnings} warning{totalWarnings === 1 ? '' : 's'}
            </span>
          )}
          {totalGrammarRepairs > 0 && (
            <span className="text-violet-700">
              {' · '}
              {totalGrammarRepairs} grammar fix
              {totalGrammarRepairs === 1 ? '' : 'es'}
            </span>
          )}
        </p>
      </div>

      <div className="shrink-0 border-b border-border bg-surface px-5 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip
            label="All"
            active={filter === 'all'}
            onClick={() => setFilter('all')}
          />
          <FilterChip
            label="High"
            tone="emerald"
            active={filter === 'high'}
            onClick={() => setFilter('high')}
          />
          <FilterChip
            label="Medium"
            tone="sky"
            active={filter === 'medium'}
            onClick={() => setFilter('medium')}
          />
          <FilterChip
            label="Low"
            tone="amber"
            active={filter === 'low'}
            onClick={() => setFilter('low')}
          />
          <FilterChip
            label="Unresolved"
            tone="danger"
            count={result.unresolved.length}
            active={filter === 'unresolved'}
            onClick={() => setFilter('unresolved')}
          />
          {totalWarnings > 0 && (
            <button
              type="button"
              onClick={() => setShowWarnings((v) => !v)}
              className={cn(
                'inline-flex cursor-pointer items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold motion-safe:transition-colors',
                showWarnings
                  ? 'border-amber-400 bg-amber-100 text-amber-900'
                  : 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100',
              )}
            >
              <FiAlertTriangle className="h-3 w-3" />
              Warnings ({totalWarnings})
            </button>
          )}
          {totalGrammarRepairs > 0 && (
            <button
              type="button"
              onClick={() => setShowGrammarRepairs((v) => !v)}
              className={cn(
                'inline-flex cursor-pointer items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold motion-safe:transition-colors',
                showGrammarRepairs
                  ? 'border-violet-400 bg-violet-100 text-violet-900'
                  : 'border-violet-200 bg-violet-50 text-violet-800 hover:bg-violet-100',
              )}
              title="Singular/plural agreement swaps applied by the autofixer"
            >
              <FiEdit3 className="h-3 w-3" />
              Grammar fixes ({totalGrammarRepairs})
            </button>
          )}
          <div className="relative ml-auto w-56">
            <FiSearch className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search fields, values, notes…"
              className="block w-full rounded-md border border-border bg-surface py-1.5 pl-8 pr-7 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                aria-label="Clear search"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-subtle hover:bg-surface-muted hover:text-text-secondary"
              >
                <FiX className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {showGrammarRepairs && totalGrammarRepairs > 0 && (
          <GrammarRepairsBlock
            parentRepairs={result.grammar_repairs ?? []}
            children={result.children}
          />
        )}

        {showWarnings && (
          <WarningsBlock
            parentWarnings={result.warnings}
            children={result.children}
          />
        )}

        <GroupHeader
          title="Parent template"
          subtitle={`${result.resolved_values.length} fields`}
        />
        {parentRows.length === 0 ? (
          <EmptyFilterState onClear={() => { setFilter('all'); setQuery(''); }} />
        ) : (
          parentRows.map((rv) => (
            <ResolutionRow
              key={rv.template_variable}
              rv={rv}
              isUnresolved={unresolvedSet.has(rv.template_variable)}
              onShowInDraft={
                onShowInDraft
                  ? () => onShowInDraft(rv.template_variable, null)
                  : undefined
              }
            />
          ))
        )}

        {result.children.map((child, idx) => (
          <CompanionGroup
            key={`${child.template_id}-${idx}`}
            child={child}
            childIndex={idx}
            collapsed={collapsedChildren.has(idx)}
            onToggle={() => {
              setCollapsedChildren((prev) => {
                const next = new Set(prev);
                if (next.has(idx)) next.delete(idx);
                else next.add(idx);
                return next;
              });
            }}
            filter={filter}
            query={query}
            onShowInDraft={onShowInDraft}
          />
        ))}
      </div>
    </div>
  );
};

// ─── filter chip ─────────────────────────────────────────────────────

const FilterChip = ({
  label,
  active,
  count,
  tone,
  onClick,
}: {
  label: string;
  active: boolean;
  count?: number;
  tone?: 'emerald' | 'sky' | 'amber' | 'danger';
  onClick: () => void;
}) => {
  const toneClasses: Record<string, string> = {
    emerald: active
      ? 'border-emerald-400 bg-emerald-100 text-emerald-800'
      : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100',
    sky: active
      ? 'border-sky-400 bg-sky-100 text-sky-800'
      : 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100',
    amber: active
      ? 'border-amber-400 bg-amber-100 text-amber-900'
      : 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100',
    danger: active
      ? 'border-app-danger-text/50 bg-app-danger-text/15 text-app-danger-text'
      : 'border-app-danger-text/30 bg-app-danger-text/5 text-app-danger-text hover:bg-app-danger-text/10',
    default: active
      ? 'border-app-accent bg-app-accent text-white'
      : 'border-border bg-surface text-text-secondary hover:bg-surface-muted',
  };
  const classes = toneClasses[tone ?? 'default'];
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex cursor-pointer items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold motion-safe:transition-colors',
        classes,
      )}
    >
      <span>{label}</span>
      {count !== undefined && count > 0 && (
        <span className="text-[10px] opacity-80">({count})</span>
      )}
    </button>
  );
};

// ─── group header ────────────────────────────────────────────────────

const GroupHeader = ({
  title,
  subtitle,
  collapsed,
  onToggle,
  iconLeft,
}: {
  title: string;
  subtitle?: string;
  collapsed?: boolean;
  onToggle?: () => void;
  iconLeft?: React.ReactNode;
}) => {
  const inner = (
    <div className="flex items-center gap-2 px-5 py-2">
      {onToggle && (
        collapsed
          ? <FiChevronRight className="h-3.5 w-3.5 text-subtle" />
          : <FiChevronDown className="h-3.5 w-3.5 text-subtle" />
      )}
      {iconLeft}
      <p className="text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
        {title}
      </p>
      {subtitle && (
        <p className="text-[10px] text-subtle">{subtitle}</p>
      )}
    </div>
  );
  if (onToggle) {
    return (
      <button
        type="button"
        onClick={onToggle}
        className="sticky top-0 z-10 w-full cursor-pointer border-b border-border bg-surface text-left hover:bg-surface-muted/60"
      >
        {inner}
      </button>
    );
  }
  return (
    <div className="sticky top-0 z-10 border-b border-border bg-surface">
      {inner}
    </div>
  );
};

// ─── companion group ─────────────────────────────────────────────────

const CompanionGroup = ({
  child,
  childIndex,
  collapsed,
  onToggle,
  filter,
  query,
  onShowInDraft,
}: {
  child: BundleChildRunV2;
  childIndex: number;
  collapsed: boolean;
  onToggle: () => void;
  filter: ConfidenceFilter;
  query: string;
  onShowInDraft?: (variableName: string, childIndex: number | null) => void;
}) => {
  const matchesFilter = (rv: ResolvedTemplateValueV2): boolean => {
    if (filter === 'all') return true;
    if (filter === 'unresolved') return !rv.value;
    return rv.confidence === filter;
  };
  const matchesQuery = (rv: ResolvedTemplateValueV2): boolean => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      rv.template_variable.toLowerCase().includes(q) ||
      rv.value.toLowerCase().includes(q) ||
      (rv.note ?? '').toLowerCase().includes(q)
    );
  };
  const rows = child.finalized.resolved_values
    .filter(matchesFilter)
    .filter(matchesQuery);
  const subtitle =
    `${child.finalized.resolved_values.length} fields` +
    (child.finalized.warnings.length > 0
      ? ` · ${child.finalized.warnings.length} warning${child.finalized.warnings.length === 1 ? '' : 's'}`
      : '');

  return (
    <>
      <GroupHeader
        title={`Companion: ${child.template_name}`}
        subtitle={subtitle}
        collapsed={collapsed}
        onToggle={onToggle}
        iconLeft={<FiLayers className="h-3.5 w-3.5 text-app-accent-text" />}
      />
      {!collapsed &&
        rows.map((rv) => {
          const isUnresolved = !rv.value;
          return (
            <ResolutionRow
              key={`${child.template_id}-${rv.template_variable}`}
              rv={rv}
              isUnresolved={isUnresolved}
              onShowInDraft={
                onShowInDraft
                  ? () => onShowInDraft(rv.template_variable, childIndex)
                  : undefined
              }
            />
          );
        })}
    </>
  );
};

// ─── resolution row ──────────────────────────────────────────────────

const ResolutionRow = ({
  rv,
  isUnresolved,
  onShowInDraft,
}: {
  rv: ResolvedTemplateValueV2;
  isUnresolved: boolean;
  onShowInDraft?: () => void;
}) => {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = Boolean(rv.note || rv.raw_context);
  return (
    <div
      className={cn(
        'group border-b border-border px-5 py-3 motion-safe:transition-colors',
        isUnresolved
          ? 'bg-app-danger-text/5 hover:bg-app-danger-text/10'
          : 'hover:bg-surface-muted/60',
      )}
    >
      <div className="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto] items-start gap-3">
        <code className="overflow-hidden truncate font-mono text-xs font-semibold text-text-secondary">
          {rv.template_variable}
        </code>
        <p
          className={cn(
            'truncate text-sm font-medium',
            rv.value
              ? 'text-app-accent-text'
              : 'italic text-subtle',
          )}
          title={rv.value || '(unresolved)'}
        >
          {rv.value || '(unresolved)'}
        </p>
        <ConfidenceBadge confidence={rv.confidence} isUnresolved={isUnresolved} />
      </div>
      {hasDetail && (
        <div className="mt-1.5">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex cursor-pointer items-center gap-1 text-[10px] font-medium text-subtle hover:text-text-secondary"
          >
            {expanded ? (
              <FiChevronDown className="h-3 w-3" />
            ) : (
              <FiChevronRight className="h-3 w-3" />
            )}
            {expanded ? 'Hide reasoning' : 'Show reasoning'}
            {rv.raw_context && (
              <span className="text-[10px] text-subtle">
                · {rv.raw_context.length}&nbsp;chr source
              </span>
            )}
          </button>
          {expanded && (
            <div className="mt-1.5 space-y-2 rounded-md border border-border bg-surface px-3 py-2">
              {rv.note && (
                <p className="text-xs leading-relaxed text-text-secondary">
                  {rv.note}
                </p>
              )}
              {rv.raw_context && (
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-subtle">
                    From the source
                  </p>
                  <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap border-l-2 border-app-accent/40 pl-3 text-[11px] italic text-muted">
                    {rv.raw_context}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {onShowInDraft && rv.value && (
        <div className="mt-1.5 opacity-0 motion-safe:transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={onShowInDraft}
            className="cursor-pointer text-[10px] font-semibold text-app-accent-text hover:underline"
          >
            Show in draft →
          </button>
        </div>
      )}
    </div>
  );
};

// ─── confidence badge ───────────────────────────────────────────────

const ConfidenceBadge = ({
  confidence,
  isUnresolved,
}: {
  confidence: string;
  isUnresolved: boolean;
}) => {
  if (isUnresolved) {
    return (
      <span className="inline-flex items-center rounded-full bg-app-danger-text/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-app-danger-text ring-1 ring-app-danger-text/30">
        unresolved
      </span>
    );
  }
  const styles: Record<string, string> = {
    high: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    medium: 'bg-sky-50 text-sky-700 ring-sky-200',
    low: 'bg-amber-50 text-amber-800 ring-amber-200',
    none: 'bg-surface-muted text-muted ring-border',
  };
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ring-1',
        styles[confidence] ?? styles.none,
      )}
    >
      {confidence}
    </span>
  );
};

// ─── grammar repairs block ───────────────────────────────────────────

const GrammarRepairsBlock = ({
  parentRepairs,
  children,
}: {
  parentRepairs: GrammarRepairV2[];
  children: BundleChildRunV2[];
}) => (
  <div className="border-b border-violet-300 bg-violet-50/70 px-5 py-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-violet-900">
      Grammar fixes applied
    </p>
    <p className="mt-0.5 text-[11px] text-violet-900/70">
      Singular ↔ plural agreement swaps auto-applied to the rendered docx.
      Names, dates, and layout are untouched.
    </p>
    {parentRepairs.length > 0 && (
      <div className="mt-2 space-y-1.5">
        {parentRepairs.map((r, i) => (
          <GrammarRepairRow key={`p-${i}`} repair={r} />
        ))}
      </div>
    )}
    {children.map(
      (child, idx) =>
        (child.finalized.grammar_repairs?.length ?? 0) > 0 && (
          <div key={idx} className="mt-3">
            <p className="text-[10px] font-semibold text-violet-900">
              In companion: {child.template_name}
            </p>
            <div className="mt-1 space-y-1.5">
              {child.finalized.grammar_repairs.map((r, i) => (
                <GrammarRepairRow key={`c-${idx}-${i}`} repair={r} />
              ))}
            </div>
          </div>
        ),
    )}
  </div>
);

const GrammarRepairRow = ({ repair }: { repair: GrammarRepairV2 }) => (
  <div className="rounded-md border border-violet-200 bg-surface px-3 py-2 shadow-sm">
    <div className="flex flex-wrap items-baseline gap-2 text-[11px]">
      <span className="font-mono text-violet-900">
        ¶{repair.paragraph_index + 1}
      </span>
      <span className="rounded bg-rose-100 px-1.5 py-0.5 font-mono text-rose-800 line-through">
        {repair.original_word}
      </span>
      <span className="text-violet-500">→</span>
      <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-mono text-emerald-800">
        {repair.replacement_word}
      </span>
      {repair.occurrences > 1 && (
        <span className="text-[10px] text-violet-700">
          ×{repair.occurrences}
        </span>
      )}
      {repair.reason && (
        <span className="text-[10px] italic text-violet-700/80">
          — {repair.reason}
        </span>
      )}
    </div>
    {repair.paragraph_preview && (
      <p className="mt-1 line-clamp-2 text-[11px] text-text-secondary">
        {repair.paragraph_preview}
      </p>
    )}
  </div>
);

// ─── warnings block ──────────────────────────────────────────────────

const WarningsBlock = ({
  parentWarnings,
  children,
}: {
  parentWarnings: string[];
  children: BundleChildRunV2[];
}) => (
  <div className="border-b border-amber-300 bg-amber-50 px-5 py-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-amber-900">
      Warnings
    </p>
    {parentWarnings.length > 0 && (
      <ul className="mt-1 space-y-0.5">
        {parentWarnings.map((w, i) => (
          <li key={`p-${i}`} className="text-[11px] text-amber-900">
            · {w}
          </li>
        ))}
      </ul>
    )}
    {children.map(
      (child, idx) =>
        child.finalized.warnings.length > 0 && (
          <div key={idx} className="mt-2">
            <p className="text-[10px] font-semibold text-amber-900">
              In companion: {child.template_name}
            </p>
            <ul className="mt-0.5 space-y-0.5">
              {child.finalized.warnings.map((w, i) => (
                <li key={`c-${idx}-${i}`} className="text-[11px] text-amber-900">
                  · {w}
                </li>
              ))}
            </ul>
          </div>
        ),
    )}
  </div>
);

// ─── empty filter state ──────────────────────────────────────────────

const EmptyFilterState = ({ onClear }: { onClear: () => void }) => (
  <div className="px-5 py-10 text-center">
    <FiFilter className="mx-auto h-5 w-5 text-subtle" />
    <p className="mt-2 text-xs text-text-secondary">
      No fields match the current filter.
    </p>
    <button
      type="button"
      onClick={onClear}
      className="mt-1.5 cursor-pointer text-[11px] font-semibold text-app-accent-text hover:underline"
    >
      Clear filter
    </button>
  </div>
);
