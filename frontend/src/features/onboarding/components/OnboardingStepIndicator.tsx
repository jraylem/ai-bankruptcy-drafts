import { FiCheck } from 'react-icons/fi';
import { cn } from '@/utils';

interface OnboardingStepIndicatorProps {
  currentStep: number;
}

const STEPS = ['Firm', 'Members', 'Review'];
const DESCRIPTIONS = ['Basic info', 'Add your team', 'Final check'];

export const OnboardingStepIndicator = ({ currentStep }: OnboardingStepIndicatorProps) => (
  <nav aria-label="Onboarding progress" className="relative space-y-12">
    <span
      className="absolute right-4 top-6 h-[calc(100%-3rem)] w-px bg-border"
      aria-hidden="true"
    />
    {STEPS.map((step, index) => {
      const stepNumber = index + 1;
      const isComplete = stepNumber < currentStep;
      const isActive = stepNumber === currentStep;

      return (
        <div key={step} className="relative z-10 flex items-center justify-end gap-5">
          <div
            className={cn(
              'min-w-0 text-right transition-opacity',
              !isComplete && !isActive && 'opacity-50'
            )}
          >
            <p
              className={cn(
                'text-sm font-semibold',
                isActive || isComplete ? 'text-text-secondary' : 'text-muted'
              )}
            >
              {step}
            </p>
            <p className="mt-0.5 text-xs text-text-secondary">{DESCRIPTIONS[index]}</p>
          </div>
          <span
            className={cn(
              'grid h-8 w-8 shrink-0 place-items-center rounded-full border text-xs font-bold ring-4 ring-surface',
              isComplete && 'border-app-accent bg-app-accent text-white',
              isActive && 'border-app-accent bg-app-accent text-white',
              !isComplete && !isActive && 'border-border bg-surface text-text-secondary'
            )}
          >
            {isComplete ? <FiCheck className="h-4 w-4" /> : stepNumber}
          </span>
        </div>
      );
    })}
  </nav>
);
