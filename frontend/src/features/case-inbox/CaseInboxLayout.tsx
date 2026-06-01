import React, { useEffect, useState } from 'react';
import { LuRefreshCw } from 'react-icons/lu';

import { SidebarLayout } from '@/components/layout/SidebarLayout';

import { formatRelative } from './formatting';

interface CaseInboxLayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle: string;
  /** Optional content rendered to the right of the title — e.g. a search input
   *  on the archived view. Header drops it on narrow viewports. */
  headerActions?: React.ReactNode;
  lastUpdatedAt: number | null;
  isLoading: boolean;
  onRefresh: () => void;
}

/**
 * Page chrome for `/inbox` and `/inbox/archived`. Matches the Cost Center
 * pattern: title + subtitle, refresh button, "Updated Xm ago" relative
 * timestamp. No 30s countdown — TanStack Query handles SWR background
 * refetches; the manual button is for explicit refreshes.
 */
export const CaseInboxLayout: React.FC<CaseInboxLayoutProps> = ({
  children,
  title,
  subtitle,
  headerActions,
  lastUpdatedAt,
  isLoading,
  onRefresh,
}) => (
  <SidebarLayout
    sidebarVariant="case-inbox"
    className="bg-page"
    contentClassName="overflow-y-auto"
  >
    <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
      <Header
        title={title}
        subtitle={subtitle}
        headerActions={headerActions}
        lastUpdatedAt={lastUpdatedAt}
        isLoading={isLoading}
        onRefresh={onRefresh}
      />
      {children}
    </div>
  </SidebarLayout>
);

interface HeaderProps {
  title: string;
  subtitle: string;
  headerActions?: React.ReactNode;
  lastUpdatedAt: number | null;
  isLoading: boolean;
  onRefresh: () => void;
}

const Header: React.FC<HeaderProps> = ({
  title,
  subtitle,
  headerActions,
  lastUpdatedAt,
  isLoading,
  onRefresh,
}) => (
  <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
    <div>
      <h1 className="text-2xl font-semibold text-text-secondary">{title}</h1>
      <p className="mt-1 text-sm text-muted">{subtitle}</p>
    </div>
    <div className="flex flex-col items-start gap-2 lg:items-end">
      {headerActions}
      <RefreshLine
        isLoading={isLoading}
        lastUpdatedAt={lastUpdatedAt}
        onRefresh={onRefresh}
      />
    </div>
  </header>
);

interface RefreshLineProps {
  isLoading: boolean;
  lastUpdatedAt: number | null;
  onRefresh: () => void;
}

const RefreshLine: React.FC<RefreshLineProps> = ({
  isLoading,
  lastUpdatedAt,
  onRefresh,
}) => {
  // Tick every 30s so "Xm ago" stays current without per-second re-renders.
  const [, force] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => force((n) => n + 1), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const label = lastUpdatedAt
    ? `Updated ${formatRelative(lastUpdatedAt)}`
    : isLoading
      ? 'Loading…'
      : '';

  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      {label && <span>{label}</span>}
      {label && <span aria-hidden="true">·</span>}
      <button
        type="button"
        onClick={onRefresh}
        disabled={isLoading}
        aria-label="Refresh"
        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-semibold text-text-secondary transition hover:text-app-accent-text disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
      >
        <LuRefreshCw
          className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`}
          aria-hidden="true"
        />
        Refresh
      </button>
    </div>
  );
};
