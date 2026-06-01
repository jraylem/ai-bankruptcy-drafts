import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { LuArchive, LuHouse, LuInbox } from 'react-icons/lu';

import { useCaseInbox } from '@/features/case-inbox/useCaseInbox';

import { SidebarBrand } from './SidebarBrand';
import { SidebarFooterUserMenu } from './SidebarFooterUserMenu';

interface CaseInboxSidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

type CaseInboxNavItem = {
  key: string;
  label: string;
  to: string;
  icon: React.ReactNode;
  /** Optional numeric badge — used for the pending-count on the Inbox item. */
  badge?: number | null;
};

interface CollapsedNavTooltipState {
  label: string;
  top: number;
  left: number;
  badge?: number | null;
}

const getIsItemActive = (pathname: string, to: string) => {
  if (to === '/') {
    // Home tile points at root, which now resolves to the case workspace.
    // Treat any /case/* path AND the bare / as active.
    return pathname === '/' || pathname.startsWith('/case');
  }
  if (to === '/inbox') {
    return pathname === '/inbox';
  }
  if (to === '/inbox/archived') {
    return pathname === '/inbox/archived';
  }
  return pathname === to;
};

/** Format the pending-count badge: 99+ cap per architect. */
const renderBadgeText = (n: number | null | undefined): string | null => {
  if (n == null || n <= 0) return null;
  return n > 99 ? '99+' : String(n);
};

export const CaseInboxSidebar: React.FC<CaseInboxSidebarProps> = ({
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const location = useLocation();
  const [collapsedTooltip, setCollapsedTooltip] =
    useState<CollapsedNavTooltipState | null>(null);

  // Sidebar-level cache subscription — derives the pending count
  // client-side per architect's "no separate /count endpoint" call.
  const { pendingCount } = useCaseInbox();

  const navItems: CaseInboxNavItem[] = [
    {
      key: 'home',
      label: 'Home',
      to: '/',
      icon: <LuHouse className="h-4 w-4" />,
    },
    {
      key: 'inbox',
      label: 'Inbox',
      to: '/inbox',
      icon: <LuInbox className="h-4 w-4" />,
      badge: pendingCount,
    },
    {
      key: 'archived',
      label: 'Archived',
      to: '/inbox/archived',
      icon: <LuArchive className="h-4 w-4" />,
    },
  ];

  const showCollapsedTooltip = (
    event: React.MouseEvent<HTMLElement> | React.FocusEvent<HTMLElement>,
    item: CaseInboxNavItem,
  ) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setCollapsedTooltip({
      label: item.label,
      badge: item.badge ?? null,
      top: rect.top + rect.height / 2,
      left: rect.right + 12,
    });
  };

  const hideCollapsedTooltip = () => setCollapsedTooltip(null);

  if (isCollapsed) {
    return (
      <div
        className="flex h-full flex-col border-r border-border bg-surface text-text transition-all duration-300"
        style={{ width: '64px' }}
      >
        <SidebarBrand isCollapsed onToggleCollapse={onToggleCollapse} />

        <div
          className="min-h-0 flex-1 overflow-y-auto px-2 pb-3"
          style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
          onScroll={hideCollapsedTooltip}
        >
          <div className="mx-auto h-px w-8 bg-surface-muted" />
          <div className="mt-3 flex flex-col items-center gap-2">
            {navItems.map((item) => {
              const isActive = getIsItemActive(location.pathname, item.to);
              const badgeText = renderBadgeText(item.badge);
              return (
                <NavLink
                  key={item.key}
                  to={item.to}
                  title={item.label}
                  className="group relative flex items-center justify-center"
                  onMouseEnter={(event) => showCollapsedTooltip(event, item)}
                  onMouseLeave={hideCollapsedTooltip}
                  onFocus={(event) => showCollapsedTooltip(event, item)}
                  onBlur={hideCollapsedTooltip}
                >
                  <div
                    className={`relative flex h-9 w-9 items-center justify-center rounded-xl border transition-all duration-200 ${
                      isActive
                        ? 'border-option-selected-border bg-option-selected text-app-accent-text shadow-sm ring-1 ring-option-selected-ring'
                        : 'border-border bg-surface text-muted shadow-sm hover:border-app-accent/50 hover:text-app-accent-text hover:shadow-md'
                    }`}
                  >
                    {item.icon}
                    {badgeText && (
                      <span className="absolute -right-1 -top-1 inline-flex min-w-[18px] items-center justify-center rounded-full bg-app-accent px-1 text-[10px] font-semibold text-white shadow">
                        {badgeText}
                      </span>
                    )}
                  </div>
                </NavLink>
              );
            })}
          </div>
        </div>

        {collapsedTooltip && (
          <div
            className="pointer-events-none fixed z-40 w-max -translate-y-1/2 rounded-xl border border-border bg-surface px-3 py-2 text-left shadow-xl"
            style={{
              top: `${collapsedTooltip.top}px`,
              left: `${collapsedTooltip.left}px`,
            }}
          >
            <p className="text-sm font-semibold leading-5 text-text">{collapsedTooltip.label}</p>
            {renderBadgeText(collapsedTooltip.badge) && (
              <p className="mt-0.5 text-xs text-muted">
                {renderBadgeText(collapsedTooltip.badge)} pending
              </p>
            )}
          </div>
        )}

        <SidebarFooterUserMenu isCollapsed />
      </div>
    );
  }

  return (
    <div
      className="flex h-full flex-col border-r border-border bg-surface text-text transition-all duration-300"
      style={{ width: '256px' }}
    >
      <SidebarBrand isCollapsed={false} onToggleCollapse={onToggleCollapse} />

      <div
        className="min-h-0 flex-1 overflow-y-auto p-3"
        style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
      >
        <div className="space-y-2">
          <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-wider text-muted">
            Case Inbox
          </div>

          {navItems.map((item) => {
            const isActive = getIsItemActive(location.pathname, item.to);
            const badgeText = renderBadgeText(item.badge);
            return (
              <NavLink
                key={item.key}
                to={item.to}
                className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors duration-150 ${
                  isActive
                    ? 'border border-option-selected-border bg-option-selected text-text shadow-sm ring-1 ring-option-selected-ring'
                    : 'text-text-secondary hover:bg-surface-muted'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  {item.icon}
                  <span className="font-medium">{item.label}</span>
                </span>
                {badgeText && (
                  <span className="inline-flex min-w-[20px] items-center justify-center rounded-full bg-app-accent px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    {badgeText}
                  </span>
                )}
              </NavLink>
            );
          })}
        </div>
      </div>

      <SidebarFooterUserMenu isCollapsed={false} />
    </div>
  );
};
