import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { exportDashboardAnalyticsUserXlsx } from '@/features/analytics/api/users.api';
import type { DashboardUsersDetailExportQuery } from '@/features/analytics/types';
import { downloadExportBlob, sanitizeFilenameToken } from '@/features/analytics/utils/userDetail.helpers';
import { useAnalyticsQueryFilters } from '@/features/analytics/hooks/useAnalyticsQueryFilters';
import { useToastStore } from '@/stores/useToastStore';

interface UseDashboardAnalyticsUserDetailExportArgs {
  userName?: string;
  userEmail?: string;
  query?: DashboardUsersDetailExportQuery;
}

export const useDashboardAnalyticsUserDetailExport = (
  args: UseDashboardAnalyticsUserDetailExportArgs = {}
) => {
  const { userId } = useParams<{ userId: string }>();
  const analyticsFilters = useAnalyticsQueryFilters();
  const addToast = useToastStore((state) => state.addToast);
  const [isExporting, setIsExporting] = useState(false);

  const handleExportUserXlsx = async () => {
    if (!userId || isExporting) {
      return;
    }

    try {
      setIsExporting(true);
      const blob = await exportDashboardAnalyticsUserXlsx(userId, analyticsFilters, args.query ?? {});

      const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const safeUser = sanitizeFilenameToken(args.userName || args.userEmail || userId);
      const fallbackFilename = `user_${safeUser}_${analyticsFilters.range}_${today}.xlsx`;
      downloadExportBlob(blob, fallbackFilename);
      addToast(`Export started for ${args.userName || 'selected user'} (.xlsx).`, 'success');
    } catch (exportError) {
      addToast(exportError instanceof Error ? exportError.message : 'Failed to export user data', 'error');
    } finally {
      setIsExporting(false);
    }
  };

  return {
    isExporting,
    handleExportUserXlsx,
  };
};
