import React, { useEffect } from 'react';
import { AppSidebar } from '@/components/layout/AppSidebar';
import { ChatSidebar } from '@/components/chat/ChatSidebar';
import { AnalyticsSidebar } from '@/components/layout/AnalyticsSidebar';
import { CaseInboxSidebar } from '@/components/layout/CaseInboxSidebar';
import { CostCenterSidebar } from '@/components/layout/CostCenterSidebar';
import { useUIStore } from '@/stores/useUIStore';

interface SidebarLayoutProps {
  children: React.ReactNode;
  autoCollapseBreakpoint?: number;
  className?: string;
  contentClassName?: string;
  sidebarVariant?: 'chat' | 'app' | 'analytics' | 'cost-center' | 'case-inbox';
}

export const SidebarLayout: React.FC<SidebarLayoutProps> = ({
  children,
  autoCollapseBreakpoint = 1279,
  className = '',
  contentClassName = '',
  sidebarVariant = 'chat',
}) => {
  const { isSidebarCollapsed, toggleSidebar, setSidebarCollapsed } = useUIStore();

  useEffect(() => {
    const mediaQuery = window.matchMedia(`(max-width: ${autoCollapseBreakpoint}px)`);

    const handleMediaChange = (e: MediaQueryListEvent | MediaQueryList) => {
      if (e.matches) {
        setSidebarCollapsed(true);
      }
    };

    handleMediaChange(mediaQuery);
    mediaQuery.addEventListener('change', handleMediaChange);

    return () => mediaQuery.removeEventListener('change', handleMediaChange);
  }, [autoCollapseBreakpoint, setSidebarCollapsed]);

  const sidebarWidth = isSidebarCollapsed ? 64 : 256;
  const SidebarComponent =
    sidebarVariant === 'app'
      ? AppSidebar
      : sidebarVariant === 'analytics'
      ? AnalyticsSidebar
      : sidebarVariant === 'cost-center'
        ? CostCenterSidebar
        : sidebarVariant === 'case-inbox'
          ? CaseInboxSidebar
          : ChatSidebar;

  return (
    <main className={`flex h-full flex-1 overflow-hidden ${className}`}>
      <aside
        className="shrink-0 transition-all duration-300 ease-in-out"
        style={{ width: `${sidebarWidth}px` }}
      >
        <SidebarComponent isCollapsed={isSidebarCollapsed} onToggleCollapse={toggleSidebar} />
      </aside>

      <section className={`min-w-0 flex-1 ${contentClassName}`}>{children}</section>
    </main>
  );
};
