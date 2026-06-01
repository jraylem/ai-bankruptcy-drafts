import type { ReactElement } from 'react';
import type { UserInputDateSourceParams } from '@/types/studio';

interface DateFormatFieldProps {
  params: UserInputDateSourceParams | null;
  onChange: (next: UserInputDateSourceParams) => void;
}

const DEFAULT_FORMAT = '%B %-d, %Y';

export const DateFormatField = ({ params, onChange }: DateFormatFieldProps): ReactElement => {
  const label = params?.label ?? '';
  const placeholder = params?.placeholder ?? '';

  const emit = (next: Partial<UserInputDateSourceParams>): void => {
    onChange({
      label,
      placeholder: placeholder || null,
      format: DEFAULT_FORMAT,
      ...next,
    });
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-app-accent-soft bg-app-accent-soft/40 px-3 py-2 text-xs text-app-accent-text">
        <p className="font-semibold">Date picker</p>
        <p className="mt-0.5">
          The author will get a calendar widget at draft time. Picked dates render as
          <span className="ml-1 font-mono">"April 1, 2026"</span> — matches
          system-generated and derived dates so they all read consistently.
        </p>
      </div>

      <div>
        <label
          className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted"
          htmlFor="date-picker-label"
        >
          <span>Label</span>
          <span className="text-red-500">*</span>
        </label>
        <input
          id="date-picker-label"
          type="text"
          value={label}
          onChange={(e) => emit({ label: e.target.value })}
          placeholder="The date the debtor's case was dismissed."
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
        />
      </div>

      <details className="group rounded-xl border border-border bg-surface-muted/40">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-semibold text-text-secondary [&::-webkit-details-marker]:hidden">
          <svg
            className="h-3.5 w-3.5 text-muted transition-transform group-open:rotate-90"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
          <span>Advanced</span>
        </summary>
        <div className="space-y-4 border-t border-border px-4 py-4">
          <div>
            <label
              className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted"
              htmlFor="date-picker-placeholder"
            >
              Placeholder
            </label>
            <input
              id="date-picker-placeholder"
              type="text"
              value={placeholder}
              onChange={(e) => emit({ placeholder: e.target.value })}
              placeholder="Optional helper text shown next to the picker"
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-secondary placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
          </div>
        </div>
      </details>
    </div>
  );
};

export default DateFormatField;
