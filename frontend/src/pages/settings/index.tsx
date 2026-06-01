import React from 'react';
import { Navigate, NavLink, useLocation } from 'react-router-dom';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import { useAuthSession } from '@/features/auth/queries';
import { hasPermission } from '@/features/auth/permissions';
import { MembersTab, ProfileTab, SecurityTab, UsageLimitsTab } from '@/features/settings/components';
import { SETTINGS_TABS } from '@/features/settings/settings.constants';
import type { SettingsTab } from '@/features/settings/types';

const getActiveSettingsTab = (pathname: string): SettingsTab => {
  if (pathname.startsWith('/settings/members')) return 'members';
  if (pathname.startsWith('/settings/usage')) return 'usage';
  if (pathname.startsWith('/settings/security')) return 'security';
  return 'profile';
};

export const SettingsPage: React.FC = () => {
  const location = useLocation();
  const { user } = useAuthSession();
  const activeTab = getActiveSettingsTab(location.pathname);
  const visibleTabs = SETTINGS_TABS.filter(
    (tab) => !tab.permission || hasPermission(user, tab.permission)
  );
  const activeTabConfig = SETTINGS_TABS.find((tab) => tab.id === activeTab);
  const canViewActiveTab =
    activeTabConfig && (!activeTabConfig.permission || hasPermission(user, activeTabConfig.permission));

  if (!canViewActiveTab) {
    const fallbackTab = visibleTabs[0];
    return fallbackTab ? <Navigate to={fallbackTab.to} replace /> : <Navigate to="/unauthorized" replace />;
  }

  const content = (() => {
    if (activeTab === 'members') return <MembersTab />;
    if (activeTab === 'usage') return <UsageLimitsTab />;
    if (activeTab === 'security') return <SecurityTab />;
    return <ProfileTab />;
  })();

  return (
    <SidebarLayout sidebarVariant="app" className="bg-page" contentClassName="overflow-y-auto">
      <div className="mx-auto w-full max-w-[1400px] px-6 py-8 pb-16 xl:px-8">
        <header className="mb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h1 className="font-poppins text-2xl font-semibold text-app-accent-text">Settings</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
                Manage firm profile, members, and usage controls.
              </p>
            </div>
          </div>

          <nav className="mt-6 flex gap-2 overflow-x-auto border-b border-border">
            {visibleTabs.map((tab) => (
              <NavLink
                key={tab.id}
                to={tab.to}
                end={tab.id === 'profile'}
                className={`whitespace-nowrap border-b-2 px-3 py-3 text-sm font-semibold transition ${
                  activeTab === tab.id
                    ? 'border-app-accent text-app-accent-text'
                    : 'border-transparent text-muted hover:text-text-secondary'
                }`}
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </header>

        {content}
      </div>
    </SidebarLayout>
  );
};
