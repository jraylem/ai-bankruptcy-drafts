import React, { useEffect, useState } from 'react';
import { cn } from '@/utils';

interface StreamingIndicatorProps {
  messageIndex: number | null;
  progressMessage?: string;
  className?: string;
}

const ICONS: Record<number, React.ReactNode> = {
  0: (
    <svg className="w-10 h-10 text-app-danger-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  ),
  1: (
    <svg className="w-10 h-10 text-app-accent-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  2: (
    <svg className="w-10 h-10 text-app-accent-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  3: (
    <svg className="w-10 h-10 text-app-accent-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
  4: (
    <svg className="w-10 h-10 text-app-accent-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  5: (
    <svg className="w-10 h-10 text-app-accent-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  ),
};

export const StreamingIndicator: React.FC<StreamingIndicatorProps> = ({
  messageIndex,
  progressMessage,
  className,
}) => {
  const [displayIndex, setDisplayIndex] = useState<number>(messageIndex ?? 1);
  const [isAnimating, setIsAnimating] = useState(false);

  useEffect(() => {
    if (messageIndex !== null && messageIndex !== displayIndex) {
      setIsAnimating(true);
      const timer = setTimeout(() => {
        setDisplayIndex(messageIndex);
        setIsAnimating(false);
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [messageIndex, displayIndex]);

  const icon = ICONS[displayIndex] || ICONS[1];
  const isError = displayIndex === 0;

  return (
    <div className={cn('flex flex-col items-center justify-center py-8', className)}>
      {/* Animated Icon Container */}
      <div className="relative mb-8">
        {/* Pulsing background ring */}
        {!isError && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-24 h-24 rounded-full bg-app-accent-soft animate-pulse-ring" />
          </div>
        )}

        {/* Icon with bounce animation */}
        <div
          className={cn(
            'relative z-10 flex items-center justify-center w-20 h-20 rounded-full transition-all duration-300',
            isError ? 'bg-app-danger-soft' : 'bg-app-accent-soft',
            isAnimating ? 'scale-90 opacity-50' : 'scale-100 opacity-100',
            !isError && 'animate-icon-float'
          )}
        >
          {icon}
        </div>

        {/* Orbiting dots for non-error states */}
        {!isError && (
          <div className="absolute inset-0 w-20 h-20 animate-spin-slow">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1 w-2.5 h-2.5 rounded-full bg-app-accent/70" />
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1 w-2.5 h-2.5 rounded-full bg-app-accent/60" />
          </div>
        )}
      </div>

      {/* Progress message from streaming API */}
      <div
        className={cn(
          'text-center max-w-md transition-all duration-300',
          isAnimating ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'
        )}
      >
        <p
          className={cn(
            'text-lg font-medium',
            isError ? 'text-app-danger-text' : 'text-text-secondary'
          )}
        >
          {progressMessage}
        </p>
      </div>
    </div>
  );
};
