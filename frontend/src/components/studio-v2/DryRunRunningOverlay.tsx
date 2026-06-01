import { FiX } from 'react-icons/fi';
import { RunningAnimation } from './RunningAnimation';

interface DryRunRunningOverlayProps {
  isOpen: boolean;
  caseLabel?: string | null;
}

/**
 * Full-screen overlay shown during the INITIAL dry-run phase — i.e.
 * after the paralegal picked a case but before the BE returns either
 * `awaiting_input` (modal opens) or `completed` (Draft tab opens).
 *
 * The matching in-modal hero for the RESUME phase lives inside
 * `AwaitingInputModalV2` (see its `busy` branch). Both reuse
 * `<RunningAnimation>` so the visual vocabulary stays consistent.
 */
export const DryRunRunningOverlay = ({
  isOpen,
  caseLabel,
}: DryRunRunningOverlayProps) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay backdrop-blur-sm">
      <div className="relative flex w-full max-w-xl flex-col items-center gap-4 rounded-2xl border border-app-accent-soft bg-surface px-8 py-8 shadow-2xl">
        <button
          type="button"
          disabled
          title="Dry-run is in progress — please wait."
          className="absolute right-4 top-4 cursor-not-allowed rounded-lg p-1 text-subtle opacity-40"
          aria-label="Close"
        >
          <FiX className="h-5 w-5" />
        </button>
        <RunningAnimation phase="initial" caseLabel={caseLabel} size="xl" />
      </div>
    </div>
  );
};
