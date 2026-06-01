import { useNavigate } from 'react-router-dom';
import { FiArrowLeft, FiHelpCircle } from 'react-icons/fi';
import { UserMenu } from '@/components/layout/UserMenu';

interface StudioV2TopbarProps {
  templateName: string;
  configuredCount: number;
  totalCount: number;
}

export const StudioV2Topbar = ({
  templateName,
  configuredCount,
  totalCount,
}: StudioV2TopbarProps) => {
  const navigate = useNavigate();

  return (
    <header className="flex shrink-0 items-center justify-between gap-4 border-b border-border bg-surface px-5 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-muted"
          aria-label="Back to workspace"
        >
          <FiArrowLeft className="h-3.5 w-3.5" />
          Workspace
        </button>
        <div className="h-5 w-px shrink-0 bg-border" aria-hidden="true" />
        <div className="flex min-w-0 items-center gap-2">
          <p className="shrink-0 text-[11px] font-semibold uppercase tracking-wider text-app-accent-text">
            Template Studio
          </p>
          <span className="hidden h-4 w-px shrink-0 bg-border md:block" aria-hidden="true" />
          <p className="hidden truncate text-sm font-semibold text-text-secondary md:block">
            {templateName}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2">
        <div className="hidden rounded-md border border-border bg-surface-muted/40 px-2.5 py-1 text-right md:block">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-subtle">
            Progress
          </p>
          <p className="text-xs font-semibold text-text-secondary">
            {configuredCount} / {totalCount} fields
          </p>
        </div>
        <button
          type="button"
          disabled
          className="inline-flex cursor-not-allowed items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium text-subtle"
          aria-label="Help"
        >
          <FiHelpCircle className="h-3.5 w-3.5" />
          Help
        </button>
        <div className="ml-1">
          <UserMenu isCollapsed />
        </div>
      </div>
    </header>
  );
};
