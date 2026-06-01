import { FiCheck } from 'react-icons/fi';
import { cn } from '@/utils';

interface StepIndicatorProps {
  currentStep: number;
  steps: { label: string; description: string }[];
  // Highest step number the user has reached. Steps ≤ maxReachedStep (and not
  // the current one) become clickable so the paralegal can jump back/forward
  // between visited steps. Defaults to currentStep (only past = clickable).
  maxReachedStep?: number;
  onStepClick?: (stepIndex: number) => void;
}

export const StepIndicator = ({
  currentStep,
  steps,
  maxReachedStep,
  onStepClick,
}: StepIndicatorProps) => {
  const maxReached = maxReachedStep ?? currentStep;

  return (
    <nav aria-label="Wizard progress" className="flex w-full items-start">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const isActive = stepNumber === currentStep;
        const isVisited = stepNumber <= maxReached && !isActive;
        const isReached = stepNumber <= maxReached;
        const isClickable = isVisited && Boolean(onStepClick);
        const isFirst = index === 0;
        const isLast = index === steps.length - 1;

        // Each connector half-line is "active" when the step it connects FROM
        // has been visited. Left half of step N is filled when step N-1 is
        // reached; right half of step N is filled when step N itself is.
        const leftLineActive = stepNumber - 1 <= maxReached && stepNumber - 1 > 0;
        const rightLineActive = stepNumber <= maxReached;

        const indicatorClass = cn(
          'grid h-7 w-7 shrink-0 place-items-center rounded-full border text-[11px] font-bold transition-colors',
          (isVisited || isActive) && 'border-app-accent bg-app-accent text-white',
          !isReached && 'border-border bg-surface text-subtle',
        );

        const labelBlock = (
          <div
            className={cn(
              'mt-1.5 flex flex-col items-center text-center',
              !isReached && 'opacity-60',
            )}
          >
            <p
              className={cn(
                'text-[11px] font-semibold uppercase tracking-wider',
                isReached ? 'text-text-secondary' : 'text-muted',
              )}
            >
              {step.label}
            </p>
            <p className="text-[11px] text-subtle">{step.description}</p>
          </div>
        );

        const stepContent = (
          <div className="flex w-full flex-col items-center">
            {/* Top row: left half-line + circle + right half-line. Half-lines
                meet between circles to form a single continuous connector. */}
            <div className="flex w-full items-center">
              <span
                aria-hidden="true"
                className={cn(
                  'h-px flex-1 transition-colors',
                  isFirst && 'invisible',
                  leftLineActive ? 'bg-app-accent' : 'bg-border',
                )}
              />
              <span className={indicatorClass}>
                {isVisited ? <FiCheck className="h-3.5 w-3.5" /> : stepNumber}
              </span>
              <span
                aria-hidden="true"
                className={cn(
                  'h-px flex-1 transition-colors',
                  isLast && 'invisible',
                  rightLineActive ? 'bg-app-accent' : 'bg-border',
                )}
              />
            </div>
            {labelBlock}
          </div>
        );

        return (
          <div
            key={step.label}
            className="flex flex-1 flex-col items-stretch"
          >
            {isClickable ? (
              <button
                type="button"
                onClick={() => onStepClick?.(index)}
                className="group cursor-pointer rounded-md transition-opacity hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-app-accent/30"
                aria-label={`Jump to step ${stepNumber}: ${step.label}`}
              >
                {stepContent}
              </button>
            ) : (
              <div>{stepContent}</div>
            )}
          </div>
        );
      })}
    </nav>
  );
};
