import { cn } from '@/utils';
import { SourceIcon } from './SourceIcon';
import type { SourceKind } from './types';

interface SourceCardProps {
  source: SourceKind;
  label: string;
  description: string;
  example: string;
  isSelected: boolean;
  onSelect: () => void;
}

export const SourceCard = ({
  source,
  label,
  description,
  example,
  isSelected,
  onSelect,
}: SourceCardProps) => (
  <button
    type="button"
    onClick={onSelect}
    className={cn(
      'group flex w-full cursor-pointer items-start gap-3 rounded-xl border bg-surface p-4 text-left transition-all',
      isSelected
        ? 'border-app-accent shadow-sm ring-2 ring-app-accent/20'
        : 'border-border hover:border-app-accent/40 hover:bg-surface-muted',
    )}
    aria-pressed={isSelected}
  >
    <span
      className={cn(
        'grid h-10 w-10 shrink-0 place-items-center rounded-lg transition-colors',
        isSelected
          ? 'bg-app-accent text-white'
          : 'bg-surface-muted text-text-secondary group-hover:bg-app-accent-soft group-hover:text-app-accent-text',
      )}
    >
      <SourceIcon source={source} className="h-5 w-5" />
    </span>
    <div className="min-w-0 flex-1">
      <p
        className={cn(
          'text-sm font-semibold',
          isSelected ? 'text-app-accent-text' : 'text-text-secondary',
        )}
      >
        {label}
      </p>
      <p className="mt-0.5 text-xs leading-relaxed text-text-secondary">{description}</p>
      <p className="mt-1.5 text-[11px] italic text-subtle">{example}</p>
    </div>
  </button>
);
