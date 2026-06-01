import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { LuHouse, LuLayoutDashboard } from 'react-icons/lu';
import { SidebarBrand } from './SidebarBrand';
import { SidebarFooterUserMenu } from './SidebarFooterUserMenu';

interface CostCenterSidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

type CostCenterNavItem = {
  key: string;
  label: string;
  to: string;
  icon: React.ReactNode;
};

interface CollapsedNavTooltipState {
  label: string;
  top: number;
  left: number;
}

const NAV_ITEMS: CostCenterNavItem[] = [
  {
    key: 'home',
    label: 'Home',
    to: '/',
    icon: <LuHouse className="h-4 w-4" />,
  },
  {
    key: 'overview',
    label: 'Overview',
    to: '/cost-center',
    icon: <LuLayoutDashboard className="h-4 w-4" />,
  },
];

const getIsItemActive = (pathname: string, item: CostCenterNavItem) => {
  if (item.to === '/cost-center') return pathname === '/cost-center';
  if (item.to === '/') {
    return pathname === '/' || pathname.startsWith('/case');
  }
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
};

export const CostCenterSidebar: React.FC<CostCenterSidebarProps> = ({
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const location = useLocation();
  const [collapsedTooltip, setCollapsedTooltip] = useState<CollapsedNavTooltipState | null>(null);

  const showCollapsedTooltip = (
    event: React.MouseEvent<HTMLElement> | React.FocusEvent<HTMLElement>,
    label: string
  ) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setCollapsedTooltip({
      label,
      top: rect.top + rect.height / 2,
      left: rect.right + 12,
    });
  };

  const hideCollapsedTooltip = () => {
    setCollapsedTooltip(null);
  };

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
            {NAV_ITEMS.map((item) => {
              const isActive = getIsItemActive(location.pathname, item);
              return (
                <NavLink
                  key={item.key}
                  to={item.to}
                  title={item.label}
                  className="group relative flex items-center justify-center"
                  onMouseEnter={(event) => showCollapsedTooltip(event, item.label)}
                  onMouseLeave={hideCollapsedTooltip}
                  onFocus={(event) => showCollapsedTooltip(event, item.label)}
                  onBlur={hideCollapsedTooltip}
                >
                  <div
                    className={`flex h-9 w-9 items-center justify-center rounded-xl border transition-all duration-200 ${
                      isActive
                        ? 'border-option-selected-border bg-option-selected text-app-accent-text shadow-sm ring-1 ring-option-selected-ring'
                        : 'border-border bg-surface text-muted shadow-sm hover:border-app-accent/50 hover:text-app-accent-text hover:shadow-md'
                    }`}
                  >
                    {item.icon}
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
            Cost Center
          </div>

          {NAV_ITEMS.map((item) => {
            const isActive = getIsItemActive(location.pathname, item);
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
              </NavLink>
            );
          })}
        </div>
      </div>

      <SidebarFooterUserMenu isCollapsed={false} />
    </div>
  );
};
