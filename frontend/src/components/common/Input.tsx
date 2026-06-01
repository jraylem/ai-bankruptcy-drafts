import React from 'react';
import { cn } from '@/utils';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, className, ...props }, ref) => {
    return (
      <div className="w-full">
        {label && <label className="block text-sm font-medium text-text-secondary mb-1">{label}</label>}
        <input
          ref={ref}
          className={cn(
            'w-full px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 transition-colors placeholder:text-subtle',
            error
              ? 'border-app-danger-text focus:ring-app-danger-text focus:border-app-danger-text'
              : 'border-border focus:ring-primary-500 focus:border-transparent',
            'disabled:bg-surface-muted disabled:cursor-not-allowed',
            className
          )}
          {...props}
        />
        {error && <p className="mt-1 text-sm text-app-danger-text">{error}</p>}
        {helperText && !error && <p className="mt-1 text-sm text-subtle">{helperText}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';
