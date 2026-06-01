import { useMemo, useState } from 'react';
import { FiFileText, FiPlus, FiSearch } from 'react-icons/fi';
import { cn } from '@/utils';
import type { V2ComposerTask } from '@/services/studioV2ComposerAsync.service';
import type { V2DryRunTask } from '@/services/studioV2DryRunAsync.service';
import ComposerTasksRailSection from './ComposerTasksRailSection';
import DryRunTasksRailSection from './DryRunTasksRailSection';
import { TEMPLATE_ROLES, type StudioTemplate } from './types';

interface TemplatesRailProps {
  templates: StudioTemplate[];
  selectedTemplateId: string | null;
  onSelectTemplate: (id: string) => void;
  onUploadClick: () => void;
  /** Forwarded to ComposerTasksRailSection — fires when paralegal
   * clicks a COMPLETED composer card (navigate to the new template). */
  onComposerTaskClick?: (task: V2ComposerTask) => void;
  /** Forwarded to DryRunTasksRailSection — fires when paralegal clicks
   * a dry-run card (open AwaitingInputModalV2 for AWAITING_INPUT,
   * focus result for COMPLETED). */
  onDryRunTaskClick?: (task: V2DryRunTask) => void;
}

type StatusTone = 'live' | 'dirty' | 'done' | 'progress' | 'todo';

const computeStatus = (
  template: StudioTemplate,
): { label: string; tone: StatusTone } => {
  // Published group has only two states — clean live, or dirty after
  // a post-publish edit. Pills stay inside the Published group either
  // way, so the per-row label can be specific without contradicting
  // the group name.
  if (template.publishedAt !== null) {
    if (template.hasUnpublishedChanges) {
      return { label: 'Changes pending', tone: 'dirty' };
    }
    return { label: 'Live', tone: 'live' };
  }

  // Unpublished group — pill describes how close to publish-ready the
  // working draft is. Composer prefills every `params` so most fresh
  // templates land at "Ready to publish" until the paralegal cracks
  // them open and tunes; that's expected and no longer hidden behind
  // a fresh-vs-stale heuristic.
  const total = template.totalFields;
  const done = template.configuredFields;
  if (total === 0) return { label: 'Empty', tone: 'todo' };
  if (done < total) {
    if (done > 0) return { label: `${done}/${total} fields`, tone: 'progress' };
    return { label: 'Setup needed', tone: 'todo' };
  }
  return { label: 'Ready to publish', tone: 'done' };
};

const STATUS_PILL_STYLES: Record<StatusTone, string> = {
  // Live = stronger accent than Ready to publish — a published template
  // is visibly distinct from one merely fully configured.
  live: 'bg-app-accent text-white',
  dirty: 'bg-amber-100 text-amber-900',
  done: 'bg-app-accent-soft text-app-accent-text',
  progress: 'bg-amber-100 text-amber-900',
  todo: 'bg-surface-muted text-subtle',
};

export const TemplatesRail = ({
  templates,
  selectedTemplateId,
  onSelectTemplate,
  onUploadClick,
  onComposerTaskClick,
  onDryRunTaskClick,
}: TemplatesRailProps) => {
  const [query, setQuery] = useState('');

  const filteredTemplates = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return templates;
    return templates.filter((t) => t.name.toLowerCase().includes(q));
  }, [templates, query]);

  /**
   * Two groups keyed purely on `publishedAt`. Pills inside each group
   * still describe per-row state (Setup needed / N/M fields / Ready
   * to publish in Unpublished; Live / Changes pending in Published)
   * but the group itself only answers ONE question — has this
   * template ever been published? An earlier three-group variant
   * (Needs setup / Ready to publish / Published) leaned on a
   * fresh-vs-stale heuristic that mis-bucketed agent-prefilled
   * templates the paralegal hadn't touched yet; the binary split is
   * simpler and matches paralegal mental model.
   */
  const groupedTemplates = useMemo(() => {
    const unpublished: typeof filteredTemplates = [];
    const published: typeof filteredTemplates = [];
    for (const t of filteredTemplates) {
      if (t.publishedAt !== null) published.push(t);
      else unpublished.push(t);
    }
    return { unpublished, published };
  }, [filteredTemplates]);

  return (
    <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-surface">
      <div className="space-y-2 border-b border-border p-3">
        <button
          type="button"
          onClick={onUploadClick}
          className="inline-flex w-full cursor-pointer items-center justify-center gap-1.5 rounded-md bg-app-accent px-3 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90"
        >
          <FiPlus className="h-3.5 w-3.5" />
          Upload legal document
        </button>
        <div className="relative">
          <FiSearch
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle"
            aria-hidden="true"
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search templates…"
            className="w-full rounded-md border border-border bg-surface-muted py-1.5 pl-7 pr-2 text-xs text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent/20"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* Sticky in-progress strip — pinned to top of the scroll
            container so it stays visible as the user scrolls a long
            template list. Auto-hides when there are zero composer
            tasks. */}
        <ComposerTasksRailSection onTaskClick={onComposerTaskClick} />

        {/* Dry-run status section — sits below composer cards.
            Auto-hides when there are zero active OR failed dry-runs.
            Studio-only mount (this rail itself only lives on
            /studio-v2 so the cards never bleed into chat). */}
        <DryRunTasksRailSection onTaskClick={onDryRunTaskClick} />

        {filteredTemplates.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs italic text-subtle">
            {query
              ? `No templates match "${query}"`
              : 'No templates yet — upload one above.'}
          </p>
        ) : (
          <>
            <TemplateGroup
              label="Unpublished"
              accentColor="amber"
              templates={groupedTemplates.unpublished}
              selectedTemplateId={selectedTemplateId}
              onSelectTemplate={onSelectTemplate}
            />
            <TemplateGroup
              label="Published"
              accentColor="emerald"
              templates={groupedTemplates.published}
              selectedTemplateId={selectedTemplateId}
              onSelectTemplate={onSelectTemplate}
            />
          </>
        )}
      </div>

      <div className="shrink-0 border-t border-border px-3 py-2">
        <p className="text-[10px] text-subtle">
          {templates.length} {templates.length === 1 ? 'template' : 'templates'}
        </p>
      </div>
    </aside>
  );
};

// ─── Group sub-section ───────────────────────────────────────────────

type AccentColor = 'amber' | 'violet' | 'emerald';

interface TemplateGroupProps {
  label: string;
  accentColor: AccentColor;
  templates: StudioTemplate[];
  selectedTemplateId: string | null;
  onSelectTemplate: (id: string) => void;
}

const GROUP_DOT_STYLES: Record<AccentColor, string> = {
  amber: 'bg-amber-500',
  violet: 'bg-violet-500',
  emerald: 'bg-emerald-500',
};

const GROUP_LABEL_STYLES: Record<AccentColor, string> = {
  amber: 'text-amber-900',
  violet: 'text-violet-900',
  emerald: 'text-emerald-900',
};

/**
 * One labeled bucket of templates within the rail. Renders nothing
 * when empty so the rail stays visually compact for new firms with
 * mostly-empty groups.
 */
const TemplateGroup = ({
  label,
  accentColor,
  templates,
  selectedTemplateId,
  onSelectTemplate,
}: TemplateGroupProps) => {
  if (templates.length === 0) return null;

  return (
    <section className="mt-1" aria-label={`${label} templates`}>
      <header className="flex items-center gap-1.5 px-3 pb-1 pt-2">
        <span
          className={cn('h-1.5 w-1.5 rounded-full', GROUP_DOT_STYLES[accentColor])}
          aria-hidden
        />
        <h3
          className={cn(
            'text-[10px] font-bold uppercase tracking-wider',
            GROUP_LABEL_STYLES[accentColor],
          )}
        >
          {label}
        </h3>
        <span className="rounded-full bg-surface-muted px-1.5 py-0.5 text-[10px] font-semibold leading-none text-app-muted">
          {templates.length}
        </span>
      </header>
      {templates.map((template) => {
        const isSelected = selectedTemplateId === template.id;
        const status = computeStatus(template);
        const roleMeta = TEMPLATE_ROLES.find(
          (r) => r.key === template.config.role,
        );
        return (
          <button
            key={template.id}
            type="button"
            onClick={() => onSelectTemplate(template.id)}
            className={cn(
              'group relative flex w-full cursor-pointer items-start gap-2 px-3 py-2.5 text-left transition-colors',
              isSelected ? 'bg-app-accent-soft' : 'hover:bg-surface-muted',
            )}
          >
            {isSelected && (
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 w-[3px] bg-app-accent"
              />
            )}
            <FiFileText
              className={cn(
                'mt-0.5 h-4 w-4 shrink-0',
                isSelected ? 'text-app-accent-text' : 'text-subtle',
              )}
            />
            <div className="min-w-0 flex-1">
              <p
                className={cn(
                  'truncate text-xs font-semibold',
                  isSelected ? 'text-app-accent-text' : 'text-text-secondary',
                )}
                title={template.name}
              >
                {template.name}
              </p>
              <div className="mt-0.5 flex items-center gap-1.5">
                <span
                  className={cn(
                    'rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider',
                    STATUS_PILL_STYLES[status.tone],
                  )}
                >
                  {status.label}
                </span>
                <span className="truncate text-[10px] text-subtle">
                  · {template.updatedRelative}
                </span>
              </div>
              {roleMeta && template.config.role !== 'single' && (
                <p className="mt-0.5 truncate text-[10px] italic text-subtle">
                  {roleMeta.label}
                </p>
              )}
            </div>
          </button>
        );
      })}
    </section>
  );
};
