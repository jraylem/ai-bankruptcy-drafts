import { useEffect, useMemo, useState, type ReactElement } from 'react';
import { useStudioStore } from '@/stores/useStudioStore';
import {
  SOURCE_CATEGORY_LABELS,
  SOURCE_CATEGORY_ORDER,
  SOURCE_FAMILIES,
  type SourceCategoryKey,
  type SourceFamily,
  type SourceFamilyKey,
} from '@/utils/studio/sourceConfig';
import { SourceIcon } from './SourceIcon';
import type { FieldSource } from '@/types/studio';

interface SourcePickerProps {
  familyKey: SourceFamilyKey | null;
  onSelectFamily: (key: SourceFamilyKey) => void;
}

export const SourcePicker = ({
  familyKey,
  onSelectFamily,
}: SourcePickerProps): ReactElement => {
  const connectors = useStudioStore((state) => state.connectors);
  const loadConnectors = useStudioStore((state) => state.loadConnectors);
  const bundleRole = useStudioStore((state) => state.bundleRole);
  const [query, setQuery] = useState<string>('');

  useEffect((): void => {
    if (connectors.length === 0) void loadConnectors();
  }, [connectors.length, loadConnectors]);

  const grouped = useMemo(() => {
    // Bundling family (`inherit_from_parent`) is only meaningful for
    // child_only templates — the parent's bundling tab fills these slots,
    // so it makes no sense to author them on a standalone or parent template.
    const roleVisibleFamilies = SOURCE_FAMILIES.filter(
      (f) => f.key !== 'bundling' || bundleRole === 'child_only',
    );
    const q = query.trim().toLowerCase();
    const matching = q
      ? roleVisibleFamilies.filter(
          (f) =>
            f.displayName.toLowerCase().includes(q) ||
            f.description.toLowerCase().includes(q) ||
            f.patterns.some(
              (p) => p.label.toLowerCase().includes(q) || p.source.toLowerCase().includes(q)
            )
        )
      : roleVisibleFamilies;

    const groups: Record<SourceCategoryKey, SourceFamily[]> = {
      bundling: [],
      lookup: [],
      static: [],
      derived: [],
      interactive: [],
    };
    for (const f of matching) {
      groups[f.category].push(f);
    }
    return groups;
  }, [query, bundleRole]);

  const hasResults = useMemo(
    () => SOURCE_CATEGORY_ORDER.some((k) => grouped[k].length > 0),
    [grouped]
  );

  return (
    <div className="flex h-full flex-col bg-surface-muted/60">
      <div className="shrink-0 border-b border-border bg-surface px-3 py-3">
        <label className="relative block">
          <span className="sr-only">Search sources</span>
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle"
          >
            <circle cx="9" cy="9" r="6" />
            <path d="m14 14 3.5 3.5" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search sources…"
            className="w-full rounded-lg border border-border bg-surface py-2 pl-8 pr-3 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
          />
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {connectors.length === 0 && (
          <div className="mx-1 my-1 rounded-lg border border-dashed border-amber-300 bg-app-warning-soft px-3 py-3 text-xs text-amber-800">
            No source connectors loaded. Refresh the page, or check the network
            tab for{' '}
            <code className="font-mono">/api/v2/core/template/connectors</code>.
          </div>
        )}

        {connectors.length > 0 && !hasResults && (
          <div className="mx-1 my-2 rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted">
            No sources match <span className="font-medium">“{query}”</span>.
          </div>
        )}

        {SOURCE_CATEGORY_ORDER.map((cat) => {
          const items = grouped[cat];
          if (items.length === 0) return null;
          return (
            <div key={cat} className="mb-3 last:mb-1">
              <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-subtle">
                {SOURCE_CATEGORY_LABELS[cat]}
              </p>
              <div className="space-y-0.5">
                {items.map((family) => {
                  const isActive = familyKey === family.key;
                  const iconSource = primaryIconSourceFor(family);
                  return (
                    <button
                      key={family.key}
                      type="button"
                      onClick={() => onSelectFamily(family.key)}
                      aria-pressed={isActive}
                      title={family.description}
                      className={`group flex w-full items-start gap-2.5 rounded-lg px-2 py-2 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-app-accent ${
                        isActive
                          ? 'bg-app-accent-soft ring-1 ring-app-accent'
                          : 'hover:bg-surface'
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md ${
                          isActive
                            ? 'bg-surface text-app-accent-text'
                            : 'bg-app-accent-soft text-app-accent-text'
                        }`}
                      >
                        <SourceIcon source={iconSource} className="h-4 w-4" />
                      </span>
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span
                          className={`flex items-center gap-1.5 truncate text-sm font-semibold ${
                            isActive ? 'text-app-accent-text' : 'text-text-secondary'
                          }`}
                        >
                          {family.displayName}
                          {family.patterns.length > 1 && (
                            <span
                              className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                                isActive
                                  ? 'bg-surface text-app-accent-text'
                                  : 'bg-surface-muted text-muted'
                              }`}
                            >
                              {family.patterns.length}
                            </span>
                          )}
                        </span>
                        <span className="truncate text-xs text-muted">
                          {family.description}
                        </span>
                      </span>
                      {isActive && (
                        <svg
                          aria-hidden="true"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className="mt-0.5 h-4 w-4 shrink-0 text-app-accent-text"
                        >
                          <path d="M7.629 13.065 4.4 9.836a.75.75 0 1 1 1.06-1.06l2.169 2.168 6.911-6.91a.75.75 0 0 1 1.06 1.06l-7.441 7.44a.75.75 0 0 1-1.06 0Z" />
                        </svg>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const primaryIconSourceFor = (family: SourceFamily): FieldSource => {
  const raw = family.patterns.find((p) => p.key === 'raw');
  if (raw) return raw.source;
  return family.patterns[0]!.source;
};

export default SourcePicker;
