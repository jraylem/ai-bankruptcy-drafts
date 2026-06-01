import { useState } from 'react';
import type { MouseEvent } from 'react';
import {
  exportDashboardAnalyticsUserXlsx,
  exportDashboardAnalyticsUsersXlsx,
} from '@/features/analytics/api/users.api';
import type {
  DashboardAnalyticsFilters,
  DashboardUsersAnalyticsSortBy,
  DashboardUsersAnalyticsUser,
  SortDirection,
} from '@/features/analytics/types';
import {
  downloadExportBlob,
  getDisplayName,
  sanitizeFilenameToken,
} from '@/features/analytics/utils/usersList.helpers';
import type { ToastType } from '@/stores/useToastStore';

interface UseUsersExportActionsOptions {
  addToast: (message: string, type?: ToastType) => void;
  analyticsFilters: DashboardAnalyticsFilters;
  searchQuery: string;
  sortBy: DashboardUsersAnalyticsSortBy;
  sortDir: SortDirection;
}

export const useUsersExportActions = ({
  addToast,
  analyticsFilters,
  searchQuery,
  sortBy,
  sortDir,
}: UseUsersExportActionsOptions) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportingUserId, setExportingUserId] = useState<string | null>(null);

  const handleExportUsersXlsx = async () => {
    if (isExporting || exportingUserId) {
      return;
    }

    try {
      setIsExporting(true);
      const blob = await exportDashboardAnalyticsUsersXlsx(analyticsFilters, {
        sort_by: sortBy,
        sort_dir: sortDir,
        ...(searchQuery ? { search: searchQuery } : {}),
      });

      const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const fallbackFilename = `users_${analyticsFilters.range}_${today}.xlsx`;
      downloadExportBlob(blob, fallbackFilename);
      addToast('Users export started (.xlsx).', 'success');
    } catch (exportError) {
      addToast(
        exportError instanceof Error ? exportError.message : 'Failed to export users data',
        'error'
      );
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportSingleUserXlsx = async (
    user: DashboardUsersAnalyticsUser,
    event: MouseEvent<HTMLButtonElement>
  ) => {
    event.stopPropagation();

    if (isExporting || exportingUserId) {
      return;
    }

    try {
      setExportingUserId(user.user_id);
      const blob = await exportDashboardAnalyticsUserXlsx(user.user_id, analyticsFilters);

      const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const safeUser = sanitizeFilenameToken(getDisplayName(user));
      const fallbackFilename = `user_${safeUser}_${analyticsFilters.range}_${today}.xlsx`;
      downloadExportBlob(blob, fallbackFilename);
      addToast(`Export started for ${getDisplayName(user)} (.xlsx).`, 'success');
    } catch (exportError) {
      addToast(
        exportError instanceof Error ? exportError.message : 'Failed to export user data',
        'error'
      );
    } finally {
      setExportingUserId(null);
    }
  };

  return {
    exportingUserId,
    handleExportSingleUserXlsx,
    handleExportUsersXlsx,
    isExporting,
  };
};
