import React from 'react';
import { FiDownload } from 'react-icons/fi';
import { KpiSurface } from '@/features/analytics/components/KpiSurface';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { useUserDetailPageContext } from './UserDetailPageContext';
import { formatRelativeActivityTime } from '@/features/analytics/utils/activityFeed.helpers';
import { formatAnalyticsNumber } from '@/features/analytics/utils/dashboard.mappers';
import { formatDateTime, formatDuration } from '@/features/analytics/utils/userDetail.helpers';

export const UserDetailHeaderCard: React.FC = () => {
  const { detail, isExporting, handleExportUserXlsx } = useUserDetailPageContext();

  return (
    <SectionCard
      className="mb-6"
      title={
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold text-text">{detail.name}</h1>
          <p className="mt-1 truncate text-sm text-muted">{detail.email}</p>
        </div>
      }
      action={
        <div className="flex flex-col items-end gap-2 text-right text-xs text-subtle">
          <div>
            <p>Joined {formatDateTime(detail.joined_at)}</p>
            <p>Last active {detail.last_active_at ? formatRelativeActivityTime(detail.last_active_at) : '--'}</p>
          </div>
          <button
            type="button"
            onClick={handleExportUserXlsx}
            disabled={isExporting}
            className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-1.5 text-xs font-semibold text-text-secondary transition hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
          >
            <FiDownload className="h-3.5 w-3.5" />
            {isExporting ? 'Exporting...' : 'Export XLSX'}
          </button>
        </div>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiSurface
          label="Motions Completed (30d)"
          value={formatAnalyticsNumber(detail.motions_completed_30d)}
          iconKey="motionsDrafted"
          valueClass="text-app-success-text"
        />
        <KpiSurface
          label="Success Rate"
          value={`${detail.draft_success_rate.toFixed(1)}%`}
          iconKey="systemStatus"
          valueClass="text-app-accent-text"
        />
        <KpiSurface
          label="Avg Draft Time"
          value={formatDuration(detail.avg_draft_time_seconds)}
          iconKey="pendingCases"
          valueClass="text-app-warning-text"
        />
        <KpiSurface
          label="Sessions Created (30d)"
          value={formatAnalyticsNumber(detail.sessions_created_30d)}
          iconKey="activeCases"
        />
      </div>
    </SectionCard>
  );
};
