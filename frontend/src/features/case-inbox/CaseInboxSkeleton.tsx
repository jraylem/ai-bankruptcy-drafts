import React from 'react';

const Block: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div
    className={`rounded bg-surface-muted animate-pulse motion-reduce:animate-none motion-reduce:opacity-60 ${className}`}
  />
);

/** Layout-shaped skeleton — matches the populated table so the layout
 *  doesn't shift when data arrives. Reuses the Cost Center pulse pattern. */
export const CaseInboxSkeleton: React.FC = () => (
  <div className="rounded-lg border border-border bg-surface p-5">
    <div className="flex flex-col gap-3">
      {[0, 1, 2, 3, 4].map((i) => (
        <div key={i} className="grid grid-cols-[80px_140px_1fr_60px_80px_200px] items-center gap-3">
          <Block className="h-3" />
          <Block className="h-3" />
          <Block className="h-3" />
          <Block className="h-4 w-12 rounded-full" />
          <Block className="h-3" />
          <Block className="h-6 justify-self-end w-40" />
        </div>
      ))}
    </div>
  </div>
);
