import type { ReactElement } from 'react';
import type { SourceFamily } from '@/utils/studio/sourceConfig';

interface InteractionPatternPickerProps {
  family: SourceFamily;
  selectedKey: string;
  onSelect: (patternKey: string) => void;
}

export const InteractionPatternPicker = ({
  family,
  selectedKey,
  onSelect,
}: InteractionPatternPickerProps): ReactElement => {
  return (
    <div>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-subtle">
        Interaction pattern
      </p>
      <div className="space-y-1.5">
        {family.patterns.map((pattern) => {
          const isSelected = pattern.key === selectedKey;
          return (
            <label
              key={pattern.key}
              className={`flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
                isSelected
                  ? 'border-app-accent bg-app-accent-soft/40'
                  : 'border-border bg-surface hover:border-border-strong'
              }`}
            >
              <input
                type="radio"
                name={`interaction-${family.key}`}
                checked={isSelected}
                onChange={() => onSelect(pattern.key)}
                className="mt-0.5 h-4 w-4 shrink-0 accent-app-accent"
              />
              <PatternIcon patternKey={pattern.key} isSelected={isSelected} />
              <div className="min-w-0 flex-1">
                <p
                  className={`text-[13px] font-semibold ${
                    isSelected ? 'text-app-accent-text' : 'text-text-secondary'
                  }`}
                >
                  {pattern.label}
                </p>
                <p
                  className={`mt-0.5 text-[11px] leading-snug ${
                    isSelected ? 'text-text-secondary' : 'text-muted'
                  }`}
                >
                  {pattern.description}
                </p>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
};

const PatternIcon = ({
  patternKey,
  isSelected,
}: { patternKey: string; isSelected: boolean }): ReactElement => {
  const tone = isSelected ? 'text-app-accent-text' : 'text-muted';
  const cls = `mt-0.5 h-4 w-4 shrink-0 ${tone}`;

  if (patternKey === 'dropdown' || patternKey === 'auto' || patternKey === 'rule') {
    return (
      <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
      </svg>
    );
  }
  if (patternKey === 'reco_chips' || patternKey === 'reco_from_deps') {
    return (
      <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 12h10M5 16h6" />
      </svg>
    );
  }
  if (patternKey === 'group') {
    return (
      <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <rect x="3" y="4" width="18" height="6" rx="1" strokeWidth={2} />
        <rect x="3" y="14" width="18" height="6" rx="1" strokeWidth={2} />
      </svg>
    );
  }
  if (patternKey === 'plain_text' || patternKey === 'with_docs') {
    return (
      <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
        />
      </svg>
    );
  }
  if (patternKey === 'date') {
    return (
      <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <rect x="3" y="4" width="18" height="18" rx="2" strokeWidth={2} />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 2v4M8 2v4M3 10h18" />
      </svg>
    );
  }
  return (
    <svg className={cls} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z"
      />
    </svg>
  );
};

export default InteractionPatternPicker;
