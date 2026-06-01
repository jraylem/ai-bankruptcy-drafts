import React from 'react';

export const SkeletonBlock: React.FC<{ className: string }> = ({ className }) => (
  <div className={`animate-pulse rounded-[18px] bg-border/70 ${className}`} />
);

export const AnalyticsBodySkeleton: React.FC<{ className?: string }> = ({ className = 'h-64' }) => (
  <SkeletonBlock className={`w-full ${className}`} />
);

export const InlineValueSkeleton: React.FC<{ className?: string }> = ({ className = 'h-8 w-20' }) => (
  <SkeletonBlock className={className} />
);

export const AnalyticsSectionSkeleton: React.FC<{
  titleWidth?: string;
  className?: string;
  bodyClassName?: string;
}> = ({ titleWidth = 'w-44', className = '', bodyClassName = 'h-64' }) => (
  <section className={`rounded-2xl bg-surface p-6 ${className}`}>
    <div className="mb-6 flex items-center justify-between">
      <SkeletonBlock className={`h-7 ${titleWidth}`} />
      <SkeletonBlock className="h-5 w-8" />
    </div>
    <SkeletonBlock className={`w-full ${bodyClassName}`} />
  </section>
);

export const KpiSurfaceSkeleton: React.FC = () => (
  <div className="rounded-2xl bg-surface p-5">
    <SkeletonBlock className="h-3 w-20" />
    <SkeletonBlock className="mt-3 h-8 w-16" />
  </div>
);
