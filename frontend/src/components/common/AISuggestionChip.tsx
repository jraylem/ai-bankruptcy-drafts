import React, { useState } from 'react';
import { FiCheck } from 'react-icons/fi';

interface AISuggestionChipProps {
  text: string;
  selected: boolean;
  onClick: () => void;
  maxLength?: number;
}

const truncateText = (text: string, maxLength: number): string => {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
};

export const AISuggestionChip: React.FC<AISuggestionChipProps> = ({
  text,
  selected,
  onClick,
  maxLength = 80,
}) => {
  const [tooltipPosition, setTooltipPosition] = useState<{ top: number; left: number } | null>(null);
  const shouldShowTooltip = text.length > maxLength;

  const showTooltip = (
    event: React.MouseEvent<HTMLButtonElement> | React.FocusEvent<HTMLButtonElement>
  ) => {
    if (!shouldShowTooltip) {
      setTooltipPosition(null);
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    setTooltipPosition({
      top: rect.top - 10,
      left: rect.left + rect.width / 2,
    });
  };

  const hideTooltip = () => {
    setTooltipPosition(null);
  };

  return (
    <>
      <button
        type="button"
        onClick={onClick}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onFocus={showTooltip}
        onBlur={hideTooltip}
        className={`inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1.5 text-left text-xs font-medium transition-colors ${
          selected
            ? 'border-app-border-strong bg-app-accent-soft text-app-accent-text'
            : 'border-border bg-surface text-text-secondary hover:border-app-accent/55 hover:bg-app-accent-soft hover:text-app-accent-text'
        }`}
      >
        <span
          className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] ${
            selected
              ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white'
              : 'font-semibold text-app-accent-text'
          }`}
        >
          {selected ? <FiCheck className="h-2.5 w-2.5" /> : '+'}
        </span>
        <span className="truncate">{truncateText(text, maxLength)}</span>
      </button>

      {tooltipPosition && (
        <div
          className="pointer-events-none fixed z-40 max-w-80 -translate-x-1/2 -translate-y-full rounded-xl border border-border bg-surface px-3 py-2 text-left shadow-xl"
          style={{
            top: `${tooltipPosition.top}px`,
            left: `${tooltipPosition.left}px`,
          }}
        >
          <p className="text-xs leading-5 text-muted">{text}</p>
        </div>
      )}
    </>
  );
};
