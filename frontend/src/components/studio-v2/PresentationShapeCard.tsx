import { cn } from '@/utils';
import type { PresentationShape } from './types';

interface PresentationShapeCardProps {
  shape: PresentationShape;
  label: string;
  description: string;
  preview: string;
  isSelected: boolean;
  onSelect: () => void;
}

export const PresentationShapeCard = ({
  label,
  description,
  preview,
  isSelected,
  onSelect,
}: PresentationShapeCardProps) => (
  <button
    type="button"
    onClick={onSelect}
    className={cn(
      'group flex w-full cursor-pointer flex-col gap-2 rounded-xl border bg-surface p-4 text-left transition-all',
      isSelected
        ? 'border-app-accent shadow-sm ring-2 ring-app-accent/20'
        : 'border-border hover:border-app-accent/40 hover:bg-surface-muted',
    )}
    aria-pressed={isSelected}
  >
    <p
      className={cn(
        'text-sm font-semibold',
        isSelected ? 'text-app-accent-text' : 'text-text-secondary',
      )}
    >
      {label}
    </p>
    <p className="text-xs leading-relaxed text-text-secondary">{description}</p>
    <div
      className={cn(
        'mt-1 rounded-md border px-3 py-2 font-mono text-[11px] leading-relaxed',
        isSelected
          ? 'border-app-accent/30 bg-app-accent-soft/40 text-app-accent-text'
          : 'border-border bg-surface-muted text-subtle',
      )}
    >
      {preview}
    </div>
  </button>
);
