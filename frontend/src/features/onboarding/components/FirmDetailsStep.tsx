import type { UseFormRegister } from 'react-hook-form';
import { Controller, useFormContext } from 'react-hook-form';
import { FiCheck } from 'react-icons/fi';
import { cn } from '@/utils';
import { ONBOARDING_PRACTICE_OPTIONS } from '../practiceTypes';
import type { OnboardingFormValues } from '../types';

interface OnboardingFieldProps {
  disabled?: boolean;
  error?: string;
  label: string;
  numericOnly?: boolean;
  placeholder?: string;
  type?: string;
  value?: string;
  registration?: ReturnType<UseFormRegister<OnboardingFormValues>>;
}

const OnboardingField = ({
  disabled = false,
  error,
  label,
  numericOnly = false,
  placeholder,
  type = 'text',
  value,
  registration,
}: OnboardingFieldProps) => (
  <div className="group">
    <label className="mb-1 block text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary">
      {label}
    </label>
    <input
      type={type}
      placeholder={placeholder}
      value={value}
      disabled={disabled}
      inputMode={numericOnly ? 'numeric' : undefined}
      pattern={numericOnly ? '[0-9]*' : undefined}
      onInput={
        numericOnly
          ? (event) => {
              event.currentTarget.value = event.currentTarget.value.replace(/\D/g, '');
            }
          : undefined
      }
      className={`w-full border-0 border-b bg-transparent px-0 pb-2 pt-1 text-sm text-text-secondary outline-none transition-colors placeholder:text-subtle focus:ring-0 disabled:cursor-not-allowed disabled:text-muted ${
        error
          ? 'border-app-danger-text'
          : 'border-border focus:border-app-accent group-focus-within:border-app-accent'
      }`}
      {...registration}
    />
    {error ? <p className="mt-1.5 text-xs font-medium text-app-danger-text">{error}</p> : null}
  </div>
);

const PracticeTypeSelector = () => {
  const {
    control,
    formState: { errors },
  } = useFormContext<OnboardingFormValues>();

  return (
    <div className="mt-12">
      <div className="mb-4 flex flex-col gap-1">
        <p className="font-poppins text-xs font-bold uppercase tracking-[0.06em] text-text-secondary">
          Legal practice type
        </p>
      </div>

      <Controller
        control={control}
        name="practiceType"
        render={({ field }) => (
          <div
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
            role="radiogroup"
            aria-label="Legal practice type"
          >
            {ONBOARDING_PRACTICE_OPTIONS.map((option) => {
              const Icon = option.icon;
              const isSelected = field.value === option.value;

              return (
                <button
                  key={option.value}
                  type="button"
                  disabled
                  role="radio"
                  aria-checked={isSelected}
                  aria-disabled
                  className={cn(
                    'group relative min-h-[180px] rounded-xl border bg-surface p-4 text-left shadow-sm transition',
                    'cursor-not-allowed opacity-75',
                    isSelected ? 'border-app-accent ring-2 ring-app-accent-soft' : 'border-border'
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className={cn(
                        'grid h-10 w-10 shrink-0 place-items-center rounded-xl',
                        isSelected
                          ? 'bg-app-accent text-white'
                          : 'bg-app-accent-soft text-app-accent-text'
                      )}
                    >
                      <Icon className="h-5 w-5" />
                    </span>
                    {isSelected ? (
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-app-accent text-white">
                        <FiCheck className="h-4 w-4" />
                      </span>
                    ) : !option.isAvailable ? (
                      <span className="absolute right-4 top-4 shrink-0 rounded-full bg-surface-muted px-2 py-1 text-[8px] font-bold uppercase tracking-[0.06em] text-text-secondary">
                        Coming soon
                      </span>
                    ) : null}
                  </div>

                  <h2 className="mt-4 font-poppins text-base font-semibold text-text-secondary">
                    {option.label}
                  </h2>
                  <p className="mt-1.5 text-xs leading-5 text-text-secondary">
                    {option.description}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      />

      {errors.practiceType?.message ? (
        <p className="mt-2 text-xs font-medium text-app-danger-text">
          {errors.practiceType.message}
        </p>
      ) : null}
    </div>
  );
};

export const FirmDetailsStep = () => {
  const {
    formState: { errors },
    register,
  } = useFormContext<OnboardingFormValues>();

  return (
    <section>
      <div>
        <h1 className="font-poppins text-2xl font-semibold text-app-accent-text">
          Configure Legal Workspace
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          Step 1: Provide basic information about your law firm to begin.
        </p>

        <PracticeTypeSelector />

        <div className="mt-14">
          <p className="font-poppins text-xs font-bold uppercase tracking-[0.06em] text-text-secondary">
            Firm details
          </p>
        </div>

        <div className="mt-8 grid gap-x-12 gap-y-10 md:grid-cols-2">
          <OnboardingField
            label="Firm name"
            placeholder="Enter law firm name"
            error={errors.firmName?.message}
            registration={register('firmName')}
          />
          <OnboardingField
            label="Firm email address"
            placeholder="name@firmdomain.com"
            error={errors.firmAddress?.message}
            registration={register('firmAddress')}
          />
          <OnboardingField
            label="Firm contact number"
            placeholder="Enter firm phone number"
            numericOnly
            error={errors.contactNumber?.message}
            registration={register('contactNumber')}
          />
          <OnboardingField
            label="Account owner"
            placeholder="Enter owner name"
            error={errors.ownerName?.message}
            disabled
            registration={register('ownerName')}
          />
        </div>
      </div>
    </section>
  );
};
