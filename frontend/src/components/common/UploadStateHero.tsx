import React from 'react';

export type UploadVisualState = 'idle' | 'hover' | 'uploading' | 'success';

interface UploadStateHeroProps {
  state: UploadVisualState;
  fileTypeLabel?: string;
}

const FileFoldCorner: React.FC<{ sizeClass?: string }> = ({ sizeClass = 'h-9 w-9' }) => (
  <div className={`pointer-events-none absolute right-0 top-0 ${sizeClass}`}>
    <svg viewBox="0 0 100 100" className="h-full w-full">
      <path d="M0 0 L100 0 L100 100 Z" className="fill-surface-muted/85" />
      <path
        d="M0 0 L100 100"
        className="stroke-border/95"
        strokeWidth="6"
        strokeLinecap="round"
      />
    </svg>
  </div>
);

export const UploadStateHero: React.FC<UploadStateHeroProps> = ({
  state,
  fileTypeLabel = 'PDF',
}) => {
  const isHover = state === 'hover';
  const isUploading = state === 'uploading';
  const isSuccess = state === 'success';

  return (
    <div className="relative mb-6 flex h-56 w-64 items-center justify-center">
      {!isUploading && !isSuccess && (
        <>
          <div
            className={`absolute h-40 w-28 overflow-hidden rounded-2xl border border-border bg-app-surface-elevated dark:border-slate-500 dark:bg-slate-600 shadow-[0_18px_35px_-28px_rgba(15,23,42,0.55)] transition-all duration-300 ${
              isHover
                ? '-translate-x-[3.15rem] rotate-[-20deg] opacity-90'
                : '-translate-x-[2.1rem] rotate-[-13deg] opacity-65 dark:opacity-90'
            }`}
          >
            <FileFoldCorner sizeClass="h-8 w-8" />
            <div className="px-3 pt-3">
              <div className="h-1.5 w-12 rounded-full bg-surface-muted dark:bg-slate-400" />
              <div className="mt-2 h-1.5 w-8 rounded-full bg-surface-muted dark:bg-slate-400" />
            </div>
          </div>
          <div
            className={`absolute h-40 w-28 overflow-hidden rounded-2xl border border-border bg-app-surface-elevated dark:border-slate-500 dark:bg-slate-600 shadow-[0_18px_35px_-28px_rgba(15,23,42,0.55)] transition-all duration-300 ${
              isHover
                ? 'translate-x-[3.15rem] rotate-[20deg] opacity-90'
                : 'translate-x-[2.1rem] rotate-[13deg] opacity-65 dark:opacity-90'
            }`}
          >
            <FileFoldCorner sizeClass="h-8 w-8" />
            <div className="px-3 pt-3">
              <div className="h-1.5 w-12 rounded-full bg-surface-muted dark:bg-slate-400" />
              <div className="mt-2 h-1.5 w-8 rounded-full bg-surface-muted dark:bg-slate-400" />
            </div>
          </div>
        </>
      )}

      {isUploading && (
        <>
          {[
            { left: '18%', delay: '0ms' },
            { left: '34%', delay: '150ms' },
            { left: '66%', delay: '80ms' },
            { left: '82%', delay: '230ms' },
          ].map((line, index) => (
            <span
              key={`upload-line-${index}`}
              className="absolute h-24 w-1 rounded-full bg-indigo-500/45"
              style={{
                left: line.left,
                top: '-6%',
                animation: `pdf-upload-line 820ms linear ${line.delay} infinite`,
              }}
            />
          ))}
        </>
      )}

      {isSuccess && (
        <>
          <svg
            className="absolute -left-2 top-28 h-20 w-20 text-border opacity-95 drop-shadow-[0_10px_20px_-14px_rgba(15,23,42,0.7)] dark:text-surface-muted dark:opacity-90"
            fill="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
            style={{ animation: 'pdf-cloud-in-left 520ms ease-out 80ms both' }}
          >
            <path d="M19 18a4 4 0 00-.7-7.9A6 6 0 006.6 9 4.5 4.5 0 007 18h12z" />
          </svg>
          <svg
            className="absolute right-0 top-24 h-16 w-16 text-border opacity-95 drop-shadow-[0_10px_20px_-14px_rgba(15,23,42,0.7)] dark:text-surface-muted dark:opacity-90"
            fill="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
            style={{ animation: 'pdf-cloud-in-right 560ms ease-out 130ms both' }}
          >
            <path d="M19 18a4 4 0 00-.7-7.9A6 6 0 006.6 9 4.5 4.5 0 007 18h12z" />
          </svg>
          <svg
            className="absolute right-8 top-8 h-12 w-12 text-muted opacity-90 drop-shadow-[0_10px_20px_-14px_rgba(15,23,42,0.65)] dark:text-surface-muted dark:opacity-85"
            fill="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
            style={{ animation: 'pdf-cloud-in-top 500ms ease-out 180ms both' }}
          >
            <path d="M19 18a4 4 0 00-.7-7.9A6 6 0 006.6 9 4.5 4.5 0 007 18h12z" />
          </svg>
        </>
      )}

      <div className="relative h-44 w-32 overflow-hidden rounded-2xl border border-border bg-app-surface-elevated dark:border-slate-500 dark:bg-slate-600 shadow-[0_22px_45px_-28px_rgba(15,23,42,0.6)]">
        <div className="px-4 pt-4">
          <div className="h-1.5 w-14 rounded-full bg-surface-muted dark:bg-slate-400" />
          <div className="mt-2 h-1.5 w-9 rounded-full bg-surface-muted dark:bg-slate-400" />
        </div>
        <FileFoldCorner />

        {!isUploading && !isSuccess && (
          <div className="absolute left-1/2 top-[58%] -translate-x-1/2 -translate-y-1/2 rounded-md bg-app-accent px-2 py-1 text-[10px] font-semibold text-white shadow-sm">
            {fileTypeLabel}
          </div>
        )}

        {isUploading && (
          <div className="absolute left-1/2 top-[58%] h-16 w-16 -translate-x-1/2 -translate-y-1/2">
            <div className="h-full w-full rounded-full border-[6px] border-app-accent/20 border-t-app-accent animate-spin" />
          </div>
        )}

        {isSuccess && (
          <div className="absolute left-1/2 top-[58%] flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-app-accent text-white shadow-[0_12px_25px_-14px_rgba(37,99,235,0.95)]">
            <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.8}
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>
        )}
      </div>

      <style>{`
        @keyframes pdf-upload-line {
          0% {
            transform: translateY(-28px);
            opacity: 0;
          }
          25% {
            opacity: 0.8;
          }
          100% {
            transform: translateY(150px);
            opacity: 0;
          }
        }

        @keyframes pdf-cloud-in-left {
          0% {
            opacity: 0;
            transform: translate(-22px, 10px) scale(0.92);
          }
          100% {
            opacity: 1;
            transform: translate(0, 0) scale(1);
          }
        }

        @keyframes pdf-cloud-in-right {
          0% {
            opacity: 0;
            transform: translate(24px, 9px) scale(0.92);
          }
          100% {
            opacity: 1;
            transform: translate(0, 0) scale(1);
          }
        }

        @keyframes pdf-cloud-in-top {
          0% {
            opacity: 0;
            transform: translateY(-16px) scale(0.9);
          }
          100% {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
      `}</style>
    </div>
  );
};
