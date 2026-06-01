import { create } from 'zustand';

interface AnalyticsAiChatState {
  isOpen: boolean;
  isMinimized: boolean;
  hasInFlightRequest: boolean;
  lastError: string | null;
  queuedSuggestedAction: string | null;
  openWidget: () => void;
  minimizeWidget: () => void;
  restoreWidget: () => void;
  closeWidget: () => void;
  enqueueSuggestedAction: (prompt: string) => void;
  consumeQueuedPrompt: () => string | null;
  setInFlight: (value: boolean) => void;
  setLastError: (message: string | null) => void;
}

export const useAnalyticsAiChatStore = create<AnalyticsAiChatState>((set, get) => ({
  isOpen: false,
  isMinimized: false,
  hasInFlightRequest: false,
  lastError: null,
  queuedSuggestedAction: null,
  openWidget: () => set({ isOpen: true, isMinimized: false }),
  minimizeWidget: () => set((state) => ({ isOpen: false, isMinimized: state.isOpen || state.isMinimized })),
  restoreWidget: () => set((state) => ({ isOpen: state.isOpen || state.isMinimized, isMinimized: false })),
  closeWidget: () => set({ isOpen: false, isMinimized: false }),
  enqueueSuggestedAction: (prompt) =>
    set({
      queuedSuggestedAction: prompt,
      isOpen: true,
      isMinimized: false,
    }),
  consumeQueuedPrompt: () => {
    const queuedPrompt = get().queuedSuggestedAction;
    if (queuedPrompt) {
      set({ queuedSuggestedAction: null });
    }
    return queuedPrompt;
  },
  setInFlight: (value) => set({ hasInFlightRequest: value }),
  setLastError: (message) => set({ lastError: message }),
}));
