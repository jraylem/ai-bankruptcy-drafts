import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { FiActivity, FiBarChart2, FiFileText, FiHome, FiTrendingUp, FiUsers } from 'react-icons/fi';
import { SidebarBrand } from './SidebarBrand';
import { SidebarFooterUserMenu } from './SidebarFooterUserMenu';

interface AnalyticsSidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

type AnalyticsNavItem = {
  key: string;
  label: string;
  to?: string;
  icon: React.ReactNode;
  comingSoon?: boolean;
};

interface CollapsedNavTooltipState {
  label: string;
  top: number;
  left: number;
  comingSoon?: boolean;
}

const NAV_ITEMS: AnalyticsNavItem[] = [
  {
    key: 'home',
    label: 'Home',
    to: '/',
    icon: <FiHome className="h-4 w-4" />,
  },
  {
    key: 'overview',
    label: 'Overview',
    to: '/analytics',
    icon: <FiBarChart2 className="h-4 w-4" />,
  },
  {
    key: 'users',
    label: 'Users',
    to: '/analytics/users',
    icon: <FiUsers className="h-4 w-4" />,
  },
  {
    key: 'cases',
    label: 'Cases',
    to: '/analytics/cases',
    icon: <FiFileText className="h-4 w-4" />,
  },
  {
    key: 'motions',
    label: 'Motions',
    to: '/analytics/motions',
    icon: <FiTrendingUp className="h-4 w-4" />,
  },
  {
    key: 'activity',
    label: 'Activity Log',
    to: '/analytics/activity-log',
    icon: <FiActivity className="h-4 w-4" />,
  },
];

const getIsItemActive = (pathname: string, item: AnalyticsNavItem) => {
  if (!item.to) return false;
  if (item.to === '/analytics') return pathname === '/analytics';
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
};

export const AnalyticsSidebar: React.FC<AnalyticsSidebarProps> = ({
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const location = useLocation();
  const [collapsedTooltip, setCollapsedTooltip] = useState<CollapsedNavTooltipState | null>(null);

  const showCollapsedTooltip = (
    event: React.MouseEvent<HTMLElement> | React.FocusEvent<HTMLElement>,
    label: string,
    options?: {
      comingSoon?: boolean;
    }
  ) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setCollapsedTooltip({
      label,
      comingSoon: options?.comingSoon,
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

              if (item.to) {
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
              }

              return (
                <button
                  key={item.key}
                  type="button"
                  disabled
                  title={`${item.label} (Coming soon)`}
                  className="flex items-center justify-center"
                  onMouseEnter={(event) =>
                    showCollapsedTooltip(event, item.label, { comingSoon: true })
                  }
                  onMouseLeave={hideCollapsedTooltip}
                >
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-surface text-subtle opacity-60">
                    {item.icon}
                  </div>
                </button>
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
            {collapsedTooltip.comingSoon ? (
              <div className="mt-2 inline-flex items-center rounded-full bg-app-warning-soft px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-app-warning-text">
                Coming soon
              </div>
            ) : null}
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
            Analytics
          </div>

          {NAV_ITEMS.map((item) => {
            const isActive = getIsItemActive(location.pathname, item);

            if (item.to) {
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
            }

            return (
              <button
                key={item.key}
                type="button"
                disabled
                className="flex w-full cursor-not-allowed items-center justify-between rounded-lg px-3 py-2 text-sm text-subtle opacity-65"
              >
                <span className="flex items-center gap-2.5">
                  {item.icon}
                  <span className="font-medium">{item.label}</span>
                </span>
                {item.comingSoon ? (
                  <span className="rounded-full bg-app-warning-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-app-warning-text">
                    Soon
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>

      <SidebarFooterUserMenu isCollapsed={false} />
    </div>
  );
};
