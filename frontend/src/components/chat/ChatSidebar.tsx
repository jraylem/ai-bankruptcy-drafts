import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  LuFileQuestion,
  LuFilePen,
  LuInbox,
  LuLayoutTemplate,
  LuLoader,
  LuPlus,
  LuSearch,
} from 'react-icons/lu';
import { useShallow } from 'zustand/react/shallow';

import { useStudioStore } from '@/stores/useStudioStore';
import { useCaseChatStore } from '@/stores/useCaseChatStore';
import { useCaseInbox } from '@/features/case-inbox/useCaseInbox';
import { readStudioEntry } from '@/hooks/useStudioPersistence';
import { useToastStore } from '@/stores/useToastStore';
import { useWorkspaceSplitStore } from '@/stores/useWorkspaceSplitStore';
import { SidebarBrand } from '@/components/layout/SidebarBrand';
import { SidebarFooterUserMenu } from '@/components/layout/SidebarFooterUserMenu';
import { deriveCaseInitials, formatCaseName } from '@/utils/studio';

import { DeleteConfirmModal } from './DeleteConfirmModal';

const DESKTOP_BREAKPOINT_QUERY = '(min-width: 1024px)';

const isMobileViewport = (): boolean =>
  typeof window === 'undefined' ? false : !window.matchMedia(DESKTOP_BREAKPOINT_QUERY).matches;

const normalizeSearchQuery = (value: string) => value.toLowerCase().trim();

const matchesSearch = (query: string, ...values: Array<string | undefined>) =>
  values.some((value) => value?.toLowerCase().includes(query));

interface ChatSidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

/**
 * Running-stripe border halo for a case row / tile while its chat turn
 * streams. Reuses the `.glow-border-line` keyframe from `src/index.css`
 * (also drives the document-viewer modal's loading halo): an SVG <rect>
 * traces the container's border path, `strokeDasharray` carves a 22%
 * slice out of the perimeter, and animated `stroke-dashoffset` slides
 * that slice around the path. `pathLength="100"` + non-scaling-stroke
 * keeps the math identical for any container size (40×40 tile or
 * variable-width row).
 *
 * Sits as the LAST DOM child of its `relative` wrapper so it paints
 * over the button content. `pointer-events-none` keeps the underlying
 * button clickable. `motion-reduce:hidden` swaps the running stripe
 * for a static indigo ring (rendered separately by the caller — see
 * the streaming branches in the row / tile JSX).
 */
function StreamingBorderHalo({
  rx,
  uniqueId,
}: {
  rx: number;
  uniqueId: string;
}): React.ReactElement {
  const gradientId = `case-stream-halo-${uniqueId}`;
  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full overflow-visible motion-reduce:hidden"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="50%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#a78bfa" />
        </linearGradient>
      </defs>
      <rect
        className="case-stream-halo"
        x="0"
        y="0"
        width="100%"
        height="100%"
        rx={rx}
        ry={rx}
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="2"
        strokeLinecap="round"
        pathLength="100"
        strokeDasharray="22 78"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

const ChatSidebarImpl: React.FC<ChatSidebarProps> = ({
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const isStudioRoute = location.pathname.startsWith('/studio');
  const isInboxRoute = location.pathname.startsWith('/inbox');
  const isCaseRoute =
    location.pathname === '/' || location.pathname.startsWith('/case');

  const {
    templates: studioTemplates,
    selectedTemplateId: studioSelectedTemplateId,
    deleteTemplate: studioDeleteTemplate,
    cases: studioCases,
    selectedCaseId: studioSelectedCaseId,
    selectCase: studioSelectCase,
    isLoadingTemplates: studioIsLoadingTemplates,
    isLoadingCases: studioIsLoadingCases,
    casesHasMore: studioCasesHasMore,
    isLoadingMoreCases: studioIsLoadingMoreCases,
    loadMoreCases: studioLoadMoreCases,
    reorderCases: studioReorderCases,
    isDirty: studioIsDirty,
    isBundlingDirty: studioIsBundlingDirty,
    pendingCase: pendingNewCase,
    startNewCase,
    cancelNewCase,
  } = useStudioStore();

  // Secondary (right-pane) case + which pane is currently focused.
  // Both the primary and the secondary case get the same "selected"
  // treatment in the sidebar; the checkmark follows the focused pane
  // so the user can tell which pane they're actively typing in.
  const splitSecondaryCaseId = useWorkspaceSplitStore((s) => s.secondaryCaseId);
  const splitFocusedPane = useWorkspaceSplitStore((s) => s.focusedPane);
  const splitSetSecondaryCaseId = useWorkspaceSplitStore((s) => s.setSecondaryCaseId);
  const splitSetFocusedPane = useWorkspaceSplitStore((s) => s.setFocusedPane);

  // Inbox badge count — shares the React Query cache with CaseInboxSidebar
  // (same queryKey), so this is deduped, not a second fetch.
  const { pendingCount: inboxPendingCount } = useCaseInbox();

  // Per-case chat state surfaced as flat id lists. `useShallow` keeps the
  // sidebar from re-rendering on every streamed content delta — only the
  // *set* of streaming / unread cases matters here, not their contents.
  const streamingCaseIds = useCaseChatStore(
    useShallow((s) =>
      Object.entries(s.byCase)
        .filter(([, slice]) => slice.isStreaming)
        .map(([id]) => id),
    ),
  );
  const unreadCaseIds = useCaseChatStore(
    useShallow((s) =>
      Object.entries(s.byCase)
        .filter(([, slice]) => slice.hasUnread)
        .map(([id]) => id),
    ),
  );
  const streamingCaseSet = useMemo(
    () => new Set(streamingCaseIds),
    [streamingCaseIds],
  );
  const unreadCaseSet = useMemo(
    () => new Set(unreadCaseIds),
    [unreadCaseIds],
  );

  const [studioSearchQuery, setStudioSearchQuery] = useState('');
  const [isSearchBarHidden, setIsSearchBarHidden] = useState<boolean>(false);
  const casesScrollRef = useRef<HTMLDivElement | null>(null);
  const [templateDeleteConfirm, setTemplateDeleteConfirm] = useState<{
    isOpen: boolean;
    templateId: string | null;
    templateName: string | null;
    // Populated when the first (non-force) delete returns 409. The modal
    // then renders a force-delete affordance listing which parents
    // would have their bundle_companions cascade-cleaned.
    conflictParents: { template_id: string; name: string; companion_labels: string[] }[] | null;
  }>({
    isOpen: false,
    templateId: null,
    templateName: null,
    conflictParents: null,
  });
  const [isDeletingTemplate, setIsDeletingTemplate] = useState<boolean>(false);

  const handleConfirmDeleteTemplate = useCallback(async (): Promise<void> => {
    const id = templateDeleteConfirm.templateId;
    if (!id || isDeletingTemplate) return;
    setIsDeletingTemplate(true);
    const onDeletedTemplateRoute = location.pathname.startsWith(
      `/studio/template/${id}`,
    );
    // First-pass = force=false; if the modal already escalated to the
    // force-delete state (conflictParents !== null), we send force=true.
    const force = templateDeleteConfirm.conflictParents !== null;
    const result = await studioDeleteTemplate(id, force);
    setIsDeletingTemplate(false);

    // Conflict path — leave the modal open, swap it to force-delete UI.
    if (!result.success && result.conflictParents && result.conflictParents.length > 0) {
      setTemplateDeleteConfirm((prev) => ({
        ...prev,
        conflictParents: result.conflictParents ?? null,
      }));
      return;
    }

    if (result.success) {
      if (onDeletedTemplateRoute) {
        navigate('/studio', { replace: true });
      }
      const cleanedCount = result.cleanedParents?.length ?? 0;
      const msg = cleanedCount > 0
        ? `Template deleted. Cleaned ${cleanedCount} parent template(s).`
        : 'Template deleted';
      useToastStore.getState().addToast(msg, 'success');
    } else if (result.error) {
      useToastStore.getState().addToast(result.error, 'error');
    }
    setTemplateDeleteConfirm({
      isOpen: false, templateId: null, templateName: null, conflictParents: null,
    });
  }, [
    templateDeleteConfirm.templateId,
    templateDeleteConfirm.conflictParents,
    isDeletingTemplate,
    location.pathname,
    navigate,
    studioDeleteTemplate,
  ]);

  const [isTemplatesSectionCollapsed, setIsTemplatesSectionCollapsed] = useState<boolean>(false);
  // Floating "magnifier" popover for the templates list. On row hover we
  // capture the row's bounding rect so a portaled card can render the
  // full template name + role pill to the right of the sidebar, escaping
  // the sidebar's overflow-hidden chain. Null when no row is hovered.
  const [hoveredTemplatePreview, setHoveredTemplatePreview] = useState<{
    templateId: string;
    name: string;
    role: 'standalone' | 'parent' | 'child_only';
    hasAgentConfig: boolean;
    isDirty: boolean;
    rect: DOMRect;
  } | null>(null);
  // Same pattern for the cases list — captures the row's bounding rect so
  // a portaled card can render the full case_name + case_number to the
  // right of the sidebar without being clipped by the sidebar's overflow.
  const [hoveredCasePreview, setHoveredCasePreview] = useState<{
    caseId: string;
    caseName: string;
    caseNumber: string;
    rect: DOMRect;
  } | null>(null);
  const [isMobile, setIsMobile] = useState<boolean>(isMobileViewport);

  // Drag-to-reorder state for the cases list.
  const [draggedCaseId, setDraggedCaseId] = useState<string | null>(null);
  const [caseDropTarget, setCaseDropTarget] = useState<{
    id: string;
    position: 'before' | 'after';
  } | null>(null);

  // Belt-and-braces drag cleanup: a row's own onDragEnd can miss when
  // the drop lands outside the sidebar (e.g. on the workspace, opening
  // a split pane) and React re-renders mid-event. Listening on window
  // guarantees we clear the dragged state so the row doesn't get
  // stuck at opacity-50.
  useEffect(() => {
    if (!draggedCaseId) return;
    const clear = () => {
      setDraggedCaseId(null);
      setCaseDropTarget(null);
    };
    window.addEventListener('dragend', clear);
    window.addEventListener('drop', clear);
    return () => {
      window.removeEventListener('dragend', clear);
      window.removeEventListener('drop', clear);
    };
  }, [draggedCaseId]);

  // Sidebar click on a case row. When the split is open we treat the
  // primary pane as the "current working case" and route new clicks
  // into the secondary pane instead of replacing the primary.
  //   - Click the primary's case → just focus it.
  //   - Click the secondary's case → just focus it.
  //   - Click any other case → put it in the secondary pane.
  // When no split is open, fall back to ordinary primary navigation.
  const handleCaseRowClick = useCallback(
    (caseId: string) => {
      if (splitSecondaryCaseId !== null) {
        if (caseId === studioSelectedCaseId) {
          splitSetFocusedPane('primary');
          return;
        }
        if (caseId === splitSecondaryCaseId) {
          splitSetFocusedPane('secondary');
          return;
        }
        splitSetSecondaryCaseId(caseId);
        splitSetFocusedPane('secondary');
        return;
      }
      studioSelectCase(caseId);
    },
    [
      splitSecondaryCaseId,
      studioSelectedCaseId,
      splitSetFocusedPane,
      splitSetSecondaryCaseId,
      studioSelectCase,
    ],
  );

  useEffect((): (() => void) | void => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia(DESKTOP_BREAKPOINT_QUERY);
    const handler = (e: MediaQueryListEvent): void => setIsMobile(!e.matches);
    mq.addEventListener('change', handler);
    return (): void => mq.removeEventListener('change', handler);
  }, []);

  // Collapse the "Search cases" bar when the user scrolls down through
  // the cases list, reveal it on scroll-up. Native passive listener —
  // runs off the main thread, no library overhead. Direction state only
  // mutates when it flips, so React renders are minimal.
  useEffect((): (() => void) | undefined => {
    const element: HTMLDivElement | null = casesScrollRef.current;
    if (!element) return undefined;

    const HIDE_THRESHOLD_PX: number = 16;
    const REVEAL_DELTA_PX: number = 4;
    let lastScrollTop: number = element.scrollTop;

    const handleScroll = (): void => {
      const currentScrollTop: number = element.scrollTop;
      const delta: number = currentScrollTop - lastScrollTop;
      if (currentScrollTop <= HIDE_THRESHOLD_PX) {
        setIsSearchBarHidden(false);
      } else if (delta > 0) {
        setIsSearchBarHidden(true);
      } else if (delta < -REVEAL_DELTA_PX) {
        setIsSearchBarHidden(false);
      }
      lastScrollTop = currentScrollTop;
    };

    element.addEventListener('scroll', handleScroll, { passive: true });
    return (): void => element.removeEventListener('scroll', handleScroll);
  }, []);

  const renderCollapsed = isCollapsed || isMobile;

  const normalizedStudioSearchQuery = useMemo(
    () => normalizeSearchQuery(studioSearchQuery),
    [studioSearchQuery],
  );

  const filteredStudioTemplates = useMemo(() => {
    const base = normalizedStudioSearchQuery
      ? studioTemplates.filter((tpl) =>
          matchesSearch(normalizedStudioSearchQuery, tpl.name),
        )
      : studioTemplates;
    // Sort newest-first by `created_at` (ISO 8601 strings sort
    // lexicographically). Null timestamps sink to the bottom so
    // legacy rows without a creation date don't dominate the top.
    return [...base].sort((a, b) => {
      if (!a.created_at && !b.created_at) return 0;
      if (!a.created_at) return 1;
      if (!b.created_at) return -1;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [normalizedStudioSearchQuery, studioTemplates]);

  // Per-template "has unsaved changes" tracker. The actively-edited
  // template's dirty state lives in the studio store (covers spec +
  // bundling). Other templates can have unsaved spec changes cached
  // in localStorage from prior sessions or accidental tab navigation.
  // Combined into one Set so the sidebar row render can flag both.
  const dirtyTemplateIds = useMemo<Set<string>>(() => {
    const set = new Set<string>();
    for (const tpl of studioTemplates) {
      if (tpl.id === studioSelectedTemplateId) {
        if (studioIsDirty || studioIsBundlingDirty) set.add(tpl.id);
        continue;
      }
      if (readStudioEntry(tpl.id)?.isDirty === true) set.add(tpl.id);
    }
    return set;
  }, [studioTemplates, studioSelectedTemplateId, studioIsDirty, studioIsBundlingDirty]);

  const filteredStudioCases = useMemo(() => {
    if (!normalizedStudioSearchQuery) return studioCases;
    const digitsOnlyQuery = normalizedStudioSearchQuery.replace(/\D/g, '');
    return studioCases.filter((c) => {
      if (
        matchesSearch(
          normalizedStudioSearchQuery,
          c.case_name,
          c.case_number,
          c.case_number_original ?? undefined,
          c.court_district ?? undefined,
          c.chapter != null ? String(c.chapter) : undefined,
        )
      ) {
        return true;
      }
      if (digitsOnlyQuery) {
        const caseDigits = `${c.case_number}${c.case_number_original ?? ''}`.replace(/\D/g, '');
        if (caseDigits.includes(digitsOnlyQuery)) return true;
      }
      return false;
    });
  }, [normalizedStudioSearchQuery, studioCases]);

  // Route-aware `+ New Case`: when on the case workspace we drive the
  // inline upload flow (route `/case/new` + optimistic placeholder row);
  // on Studio it still launches the same dropzone — the case workspace
  // page handles both arrival paths.
  //
  // We call `startNewCase()` BEFORE navigate so the store's
  // `selectedCaseId` is already the synthetic `untitled-*` id by the
  // time the URL transitions. This prevents the page's store→URL sync
  // effect from briefly bouncing back to the previously-selected case
  // URL (which was the symptom: click + New Case → URL flickers to
  // /new then snaps back to /case/<prev>).
  const handleNewCase = (): void => {
    if (!useStudioStore.getState().pendingCase) {
      startNewCase();
    }
    navigate('/case/new');
  };

  // Workspace nav — Inbox v2, Template Studio, Case workspace. All three
  // are real route navigations now (no in-sidebar mode toggles).
  type NavTile = {
    key: 'inbox' | 'studio' | 'case';
    label: string;
    Icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>;
    active: boolean;
    to: string;
    count: number;
    /** Red corner dot — only the Inbox lights up, and only when it has items. */
    showDot: boolean;
  };

  const navTiles: NavTile[] = [
    {
      key: 'inbox',
      label: 'Inbox',
      Icon: LuInbox,
      active: isInboxRoute,
      to: '/inbox',
      count: inboxPendingCount,
      showDot: inboxPendingCount > 0,
    },
    {
      key: 'case',
      label: 'Cases',
      Icon: LuFilePen,
      active: isCaseRoute,
      to: '/',
      count: studioCases.length,
      showDot: false,
    },
  ];

  // Shared hover/focus tooltip for case rows. Portaled to <body> so it
  // escapes the sidebar's overflow-hidden chain. Used by both the
  // expanded list rows and the collapsed initials tiles — same data
  // shape, so a single render expression backs both views.
  const casePreviewPortal =
    hoveredCasePreview &&
    createPortal(
      (() => {
        const GAP = 8;
        const PREVIEW_MAX_WIDTH = 360;
        const top = hoveredCasePreview.rect.top;
        const rightEdge =
          hoveredCasePreview.rect.right + GAP + PREVIEW_MAX_WIDTH;
        const overflowsRight =
          typeof window !== 'undefined' && rightEdge > window.innerWidth;
        const left = overflowsRight
          ? Math.max(
              GAP,
              hoveredCasePreview.rect.left - PREVIEW_MAX_WIDTH - GAP,
            )
          : hoveredCasePreview.rect.right + GAP;
        return (
          <div
            role="tooltip"
            aria-hidden="true"
            style={{
              position: 'fixed',
              top,
              left,
              maxWidth: PREVIEW_MAX_WIDTH,
              zIndex: 60,
            }}
            className="pointer-events-none flex flex-col gap-0.5 rounded-lg border border-app-accent-soft bg-surface px-3 py-2 shadow-xl ring-1 ring-black/10"
          >
            <span className="break-words text-sm font-medium text-text-secondary">
              {hoveredCasePreview.caseName}
            </span>
            <span className="text-[11px] text-muted">
              {hoveredCasePreview.caseNumber}
            </span>
          </div>
        );
      })(),
      document.body,
    );

  // Collapsed view — forced on mobile (<lg) regardless of prop, so the 256px
  // expanded sidebar never squeezes the main pane to a few characters wide.
  if (renderCollapsed) {
    return (
      <div
        className="flex h-full flex-col border-r border-border bg-surface text-text transition-all duration-300"
        style={{ width: '64px' }}
      >
        <SidebarBrand isCollapsed onToggleCollapse={onToggleCollapse} />

        {/* Primary actions — icon-only in collapsed sidebar */}
        <div className="px-3 py-3 flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={handleNewCase}
            className="w-8 h-8 flex items-center justify-center bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white rounded-lg transition-all duration-200 shadow-sm hover:shadow-md cursor-pointer"
            title="New Case"
          >
            <LuPlus className="w-4 h-4" aria-hidden="true" />
          </button>
          {navTiles.map(({ key, label, Icon, active, to, count, showDot }) => (
            <NavLink
              key={key}
              to={to}
              aria-current={active ? 'page' : undefined}
              title={count > 0 ? `${label} (${count})` : label}
              className={`relative w-8 h-8 flex items-center justify-center rounded-lg border transition-all duration-200 shadow-sm hover:shadow-md ${
                active
                  ? 'border-app-border-strong bg-app-accent-soft text-app-accent-text'
                  : 'border-border text-text-secondary hover:border-app-accent/55 hover:bg-app-accent-soft hover:text-app-accent-text'
              }`}
            >
              <Icon className="w-4 h-4" aria-hidden="true" />
              {showDot && (
                <span
                  aria-hidden="true"
                  className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border-2 border-surface bg-red-500"
                />
              )}
            </NavLink>
          ))}
        </div>

        {/* Collapsed case rail — initials avatars with the same hover/focus
            tooltip portal used by the expanded view. Streaming + unread
            indicators render here too (no expanded-only states). */}
        {filteredStudioCases.length > 0 ? (
          <nav
            aria-label="Cases"
            className="hide-scrollbar min-h-0 flex-1 overflow-y-auto pb-3"
            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
          >
            <div
              aria-hidden="true"
              className="mx-auto mb-3 h-px w-8 bg-border"
            />
            <div className="flex flex-col items-center gap-2">
              {filteredStudioCases.map((c) => {
                const isPrimaryCase = studioSelectedCaseId === c.id;
                const isSecondaryCase =
                  !isPrimaryCase && splitSecondaryCaseId === c.id;
                const isSelectedInAnyPane = isPrimaryCase || isSecondaryCase;
                const isFocusedPaneCase =
                  (isPrimaryCase && splitFocusedPane === 'primary') ||
                  (isSecondaryCase && splitFocusedPane === 'secondary');
                const isCaseStreaming = streamingCaseSet.has(c.id);
                const showUnread =
                  unreadCaseSet.has(c.id) &&
                  !isCaseStreaming &&
                  !isSelectedInAnyPane;
                const displayName = formatCaseName(c.case_name);
                const initials = deriveCaseInitials(c.case_name);
                const ariaLabel = [
                  `${displayName}, case ${c.case_number}`,
                  isCaseStreaming ? 'AI working' : null,
                  showUnread ? 'new activity' : null,
                ]
                  .filter(Boolean)
                  .join(', ');
                const captureRect = (
                  e:
                    | React.MouseEvent<HTMLButtonElement>
                    | React.FocusEvent<HTMLButtonElement>,
                ) =>
                  setHoveredCasePreview({
                    caseId: c.id,
                    caseName: displayName,
                    caseNumber: c.case_number,
                    rect: e.currentTarget.getBoundingClientRect(),
                  });
                const clearRect = () =>
                  setHoveredCasePreview((prev) =>
                    prev?.caseId === c.id ? null : prev,
                  );
                return (
                  <div
                    key={c.id}
                    className={`relative h-10 w-10 ${
                      isCaseStreaming ? 'case-stream-glow rounded-lg' : ''
                    }`}
                  >
                    {/* Selection bar — sits OUTSIDE the tile to the left
                        so the 40×40 avatar stays the visual anchor. */}
                    {isSelectedInAnyPane && (
                      <span
                        aria-hidden="true"
                        className={`absolute -left-2 inset-y-1 w-1 rounded-full bg-indigo-500 ${
                          isFocusedPaneCase ? '' : 'opacity-50'
                        }`}
                      />
                    )}
                    {/* motion-reduce fallback — running stripe is
                        suppressed for users who opted out of motion,
                        replaced by a static indigo ring. The animated
                        SVG halo for the motion-safe path is appended
                        AFTER the button so it paints on top of the
                        tile. */}
                    {isCaseStreaming && (
                      <span
                        aria-hidden="true"
                        className="pointer-events-none absolute inset-0 hidden rounded-lg ring-2 ring-indigo-500/60 motion-reduce:block"
                      />
                    )}
                    <button
                      type="button"
                      draggable
                      onClick={() => handleCaseRowClick(c.id)}
                      onDragStart={(e) => {
                        setDraggedCaseId(c.id);
                        e.dataTransfer.effectAllowed = 'move';
                        e.dataTransfer.setData('text/plain', c.id);
                      }}
                      onDragEnd={() => {
                        setDraggedCaseId(null);
                        setCaseDropTarget(null);
                      }}
                      onMouseEnter={captureRect}
                      onMouseLeave={clearRect}
                      onFocus={captureRect}
                      onBlur={clearRect}
                      aria-label={ariaLabel}
                      aria-current={isPrimaryCase ? 'true' : undefined}
                      className={`relative flex h-10 w-10 items-center justify-center rounded-lg text-xs font-semibold uppercase tracking-tight ring-1 ring-inset transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${
                        isSelectedInAnyPane
                          ? 'bg-app-accent-soft text-app-accent-text ring-app-accent/45 shadow-sm'
                          : 'bg-surface-muted text-text-secondary ring-border hover:bg-app-accent-soft/40 hover:ring-app-accent/55'
                      } ${draggedCaseId === c.id ? 'opacity-50' : ''}`}
                    >
                      {initials ? (
                        initials
                      ) : (
                        <LuFileQuestion
                          className="h-4 w-4 text-muted"
                          aria-hidden="true"
                        />
                      )}
                      {/* Amber unread dot. ring-2 in surface color carves
                          out a "donut" so it reads as a sticker on top
                          of any tile background. */}
                      {showUnread && (
                        <span
                          aria-hidden="true"
                          className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-amber-500 ring-2 ring-surface"
                        />
                      )}
                    </button>
                    {isCaseStreaming && (
                      <StreamingBorderHalo
                        rx={8}
                        uniqueId={`tile-${c.id}`}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </nav>
        ) : (
          <div className="min-h-0 flex-1" />
        )}

        <SidebarFooterUserMenu isCollapsed />

        <DeleteConfirmModal
          isOpen={templateDeleteConfirm.isOpen}
          title={
            templateDeleteConfirm.conflictParents
              ? 'Template Is Used By Other Templates'
              : 'Delete Template'
          }
          message={
            templateDeleteConfirm.conflictParents
              ? `"${templateDeleteConfirm.templateName ?? 'This template'}" is referenced by ${templateDeleteConfirm.conflictParents.length} parent template${templateDeleteConfirm.conflictParents.length === 1 ? '' : 's'}:`
              : `Are you sure you want to delete "${templateDeleteConfirm.templateName ?? 'this template'}"? This action cannot be undone.`
          }
          detail={
            templateDeleteConfirm.conflictParents && (
              <>
                <ul className="max-h-48 overflow-y-auto rounded-md ring-1 ring-border divide-y divide-border bg-surface-muted">
                  {templateDeleteConfirm.conflictParents.map((p) => (
                    <li key={p.template_id} className="px-3 py-2">
                      <div className="text-sm font-medium text-text break-words">{p.name}</div>
                      {p.companion_labels.length > 0 && (
                        <div className="mt-0.5 text-xs text-subtle break-words">
                          {p.companion_labels.join(', ')}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-app-danger-text">
                  Force delete will remove this template from those parents&apos; bundle companions and then delete it. This action cannot be undone.
                </p>
              </>
            )
          }
          confirmText={
            templateDeleteConfirm.conflictParents
              ? `Force delete (clean ${templateDeleteConfirm.conflictParents.length} parent${templateDeleteConfirm.conflictParents.length === 1 ? '' : 's'})`
              : 'Delete'
          }
          cancelText="Cancel"
          onConfirm={handleConfirmDeleteTemplate}
          onCancel={() => setTemplateDeleteConfirm({
            isOpen: false, templateId: null, templateName: null, conflictParents: null,
          })}
          variant="danger"
          isProcessing={isDeletingTemplate}
        />

        {casePreviewPortal}
      </div>
    );
  }

  // Expanded view
  return (
    <div
      className="flex h-full flex-col border-r border-border bg-surface text-text transition-all duration-300"
      style={{ width: '256px' }}
    >
      <SidebarBrand isCollapsed={false} onToggleCollapse={onToggleCollapse} />

      {/* Primary action + workspace rail + filter search */}
      <div className="px-3 pt-3 pb-0">
        <button
          type="button"
          onClick={handleNewCase}
          className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
        >
          <LuPlus className="h-4 w-4" aria-hidden="true" />
          New Case
        </button>

        {/* Workspace nav — stacked icon + label rows, grouped in a single
            soft container so they read as related options rather than
            independent CTAs competing with each other. */}
        <nav aria-label="Workspace" className="mt-2.5 flex flex-col gap-1.5">
          {navTiles.map(({ key, label, Icon, active, to, count, showDot }) => (
            <NavLink
              key={key}
              to={to}
              aria-current={active ? 'page' : undefined}
              className={`group relative flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-app-accent ${
                active
                  ? 'border-app-border-strong bg-app-accent-soft font-semibold text-app-accent-text'
                  : 'border-border text-text-secondary hover:border-app-accent/55 hover:bg-app-accent-soft/50 hover:text-text'
              }`}
            >
              <Icon
                className={`h-4 w-4 shrink-0 ${active ? 'text-app-accent-text' : 'text-muted group-hover:text-text'}`}
                aria-hidden="true"
              />
              <span>
                {label}
                {count > 0 && ` (${count})`}
              </span>
              {showDot && (
                <span
                  aria-hidden="true"
                  className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full border-2 border-surface bg-red-500"
                />
              )}
            </NavLink>
          ))}
        </nav>

        {/* Filter search — sits directly above the list it filters.
            The outer wrapper animates collapsed/expanded with scroll: it
            hides when the user scrolls down through the cases list and
            re-appears on scroll-up. */}
        <div
          className={`transition-all duration-200 ease-out ${
            isSearchBarHidden
              ? 'pointer-events-none mt-0 mb-0 max-h-0 -translate-y-1 opacity-0'
              : 'mt-2.5 mb-3 max-h-12 translate-y-0 opacity-100'
          }`}
          aria-hidden={isSearchBarHidden}
        >
          <div className="relative">
            <LuSearch
              aria-hidden="true"
              className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle"
            />
            <input
              type="text"
              placeholder="Search cases…"
              value={studioSearchQuery}
              onChange={(event: React.ChangeEvent<HTMLInputElement>): void =>
                setStudioSearchQuery(event.target.value)
              }
              aria-label="Search cases"
              className="w-full rounded-md border border-border bg-surface py-1.5 pl-8 pr-7 text-sm text-text placeholder:text-subtle transition focus:border-transparent focus:outline-none focus:ring-2 focus:ring-app-accent"
            />
            {studioSearchQuery && (
              <button
                type="button"
                onClick={() => setStudioSearchQuery('')}
                aria-label="Clear search"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-subtle transition-colors hover:bg-app-accent-soft hover:text-text"
              >
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Templates (Studio only) + Cases list */}
      <div
        className="flex-1 p-3 scrollbar-hide flex flex-col overflow-hidden"
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
      >
        <div className="flex min-h-0 flex-1 flex-col gap-2">
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
            {isStudioRoute && (
              <section
                className={`flex min-h-0 flex-col overflow-hidden rounded-lg ${
                  isTemplatesSectionCollapsed ? 'shrink-0' : 'flex-1'
                }`}
              >
                <button
                  type="button"
                  onClick={() => setIsTemplatesSectionCollapsed((v) => !v)}
                  className="sticky top-0 z-10 flex w-full shrink-0 items-center justify-between gap-2 rounded-md bg-surface/95 px-2 py-1.5 text-left shadow-[0_2px_4px_-1px_rgba(0,0,0,0.08)] backdrop-blur transition-colors hover:bg-surface-muted"
                  aria-expanded={!isTemplatesSectionCollapsed}
                >
                  <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-app-accent-text [text-shadow:0_1px_0_rgba(255,255,255,0.7)]">
                    <LuLayoutTemplate className="h-3.5 w-3.5" aria-hidden="true" />
                    Templates
                    {studioTemplates.length > 0 && (
                      <span className="rounded-full bg-app-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-app-accent-text">
                        {studioTemplates.length}
                      </span>
                    )}
                  </span>
                  <svg
                    className={`h-3.5 w-3.5 text-subtle transition-transform duration-150 ${
                      isTemplatesSectionCollapsed ? '-rotate-90' : ''
                    }`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {!isTemplatesSectionCollapsed && (
                  <div className="hide-scrollbar min-h-0 flex-1 overflow-y-auto pr-1">
                    {studioIsLoadingTemplates && studioTemplates.length === 0 ? (
                      <div className="space-y-4 px-1 py-2" aria-busy="true" aria-label="Loading templates">
                        {[0, 1, 2, 3].map((i) => (
                          <div key={i} className="space-y-2 px-2">
                            <span className="block h-3 w-[85%] animate-pulse rounded bg-border" />
                            <span className="block h-3 w-[55%] animate-pulse rounded bg-border" />
                          </div>
                        ))}
                      </div>
                    ) : studioTemplates.length === 0 ? (
                      <div className="px-2 py-6 text-center text-subtle text-sm">
                        <p>No templates yet</p>
                        <p className="text-xs mt-1">Upload a DOCX to get started</p>
                      </div>
                    ) : (
                      <div className="space-y-0.5">
                        {filteredStudioTemplates.length === 0 && (
                          <div className="px-2 py-4 text-center text-xs text-subtle">
                            No templates match “{studioSearchQuery}”.
                          </div>
                        )}
                        {filteredStudioTemplates.map((tpl) => {
                          const isActive = studioSelectedTemplateId === tpl.id;
                          const isTplDirty = dirtyTemplateIds.has(tpl.id);
                          const rolePill =
                            tpl.bundle_role === 'parent'
                              ? { label: 'Parent', cls: 'bg-app-accent-soft text-app-accent-text' }
                              : tpl.bundle_role === 'child_only'
                                ? { label: 'Child', cls: 'bg-app-warning-soft text-amber-800' }
                                : null;
                          return (
                            <div
                              key={tpl.id}
                              onMouseEnter={(e) =>
                                setHoveredTemplatePreview({
                                  templateId: tpl.id,
                                  name: tpl.name,
                                  role: tpl.bundle_role,
                                  hasAgentConfig: Boolean(tpl.agent_config),
                                  isDirty: isTplDirty,
                                  rect: e.currentTarget.getBoundingClientRect(),
                                })
                              }
                              onMouseLeave={() =>
                                setHoveredTemplatePreview((prev) =>
                                  prev?.templateId === tpl.id ? null : prev,
                                )
                              }
                              className={`group relative w-full rounded-lg transition-colors duration-150 ${
                                isActive
                                  ? 'border border-app-accent-soft bg-app-accent-soft shadow-sm'
                                  : 'hover:bg-surface-muted'
                              }`}
                            >
                              {isActive && (
                                <span
                                  className="absolute inset-y-2 left-1 w-1 rounded-full bg-indigo-500"
                                  aria-hidden="true"
                                />
                              )}
                              <button
                                type="button"
                                onClick={() => navigate(`/studio/template/${tpl.id}`)}
                                className="flex w-full items-center gap-2 px-3 py-2 pr-9 text-left"
                              >
                                <span
                                  className={`h-2 w-2 shrink-0 rounded-full ${
                                    isTplDirty
                                      ? 'bg-amber-500 ring-2 ring-amber-200'
                                      : tpl.agent_config
                                        ? 'bg-emerald-500'
                                        : 'bg-subtle'
                                  }`}
                                  aria-hidden="true"
                                  title={
                                    isTplDirty
                                      ? 'Has unsaved changes'
                                      : tpl.agent_config
                                        ? 'Configuration saved'
                                        : 'Not yet configured'
                                  }
                                />
                                <span
                                  className={`min-w-0 flex-1 truncate text-sm ${
                                    isActive ? 'font-semibold text-app-accent-text' : 'text-text-secondary'
                                  }`}
                                >
                                  {tpl.name}
                                </span>
                                {rolePill && (
                                  <span
                                    className={`shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${rolePill.cls}`}
                                  >
                                    {rolePill.label}
                                  </span>
                                )}
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setTemplateDeleteConfirm({
                                    isOpen: true,
                                    templateId: tpl.id,
                                    templateName: tpl.name,
                                    conflictParents: null,
                                  });
                                }}
                                className="absolute right-1.5 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-subtle opacity-0 transition hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 focus:opacity-100"
                                aria-label={`Delete ${tpl.name}`}
                                title="Delete template"
                              >
                                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M10 7V4a1 1 0 011-1h2a1 1 0 011 1v3" />
                                </svg>
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            {!isStudioRoute && (
            <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg">
                <div
                  ref={casesScrollRef}
                  className="hide-scrollbar min-h-0 flex-1 overflow-y-auto pl-2 pr-1"
                >
                  {studioIsLoadingCases && studioCases.length === 0 ? (
                    <div className="space-y-4 px-1 py-2" aria-busy="true" aria-label="Loading cases">
                      {[0, 1, 2, 3].map((i) => (
                        <div key={i} className="space-y-2 px-2">
                          <span className="block h-3 w-[85%] animate-pulse rounded bg-border" />
                          <span className="block h-3 w-[55%] animate-pulse rounded bg-border" />
                        </div>
                      ))}
                    </div>
                  ) : studioCases.length === 0 && !(pendingNewCase && isCaseRoute) ? (
                    <div className="px-2 py-4 text-center text-subtle text-sm">
                      <p>No cases yet</p>
                      <p className="text-xs mt-1">Click + New Case to upload a petition</p>
                    </div>
                  ) : (
                    <div className="space-y-0.5">
                      {pendingNewCase && isCaseRoute && (
                        <div
                          className={`group relative w-full rounded-lg border border-dashed border-app-accent-soft px-3 py-2 transition-colors ${
                            studioSelectedCaseId === pendingNewCase.id
                              ? 'bg-app-accent-soft'
                              : 'bg-surface-muted/40 hover:bg-surface-muted'
                          }`}
                        >
                          <button
                            type="button"
                            onClick={() => navigate('/case/new')}
                            className="flex w-full items-center gap-2 text-left"
                          >
                            <div className="flex min-w-0 flex-1 flex-col">
                              <span className="truncate text-sm italic text-app-accent-text">
                                Untitled
                              </span>
                              <span className="flex items-center gap-1.5 truncate text-[11px] text-muted">
                                {pendingNewCase.isUploading && (
                                  <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border border-app-accent-text border-t-transparent" />
                                )}
                                {pendingNewCase.isUploading
                                  ? 'Uploading petition…'
                                  : 'Awaiting petition'}
                              </span>
                            </div>
                            <span
                              role="button"
                              tabIndex={0}
                              aria-label="Cancel new case"
                              title="Cancel new case"
                              onClick={(e) => {
                                e.stopPropagation();
                                cancelNewCase();
                                navigate('/');
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  cancelNewCase();
                                  navigate('/');
                                }
                              }}
                              className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-subtle transition-colors hover:bg-surface hover:text-text-secondary ${
                                pendingNewCase.isUploading ? 'pointer-events-none opacity-30' : ''
                              }`}
                            >
                              <svg
                                className="h-3 w-3"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth={2}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                aria-hidden="true"
                              >
                                <path d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </span>
                          </button>
                        </div>
                      )}
                      {filteredStudioCases.length === 0 && (
                        <div className="px-2 py-4 text-center text-xs text-subtle">
                          No cases match “{studioSearchQuery}”.
                        </div>
                      )}
                      {filteredStudioCases.map((c) => {
                        const isPrimaryCase = studioSelectedCaseId === c.id;
                        const isSecondaryCase =
                          !isPrimaryCase && splitSecondaryCaseId === c.id;
                        // Both panes are "selected" visually; the
                        // checkmark differentiates which pane the user
                        // is currently focused on.
                        const isSelectedInAnyPane = isPrimaryCase || isSecondaryCase;
                        const isFocusedPaneCase =
                          (isPrimaryCase && splitFocusedPane === 'primary') ||
                          (isSecondaryCase && splitFocusedPane === 'secondary');
                        const isCaseStreaming = streamingCaseSet.has(c.id);
                        // Streaming wins over unread (more actionable
                        // signal). A selected case can't be unread —
                        // selection synchronously clears it via the
                        // studio/split-store subscriptions on
                        // useCaseChatStore.
                        const showUnread =
                          unreadCaseSet.has(c.id) &&
                          !isCaseStreaming &&
                          !isSelectedInAnyPane;
                        const displayName = formatCaseName(c.case_name);
                        const ariaLabel = [
                          `${displayName}, case ${c.case_number}`,
                          isCaseStreaming ? 'AI working' : null,
                          showUnread ? 'new activity' : null,
                        ]
                          .filter(Boolean)
                          .join(', ');
                        return (
                          <div
                            key={c.id}
                            className={`relative ${
                              isCaseStreaming ? 'case-stream-glow rounded-lg' : ''
                            }`}
                          >
                            {/* Selection bar — sits OUTSIDE the row to the
                                left so the row itself stays the visual
                                anchor (mirrors the collapsed-tile pattern). */}
                            {isSelectedInAnyPane && (
                              <span
                                aria-hidden="true"
                                className={`absolute -left-2 inset-y-1 w-1 rounded-full bg-indigo-500 ${
                                  isFocusedPaneCase ? '' : 'opacity-50'
                                }`}
                              />
                            )}
                            {/* Running-stripe halo while streaming. The
                                SVG paints as the LAST DOM child of this
                                wrapper (after the button) so the stroke
                                renders over the row content. */}
                            {isCaseStreaming && (
                              <span
                                aria-hidden="true"
                                className="pointer-events-none absolute inset-0 hidden rounded-lg ring-2 ring-indigo-500/60 motion-reduce:block"
                              />
                            )}
                          <button
                            type="button"
                            aria-label={ariaLabel}
                            aria-current={isPrimaryCase ? 'true' : undefined}
                            // Drag stays enabled during search so the user can
                            // still drag a filtered case into the workspace to
                            // open it in a split pane. Reorder is suppressed
                            // below — re-ordering inside a filtered list would
                            // mis-position relative to the underlying order.
                            draggable
                            onClick={() => handleCaseRowClick(c.id)}
                            onDragStart={(e) => {
                              setDraggedCaseId(c.id);
                              e.dataTransfer.effectAllowed = 'move';
                              e.dataTransfer.setData('text/plain', c.id);
                            }}
                            onDragOver={(e) => {
                              if (normalizedStudioSearchQuery) return;
                              if (!draggedCaseId || draggedCaseId === c.id) return;
                              e.preventDefault();
                              e.dataTransfer.dropEffect = 'move';
                              const rect = e.currentTarget.getBoundingClientRect();
                              const position =
                                e.clientY > rect.top + rect.height / 2 ? 'after' : 'before';
                              setCaseDropTarget((prev) =>
                                prev?.id === c.id && prev.position === position
                                  ? prev
                                  : { id: c.id, position },
                              );
                            }}
                            onDrop={(e) => {
                              e.preventDefault();
                              if (
                                !normalizedStudioSearchQuery &&
                                draggedCaseId &&
                                caseDropTarget
                              ) {
                                studioReorderCases(
                                  draggedCaseId,
                                  caseDropTarget.id,
                                  caseDropTarget.position,
                                );
                              }
                              setDraggedCaseId(null);
                              setCaseDropTarget(null);
                            }}
                            onDragEnd={() => {
                              setDraggedCaseId(null);
                              setCaseDropTarget(null);
                            }}
                            onMouseEnter={(e) =>
                              setHoveredCasePreview({
                                caseId: c.id,
                                caseName: formatCaseName(c.case_name),
                                caseNumber: c.case_number,
                                rect: e.currentTarget.getBoundingClientRect(),
                              })
                            }
                            onMouseLeave={() =>
                              setHoveredCasePreview((prev) =>
                                prev?.caseId === c.id ? null : prev,
                              )
                            }
                            className={`group relative w-full px-3 py-2 rounded-lg cursor-pointer transition-colors duration-150 text-left ${
                              isSelectedInAnyPane
                                ? 'bg-app-accent-soft shadow-sm ring-1 ring-inset ring-app-accent/45'
                                : 'hover:bg-surface-muted'
                            } ${draggedCaseId === c.id ? 'opacity-50' : ''}`}
                          >
                            {caseDropTarget?.id === c.id && (
                              <span
                                aria-hidden="true"
                                className={`absolute inset-x-2 h-0.5 rounded-full bg-app-accent ${
                                  caseDropTarget.position === 'before' ? 'top-0' : 'bottom-0'
                                }`}
                              />
                            )}
                            <div className="flex items-center gap-2">
                              <div className="flex min-w-0 flex-1 flex-col">
                                <span
                                  className={`text-sm truncate ${
                                    isSelectedInAnyPane
                                      ? 'text-app-accent-text font-semibold'
                                      : showUnread
                                        ? 'text-text font-semibold'
                                        : 'text-text-secondary'
                                  }`}
                                >
                                  {formatCaseName(c.case_name)}
                                </span>
                                <span className="truncate text-[11px] text-muted">
                                  {c.case_number}
                                </span>
                              </div>
                              {/* Trailing accessory hierarchy:
                                  streaming spinner > unread amber dot >
                                  focused-pane checkmark. Mutually
                                  exclusive: streaming wins over unread
                                  by construction (showUnread is gated
                                  on !isCaseStreaming), and a selected
                                  case can't be unread. */}
                              {isCaseStreaming ? (
                                <LuLoader
                                  aria-hidden="true"
                                  className="h-3.5 w-3.5 shrink-0 text-indigo-500 motion-safe:animate-spin"
                                />
                              ) : showUnread ? (
                                <span
                                  aria-hidden="true"
                                  className="h-2.5 w-2.5 shrink-0 rounded-full bg-amber-500 ring-2 ring-surface"
                                />
                              ) : (
                                isFocusedPaneCase && (
                                  <svg
                                    aria-hidden="true"
                                    className="h-3.5 w-3.5 shrink-0 text-app-accent-text"
                                    viewBox="0 0 20 20"
                                    fill="currentColor"
                                  >
                                    <path d="M7.629 13.065 4.4 9.836a.75.75 0 1 1 1.06-1.06l2.169 2.168 6.911-6.91a.75.75 0 0 1 1.06 1.06l-7.441 7.44a.75.75 0 0 1-1.06 0Z" />
                                  </svg>
                                )
                              )}
                            </div>
                          </button>
                          {isCaseStreaming && (
                            <StreamingBorderHalo
                              rx={8}
                              uniqueId={`row-${c.id}`}
                            />
                          )}
                          </div>
                        );
                      })}
                      {studioCasesHasMore && !normalizedStudioSearchQuery && (
                        <button
                          type="button"
                          onClick={() => void studioLoadMoreCases()}
                          disabled={studioIsLoadingMoreCases}
                          aria-label={
                            studioIsLoadingMoreCases
                              ? 'Loading more cases'
                              : `Load more cases (showing ${studioCases.length})`
                          }
                          className="mt-3 mb-4 flex w-full items-center justify-center gap-2 rounded-md bg-app-accent-soft px-3 py-2 text-xs font-semibold text-app-accent-text shadow-sm ring-1 ring-inset ring-app-accent/20 transition-colors hover:bg-app-accent hover:text-white hover:ring-app-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent focus-visible:ring-offset-1 disabled:cursor-wait disabled:opacity-70"
                        >
                          {studioIsLoadingMoreCases ? (
                            <>
                              <svg
                                className="h-3.5 w-3.5 animate-spin"
                                viewBox="0 0 24 24"
                                fill="none"
                                aria-hidden="true"
                              >
                                <circle
                                  cx="12"
                                  cy="12"
                                  r="9"
                                  stroke="currentColor"
                                  strokeWidth="2.5"
                                  strokeLinecap="round"
                                  strokeDasharray="40 60"
                                />
                              </svg>
                              <span>Loading more</span>
                            </>
                          ) : (
                            <>
                              <span>Load more cases</span>
                              <span className="rounded-full bg-white/60 px-1.5 py-0.5 text-[10px] font-semibold text-app-accent-text dark:bg-white/10">
                                {studioCases.length}+
                              </span>
                              <svg
                                className="h-3.5 w-3.5"
                                viewBox="0 0 20 20"
                                fill="currentColor"
                                aria-hidden="true"
                              >
                                <path
                                  fillRule="evenodd"
                                  d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.06l3.71-3.83a.75.75 0 1 1 1.08 1.04l-4.25 4.39a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z"
                                  clipRule="evenodd"
                                />
                              </svg>
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  )}
                </div>
            </section>
            )}
          </div>
        </div>
      </div>

      <style>{`
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
      `}</style>

      <SidebarFooterUserMenu isCollapsed={false} />

      <DeleteConfirmModal
        isOpen={templateDeleteConfirm.isOpen}
        title={
          templateDeleteConfirm.conflictParents
            ? 'Template Is Used By Other Templates'
            : 'Delete Template'
        }
        message={
          templateDeleteConfirm.conflictParents
            ? `"${templateDeleteConfirm.templateName ?? 'This template'}" is referenced by ${templateDeleteConfirm.conflictParents.length} parent template${templateDeleteConfirm.conflictParents.length === 1 ? '' : 's'}:`
            : `Are you sure you want to delete "${templateDeleteConfirm.templateName ?? 'this template'}"? This action cannot be undone.`
        }
        detail={
          templateDeleteConfirm.conflictParents && (
            <>
              <ul className="max-h-48 overflow-y-auto rounded-md ring-1 ring-border divide-y divide-border bg-surface-muted">
                {templateDeleteConfirm.conflictParents.map((p) => (
                  <li key={p.template_id} className="px-3 py-2">
                    <div className="text-sm font-medium text-text break-words">{p.name}</div>
                    {p.companion_labels.length > 0 && (
                      <div className="mt-0.5 text-xs text-subtle break-words">
                        {p.companion_labels.join(', ')}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-app-danger-text">
                Force delete will remove this template from those parents&apos; bundle companions and then delete it. This action cannot be undone.
              </p>
            </>
          )
        }
        confirmText={
          templateDeleteConfirm.conflictParents
            ? `Force delete (clean ${templateDeleteConfirm.conflictParents.length} parent${templateDeleteConfirm.conflictParents.length === 1 ? '' : 's'})`
            : 'Delete'
        }
        cancelText="Cancel"
        onConfirm={handleConfirmDeleteTemplate}
        onCancel={() => setTemplateDeleteConfirm({
          isOpen: false, templateId: null, templateName: null, conflictParents: null,
        })}
        variant="danger"
        isProcessing={isDeletingTemplate}
      />

      {hoveredTemplatePreview &&
        createPortal(
          (() => {
            const GAP = 8;
            const PREVIEW_MAX_WIDTH = 360;
            // Position to the right of the hovered row, top-aligned. Falls
            // back to placing it leftward when the right edge would clip
            // beyond the viewport (e.g. small browser window).
            const top = hoveredTemplatePreview.rect.top;
            const rightEdge =
              hoveredTemplatePreview.rect.right + GAP + PREVIEW_MAX_WIDTH;
            const overflowsRight =
              typeof window !== 'undefined' && rightEdge > window.innerWidth;
            const left = overflowsRight
              ? Math.max(GAP, hoveredTemplatePreview.rect.left - PREVIEW_MAX_WIDTH - GAP)
              : hoveredTemplatePreview.rect.right + GAP;
            const pill =
              hoveredTemplatePreview.role === 'parent'
                ? { label: 'Parent', cls: 'bg-app-accent-soft text-app-accent-text' }
                : hoveredTemplatePreview.role === 'child_only'
                  ? { label: 'Child', cls: 'bg-app-warning-soft text-amber-800' }
                  : null;
            return (
              <div
                role="tooltip"
                aria-hidden="true"
                style={{
                  position: 'fixed',
                  top,
                  left,
                  maxWidth: PREVIEW_MAX_WIDTH,
                  zIndex: 60,
                }}
                className="pointer-events-none flex items-start gap-2 rounded-lg border border-app-accent-soft bg-surface px-3 py-2 shadow-xl ring-1 ring-black/10"
              >
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    hoveredTemplatePreview.isDirty
                      ? 'bg-amber-500 ring-2 ring-amber-200'
                      : hoveredTemplatePreview.hasAgentConfig
                        ? 'bg-emerald-500'
                        : 'bg-subtle'
                  }`}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 break-words text-sm font-medium text-text-secondary">
                  {hoveredTemplatePreview.name}
                </span>
                {hoveredTemplatePreview.isDirty && (
                  <span className="mt-0.5 shrink-0 rounded-full bg-app-warning-soft px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-800">
                    Unsaved
                  </span>
                )}
                {pill && (
                  <span
                    className={`mt-0.5 shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${pill.cls}`}
                  >
                    {pill.label}
                  </span>
                )}
              </div>
            );
          })(),
          document.body,
        )}

      {casePreviewPortal}
    </div>
  );
};

export const ChatSidebar = React.memo(ChatSidebarImpl);
