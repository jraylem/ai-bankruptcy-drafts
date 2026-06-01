import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { STORAGE_KEYS } from '@/constants';

export type ThemeMode = 'light' | 'dark' | 'system';
export type ResolvedThemeMode = 'light' | 'dark';

interface ThemeState {
  mode: ThemeMode;
  resolvedMode: ResolvedThemeMode;
  setMode: (mode: ThemeMode) => void;
  toggleMode: () => void;
  syncResolvedMode: () => void;
}

const resolveSystemMode = (): ResolvedThemeMode => {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return 'light';
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

const resolveMode = (mode: ThemeMode): ResolvedThemeMode => {
  if (mode === 'system') {
    return resolveSystemMode();
  }

  return mode;
};

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: 'system',
      resolvedMode: resolveSystemMode(),

      setMode: (mode) =>
        set({
          mode,
          resolvedMode: resolveMode(mode),
        }),

      toggleMode: () => {
        const nextMode = get().resolvedMode === 'dark' ? 'light' : 'dark';
        set({
          mode: nextMode,
          resolvedMode: nextMode,
        });
      },

      syncResolvedMode: () => {
        const { mode } = get();
        if (mode !== 'system') {
          return;
        }

        set({
          resolvedMode: resolveSystemMode(),
        });
      },
    }),
    {
      name: STORAGE_KEYS.THEME,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        mode: state.mode,
      }),
      onRehydrateStorage: () => (state) => {
        if (!state) {
          return;
        }

        state.setMode(state.mode);
      },
    }
  )
);
