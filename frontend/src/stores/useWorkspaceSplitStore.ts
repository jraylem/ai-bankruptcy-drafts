/**
 * Tracks the secondary (right-hand) pane of the split-screen case
 * workspace. Pulled into its own store so the sidebar can highlight
 * the case in the right pane without prop-drilling through the layout.
 *
 * The primary (left) pane is URL-bound and tracked via
 * `useStudioStore.selectedCaseId` — this store ONLY holds the
 * secondary pane's caseId. In-memory only by design: reload collapses
 * the split back to the single primary pane.
 */

import { create } from 'zustand';

export type WorkspacePaneRole = 'primary' | 'secondary';

interface WorkspaceSplitState {
  secondaryCaseId: string | null;
  /**
   * Which pane the user is currently interacting with. Drives the
   * checkmark/active indicator on the sidebar so it follows focus,
   * not just the URL.
   */
  focusedPane: WorkspacePaneRole;
  setSecondaryCaseId: (caseId: string | null) => void;
  closeSecondary: () => void;
  setFocusedPane: (role: WorkspacePaneRole) => void;
}

export const useWorkspaceSplitStore = create<WorkspaceSplitState>((set) => ({
  secondaryCaseId: null,
  focusedPane: 'primary',
  setSecondaryCaseId: (caseId) => set({ secondaryCaseId: caseId }),
  // Closing the secondary always returns focus to the primary so the
  // sidebar checkmark doesn't linger on a pane that no longer exists.
  closeSecondary: () => set({ secondaryCaseId: null, focusedPane: 'primary' }),
  setFocusedPane: (role) => set({ focusedPane: role }),
}));
