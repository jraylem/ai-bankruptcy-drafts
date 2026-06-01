import React from 'react';

export const ContentSkeleton: React.FC = () => {
  return (
    <div className="flex-1 flex min-w-0 h-full animate-pulse">
      {/* Chat Area Skeleton */}
      <div className="flex-1 flex flex-col min-w-0 bg-surface-muted">
        {/* Chat header */}
        <div className="h-16 border-b border-border bg-surface px-6 flex items-center">
          <div className="h-6 bg-border rounded w-48" />
        </div>

        {/* Messages area */}
        <div className="flex-1 p-6 space-y-4">
          <div className="flex justify-start">
            <div className="h-20 bg-border rounded-lg w-2/3" />
          </div>
          <div className="flex justify-end">
            <div className="h-12 bg-border rounded-lg w-1/2" />
          </div>
          <div className="flex justify-start">
            <div className="h-32 bg-border rounded-lg w-3/4" />
          </div>
        </div>

        {/* Input area */}
        <div className="h-20 border-t border-border bg-surface px-6 flex items-center">
          <div className="h-12 bg-border rounded-lg flex-1" />
        </div>
      </div>

      {/* PDF Panel Skeleton */}
      <aside className="w-[40%] flex-shrink-0 border-l border-border bg-surface">
        <div className="p-4 space-y-4">
          <div className="h-10 bg-border rounded" />
          <div className="h-[calc(100vh-200px)] bg-border rounded" />
        </div>
      </aside>
    </div>
  );
};
