import { create } from 'zustand';

interface UIState {
  isSidebarCollapsed: boolean;
  isPDFPanelCollapsed: boolean;
  preferredPrimaryPaneView: 'chat' | 'pdf' | null;
  isRestoringAcceptedSession: boolean;
  restoringAcceptedSessionCase: { title: string; caseNumber?: string } | null;
  setRestoringAcceptedSession: (
    value: boolean,
    caseInfo?: { title: string; caseNumber?: string }
  ) => void;
  toggleSidebar: () => void;
  togglePDFPanel: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setPDFPanelCollapsed: (collapsed: boolean) => void;
  setPreferredPrimaryPaneView: (view: 'chat' | 'pdf' | null) => void;
}

// Get persisted state from localStorage
const getPersistedState = () => {
  try {
    const sidebarCollapsed = localStorage.getItem('sidebar_collapsed');
    const pdfPanelCollapsed = localStorage.getItem('pdf_panel_collapsed');
    return {
      isSidebarCollapsed: sidebarCollapsed === 'true',
      isPDFPanelCollapsed: pdfPanelCollapsed === null ? true : pdfPanelCollapsed === 'true',
    };
  } catch {
    return {
      isSidebarCollapsed: false,
      isPDFPanelCollapsed: true,
    };
  }
};

export const useUIStore = create<UIState>((set) => ({
  ...getPersistedState(),
  preferredPrimaryPaneView: null,
  isRestoringAcceptedSession: false,
  restoringAcceptedSessionCase: null,
  setRestoringAcceptedSession: (value, caseInfo) =>
    set({
      isRestoringAcceptedSession: value,
      restoringAcceptedSessionCase: value ? caseInfo ?? null : null,
    }),

  toggleSidebar: () => {
    set((state) => {
      const newValue = !state.isSidebarCollapsed;
      try {
        localStorage.setItem('sidebar_collapsed', String(newValue));
      } catch {
        // Ignore localStorage errors
      }
      return { isSidebarCollapsed: newValue };
    });
  },

  togglePDFPanel: () => {
    set((state) => {
      const newValue = !state.isPDFPanelCollapsed;
      try {
        localStorage.setItem('pdf_panel_collapsed', String(newValue));
      } catch {
        // Ignore localStorage errors
      }
      return { isPDFPanelCollapsed: newValue };
    });
  },

  setSidebarCollapsed: (collapsed: boolean) => {
    try {
      localStorage.setItem('sidebar_collapsed', String(collapsed));
    } catch {
      // Ignore localStorage errors
    }
    set({ isSidebarCollapsed: collapsed });
  },

  setPDFPanelCollapsed: (collapsed: boolean) => {
    try {
      localStorage.setItem('pdf_panel_collapsed', String(collapsed));
    } catch {
      // Ignore localStorage errors
    }
    set({ isPDFPanelCollapsed: collapsed });
  },

  setPreferredPrimaryPaneView: (view: 'chat' | 'pdf' | null) => {
    set({ preferredPrimaryPaneView: view });
  },
}));
