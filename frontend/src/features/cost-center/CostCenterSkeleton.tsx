import React from 'react';

const Block: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div
    className={`rounded bg-surface-muted animate-pulse motion-reduce:animate-none motion-reduce:opacity-60 ${className}`}
  />
);

export const CostCenterSkeleton: React.FC = () => (
  <>
    <section className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <article
          key={i}
          className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5"
        >
          <div className="flex items-center gap-2">
            <Block className="h-7 w-7 rounded-md" />
            <Block className="h-3 w-24" />
          </div>
          <Block className="h-8 w-32" />
          <Block className="h-3 w-40" />
        </article>
      ))}
    </section>
    <section className="mb-6">
      <Block className="mb-2 h-3 w-16" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <article
            key={i}
            className="flex flex-col gap-1 rounded-md border border-border/60 bg-surface-muted/40 px-4 py-3"
          >
            <Block className="h-2.5 w-16" />
            <Block className="h-5 w-20" />
          </article>
        ))}
      </div>
    </section>
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <div className="rounded-lg border border-border bg-surface p-5 lg:col-span-7">
        <Block className="mb-4 h-4 w-24" />
        <Block className="h-[200px] w-full max-sm:h-[160px]" />
      </div>
      <div className="rounded-lg border border-border bg-surface p-5 lg:col-span-5">
        <Block className="mb-4 h-4 w-32" />
        <div className="flex flex-col gap-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <Block key={i} className="h-5 w-full" />
          ))}
        </div>
      </div>
    </section>
  </>
);
