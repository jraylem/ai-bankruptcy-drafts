import React from 'react';
import { FiMoon, FiSun } from 'react-icons/fi';
import { useThemeStore } from '@/stores/useThemeStore';

interface ThemeModeToggleProps {
  orientation?: 'horizontal' | 'vertical';
  className?: string;
}

export const ThemeModeToggle: React.FC<ThemeModeToggleProps> = ({
  orientation = 'horizontal',
  className = '',
}) => {
  const resolvedMode = useThemeStore((state) => state.resolvedMode);
  const setMode = useThemeStore((state) => state.setMode);
  const isDark = resolvedMode === 'dark';
  const isVertical = orientation === 'vertical';

  return (
    <button
      type="button"
      onClick={() => setMode(isDark ? 'light' : 'dark')}
      className={`relative inline-flex rounded-full border transition-all duration-200 ${
        isVertical ? 'h-16 w-8' : 'h-8 w-16'
      } ${
        isDark
          ? 'border-zinc-900 bg-zinc-900'
          : 'border-zinc-300 bg-zinc-100'
      } ${className}`}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={`Theme switch, currently ${resolvedMode}`}
      aria-checked={isDark}
      role="switch"
    >
      {isDark ? (
        <FiMoon
          className={
            isVertical
              ? 'absolute bottom-2 left-1/2 h-3.5 w-3.5 -translate-x-1/2 text-white/90'
              : 'absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/90'
          }
        />
      ) : (
        <FiSun
          className={
            isVertical
              ? 'absolute left-1/2 top-2 h-3.5 w-3.5 -translate-x-1/2 text-zinc-700'
              : 'absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-700'
          }
        />
      )}

      <span
        className={`absolute h-6 w-6 rounded-full shadow-[0_2px_6px_rgba(0,0,0,0.35)] transition-transform duration-200 ${
          isVertical ? 'left-[3px] top-[3px]' : 'left-[3px] top-[3px]'
        } ${
          isVertical
            ? isDark
              ? 'translate-y-0 bg-white'
              : 'translate-y-[32px] bg-zinc-800'
            : isDark
              ? 'translate-x-0 bg-white'
              : 'translate-x-[32px] bg-zinc-800'
        }`}
      />
    </button>
  );
};
