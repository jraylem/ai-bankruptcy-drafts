import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  FiActivity,
  FiArchive,
  FiBarChart2,
  FiChevronDown,
  FiCreditCard,
  FiFileText,
  FiFolder,
  FiInbox,
  FiPieChart,
  FiSettings,
  FiTrendingUp,
  FiUsers,
  FiZap,
} from 'react-icons/fi';
import { SidebarBrand } from './SidebarBrand';
import { SidebarFooterUserMenu } from './SidebarFooterUserMenu';
import { useAuthSession } from '@/features/auth/queries';
import { APP_PERMISSIONS, hasPermission, type AppPermission } from '@/features/auth/permissions';
import type { User } from '@/types';

interface AppSidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

type NavItem = {
  label: string;
  to: string;
  icon: React.ReactNode;
  end?: boolean;
  permission?: AppPermission;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

const ANALYTICS_DROPDOWN_STORAGE_KEY = 'app_sidebar_analytics_open';

const getInitialAnalyticsDropdownOpen = () => {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(ANALYTICS_DROPDOWN_STORAGE_KEY) === 'true';
};

const WORKSPACE_ITEMS: NavItem[] = [
  {
    label: 'Cases',
    to: '/',
    icon: <FiFolder className="h-4 w-4" />,
    end: true,
    permission: APP_PERMISSIONS.caseManagement,
  },
  {
    label: 'Case Inbox',
    to: '/inbox',
    icon: <FiInbox className="h-4 w-4" />,
    permission: APP_PERMISSIONS.caseManagement,
  },
  {
    label: 'Studio',
    to: '/studio',
    icon: <FiZap className="h-4 w-4" />,
    permission: APP_PERMISSIONS.motionStudio,
  },
];

const ANALYTICS_ITEMS: NavItem[] = [
  { label: 'Overview', to: '/analytics', icon: <FiBarChart2 className="h-4 w-4" />, end: true },
  { label: 'Users', to: '/analytics/users', icon: <FiUsers className="h-4 w-4" /> },
  { label: 'Cases', to: '/analytics/cases', icon: <FiFileText className="h-4 w-4" /> },
  { label: 'Motions', to: '/analytics/motions', icon: <FiTrendingUp className="h-4 w-4" /> },
  {
    label: 'Activity Log',
    to: '/analytics/activity-log',
    icon: <FiActivity className="h-4 w-4" />,
  },
];

const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Workspace',
    items: WORKSPACE_ITEMS,
  },
  {
    label: 'Insights',
    items: [
      {
        label: 'Cost Center',
        to: '/cost-center',
        icon: <FiArchive className="h-4 w-4" />,
        permission: APP_PERMISSIONS.adminDashboard,
      },
    ],
  },
  {
    label: 'Firm',
    items: [
      {
        label: 'Billing',
        to: '/billing',
        icon: <FiCreditCard className="h-4 w-4" />,
        permission: APP_PERMISSIONS.adminDashboard,
      },
      {
        label: 'Settings',
        to: '/settings',
        icon: <FiSettings className="h-4 w-4" />,
        permission: APP_PERMISSIONS.adminDashboard,
      },
    ],
  },
];

const isNavItemAllowed = (item: NavItem, user: User | null) =>
  !item.permission || hasPermission(user, item.permission);

const isActivePath = (pathname: string, item: NavItem) => {
  if (item.to === '/') return pathname === '/' || pathname.startsWith('/case/');
  if (item.end) return pathname === item.to;
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
};

const NavRow = ({ item, collapsed = false }: { item: NavItem; collapsed?: boolean }) => {
  const location = useLocation();
  const isActive = isActivePath(location.pathname, item);

  return (
    <NavLink
      to={item.to}
      aria-label={collapsed ? item.label : undefined}
      className={`group relative flex items-center gap-2.5 rounded-lg text-sm font-medium transition-colors ${
        collapsed
          ? `h-9 w-9 justify-center ${
              isActive
                ? 'bg-option-selected text-app-accent-text ring-1 ring-option-selected-ring'
                : 'text-muted hover:bg-surface-muted hover:text-text-secondary'
            }`
          : `px-3 py-2 ${
              isActive
                ? 'bg-option-selected text-app-accent-text ring-1 ring-option-selected-ring'
                : 'text-text-secondary hover:bg-surface-muted hover:text-text'
            }`
      }`}
    >
      {item.icon}
      {!collapsed ? <span>{item.label}</span> : null}
      {collapsed ? (
        <span className="pointer-events-none absolute left-[calc(100%+10px)] top-1/2 z-50 -translate-y-1/2 whitespace-nowrap rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-semibold text-text opacity-0 shadow-lg ring-1 ring-black/5 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
          {item.label}
        </span>
      ) : null}
    </NavLink>
  );
};

const Section = ({ section, user }: { section: NavSection; user: User | null }) => (
  <div className="space-y-1">
    <p className="px-3 pb-1 pt-4 text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
      {section.label}
    </p>
    {section.items
      .filter((item) => isNavItemAllowed(item, user))
      .map((item) => (
        <NavRow key={item.to} item={item} />
      ))}
  </div>
);

export const AppSidebar: React.FC<AppSidebarProps> = ({
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const { user } = useAuthSession();
  const location = useLocation();
  const [analyticsOpen, setAnalyticsOpen] = useState(getInitialAnalyticsDropdownOpen);
  const canViewAnalytics = hasPermission(user, APP_PERMISSIONS.analytics);
  const isAnalyticsActive =
    location.pathname === '/analytics' || location.pathname.startsWith('/analytics/');
  const showAnalyticsChildren = analyticsOpen;

  const toggleAnalyticsOpen = () => {
    setAnalyticsOpen((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(ANALYTICS_DROPDOWN_STORAGE_KEY, String(next));
      } catch {
        // Ignore localStorage errors.
      }
      return next;
    });
  };

  if (isCollapsed) {
    return (
      <div className="flex h-full flex-col border-r border-border bg-surface text-text">
        <SidebarBrand isCollapsed onToggleCollapse={onToggleCollapse} />
        <div className="min-h-0 flex-1 overflow-visible px-2 pb-3">
          <div className="mx-auto mb-3 h-px w-8 bg-surface-muted" />
          <div className="flex flex-col items-center gap-2">
            {[
              ...WORKSPACE_ITEMS,
              {
                label: 'Analytics',
                to: '/analytics',
                icon: <FiPieChart className="h-4 w-4" />,
                permission: APP_PERMISSIONS.analytics,
              },
              ...NAV_SECTIONS[1].items,
              ...NAV_SECTIONS[2].items,
            ]
              .filter((item) => isNavItemAllowed(item, user))
              .map((item) => (
                <NavRow key={`${item.label}-${item.to}`} item={item} collapsed />
              ))}
          </div>
        </div>
        <SidebarFooterUserMenu isCollapsed />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col border-r border-border bg-surface text-text">
      <SidebarBrand isCollapsed={false} onToggleCollapse={onToggleCollapse} />

      <nav className="min-h-0 flex-1 overflow-y-auto p-3">
        <Section section={NAV_SECTIONS[0]} user={user} />

        {canViewAnalytics || NAV_SECTIONS[1].items.some((item) => isNavItemAllowed(item, user)) ? (
          <div className="space-y-1">
            <p className="px-3 pb-1 pt-4 text-[11px] font-bold uppercase tracking-[0.16em] text-muted">
              Insights
            </p>
            {canViewAnalytics ? (
              <>
                <button
                  type="button"
                  onClick={toggleAnalyticsOpen}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isAnalyticsActive
                      ? 'bg-option-selected text-app-accent-text ring-1 ring-option-selected-ring'
                      : 'text-text-secondary hover:bg-surface-muted hover:text-text'
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <FiPieChart className="h-4 w-4" />
                    Analytics
                  </span>
                  <FiChevronDown
                    className={`h-4 w-4 transition-transform ${showAnalyticsChildren ? 'rotate-180' : ''}`}
                  />
                </button>
                {showAnalyticsChildren ? (
                  <div className="ml-4 space-y-1 border-l border-border pl-3">
                    {ANALYTICS_ITEMS.map((item) => (
                      <NavRow key={item.to} item={item} />
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
            {NAV_SECTIONS[1].items
              .filter((item) => isNavItemAllowed(item, user))
              .map((item) => (
                <NavRow key={item.to} item={item} />
              ))}
          </div>
        ) : null}

        <Section section={NAV_SECTIONS[2]} user={user} />
      </nav>

      <SidebarFooterUserMenu isCollapsed={false} />
    </div>
  );
};
