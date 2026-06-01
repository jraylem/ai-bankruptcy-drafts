import React from 'react';
import { SkeletonBlock } from '@/features/analytics/components/AnalyticsSkeleton';

export const UserDetailPageSkeleton: React.FC = () => (
  <div className="space-y-6">
    <section className="rounded-2xl bg-surface p-6">
      <div className="mb-6 flex items-start justify-between gap-6">
        <div className="min-w-0 space-y-2">
          <SkeletonBlock className="h-8 w-56" />
          <SkeletonBlock className="h-4 w-72" />
        </div>
        <div className="space-y-2">
          <SkeletonBlock className="h-4 w-36" />
          <SkeletonBlock className="h-4 w-32" />
          <SkeletonBlock className="h-8 w-28" />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={`primary-kpi-skeleton-${index}`} className="rounded-2xl bg-surface-muted/40 p-4">
            <SkeletonBlock className="h-3 w-28" />
            <SkeletonBlock className="mt-3 h-8 w-16" />
          </div>
        ))}
      </div>
    </section>

    <section className="grid gap-6 xl:grid-cols-2">
      {Array.from({ length: 2 }).map((_, index) => (
        <div key={`chart-skeleton-${index}`} className="rounded-2xl bg-surface p-6">
          <div className="mb-6 flex items-center justify-between">
            <SkeletonBlock className="h-6 w-48" />
            <SkeletonBlock className="h-4 w-32" />
          </div>
          <SkeletonBlock className="h-60 w-full" />
        </div>
      ))}
    </section>

    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={`secondary-kpi-skeleton-${index}`} className="rounded-2xl bg-surface p-6">
          <SkeletonBlock className="h-4 w-24" />
          <SkeletonBlock className="mt-4 h-8 w-16" />
          <SkeletonBlock className="mt-2 h-3 w-32" />
        </div>
      ))}
    </section>

    <section className="rounded-2xl bg-surface p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <SkeletonBlock className="h-6 w-40" />
        <div className="flex items-center gap-2">
          <SkeletonBlock className="h-10 w-72" />
          <SkeletonBlock className="h-10 w-32" />
          <SkeletonBlock className="h-10 w-36" />
        </div>
      </div>
      <SkeletonBlock className="h-56 w-full" />
      <div className="mt-3 flex items-center justify-between">
        <SkeletonBlock className="h-4 w-32" />
        <SkeletonBlock className="h-8 w-56" />
      </div>
    </section>

    <section className="rounded-2xl bg-surface p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <SkeletonBlock className="h-6 w-36" />
        <div className="flex items-center gap-2">
          <SkeletonBlock className="h-10 w-72" />
          <SkeletonBlock className="h-10 w-32" />
          <SkeletonBlock className="h-10 w-32" />
        </div>
      </div>
      <SkeletonBlock className="h-56 w-full" />
      <div className="mt-3 flex items-center justify-between">
        <SkeletonBlock className="h-4 w-32" />
        <SkeletonBlock className="h-8 w-56" />
      </div>
    </section>
  </div>
);
