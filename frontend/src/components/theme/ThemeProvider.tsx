import React, { useEffect, useLayoutEffect } from 'react';
import { useThemeStore } from '@/stores/useThemeStore';

interface ThemeProviderProps {
  children: React.ReactNode;
}

const THEME_MEDIA_QUERY = '(prefers-color-scheme: dark)';

const applyThemeToDocument = (resolvedMode: 'light' | 'dark') => {
  const root = document.documentElement;
  const isDark = resolvedMode === 'dark';

  root.classList.toggle('dark', isDark);
  root.dataset.theme = resolvedMode;
  root.style.colorScheme = resolvedMode;
};

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const mode = useThemeStore((state) => state.mode);
  const resolvedMode = useThemeStore((state) => state.resolvedMode);
  const syncResolvedMode = useThemeStore((state) => state.syncResolvedMode);

  useLayoutEffect(() => {
    applyThemeToDocument(resolvedMode);
  }, [resolvedMode]);

  useEffect(() => {
    if (mode !== 'system') {
      return;
    }

    const mediaQuery = window.matchMedia(THEME_MEDIA_QUERY);
    const syncFromSystem = () => syncResolvedMode();

    syncFromSystem();
    mediaQuery.addEventListener('change', syncFromSystem);

    return () => {
      mediaQuery.removeEventListener('change', syncFromSystem);
    };
  }, [mode, syncResolvedMode]);

  return <>{children}</>;
};
