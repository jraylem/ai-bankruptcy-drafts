import React, { useEffect, useState } from 'react';
import { LuRefreshCw } from 'react-icons/lu';

import { SidebarLayout } from '@/components/layout/SidebarLayout';
import type { CostRange } from '@/types/costs';

import { formatRelative } from './formatting';

interface CostCenterLayoutProps {
  children: React.ReactNode;
  range: CostRange;
  onRangeChange: (next: CostRange) => void;
  lastUpdatedAt: number | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export const CostCenterLayout: React.FC<CostCenterLayoutProps> = ({
  children,
  range,
  onRangeChange,
  lastUpdatedAt,
  isLoading,
  onRefresh,
}) => (
  <SidebarLayout
    sidebarVariant="app"
    className="bg-page"
    contentClassName="overflow-y-auto"
  >
    <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
      <CostCenterHeader
        range={range}
        onRangeChange={onRangeChange}
        lastUpdatedAt={lastUpdatedAt}
        isLoading={isLoading}
        onRefresh={onRefresh}
      />
      {children}
    </div>
  </SidebarLayout>
);

interface CostCenterHeaderProps {
  range: CostRange;
  onRangeChange: (next: CostRange) => void;
  lastUpdatedAt: number | null;
  isLoading: boolean;
  onRefresh: () => void;
}

const CostCenterHeader: React.FC<CostCenterHeaderProps> = ({
  range,
  onRangeChange,
  lastUpdatedAt,
  isLoading,
  onRefresh,
}) => (
  <header className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
    <div>
      <h1 className="text-2xl font-semibold text-text-secondary">Cost Center</h1>
      <p className="mt-1 text-sm text-muted">
        Token and compute spend across your firm's drafting workload.
      </p>
    </div>
    <div className="flex flex-col items-start gap-2 lg:items-end">
      <CostRangeToggle range={range} onChange={onRangeChange} />
      <RefreshLine
        isLoading={isLoading}
        lastUpdatedAt={lastUpdatedAt}
        onRefresh={onRefresh}
      />
    </div>
  </header>
);

interface CostRangeToggleProps {
  range: CostRange;
  onChange: (next: CostRange) => void;
}

const CostRangeToggle: React.FC<CostRangeToggleProps> = ({ range, onChange }) => (
  <div
    role="tablist"
    aria-label="Cost range"
    className="inline-flex rounded-md border border-border bg-surface p-0.5"
  >
    {(['week', 'month'] as const).map((r) => {
      const isActive = range === r;
      return (
        <button
          key={r}
          type="button"
          role="tab"
          aria-selected={isActive}
          onClick={() => onChange(r)}
          className={`rounded px-4 py-1.5 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent ${
            isActive
              ? 'bg-app-accent-soft text-app-accent-text shadow-sm'
              : 'text-text-secondary hover:text-app-accent-text'
          }`}
        >
          {r === 'week' ? 'Week' : 'Month'}
        </button>
      );
    })}
  </div>
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
  // Tick every 30s so "Xm ago" stays current without spamming re-renders.
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
