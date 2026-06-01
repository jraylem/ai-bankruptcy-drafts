import React, { useEffect, useMemo, useState } from 'react';
import { FiArrowLeft } from 'react-icons/fi';
import { useNavigate, useParams } from 'react-router-dom';
import { SidebarLayout } from '@/components/layout/SidebarLayout';
import {
  UserDetailActivityCard,
  UserDetailChartsSection,
  UserDetailHeaderCard,
  UserDetailPageContext,
  UserDetailPageSkeleton,
  UserDetailSecondaryKpisSection,
  UserDetailSessionsCard,
} from '@/features/analytics/components/users/detail';
import { useDashboardAnalyticsUserDetail } from '@/features/analytics/hooks/useDashboardAnalyticsUserDetail';
import { useDashboardAnalyticsUserDetailExport } from '@/features/analytics/hooks/useDashboardAnalyticsUserDetailExport';
import type {
  DashboardUsersDetailExportQuery,
  UserDetailActivityQueryState,
  UserDetailSessionsQueryState,
} from '@/features/analytics/types';

const DEFAULT_SESSIONS_QUERY: UserDetailSessionsQueryState = {
  page: 1,
  pageSize: 10,
  search: '',
  source: '',
  status: '',
  sortBy: 'last_activity',
  sortDir: 'desc',
};

const DEFAULT_ACTIVITY_QUERY: UserDetailActivityQueryState = {
  page: 1,
  pageSize: 10,
  search: '',
  action: '',
  status: '',
  sortBy: 'occurred',
  sortDir: 'desc',
};

export const AnalyticsUserDetailPage: React.FC = () => {
  const navigate = useNavigate();
  const { userId } = useParams<{ userId: string }>();
  const [sessionsQuery, setSessionsQuery] = useState<UserDetailSessionsQueryState>(DEFAULT_SESSIONS_QUERY);
  const [activityQuery, setActivityQuery] = useState<UserDetailActivityQueryState>(DEFAULT_ACTIVITY_QUERY);

  useEffect(() => {
    setSessionsQuery(DEFAULT_SESSIONS_QUERY);
    setActivityQuery(DEFAULT_ACTIVITY_QUERY);
  }, [userId]);

  const detailQuery = useMemo(
    () => ({
      sessions_page: sessionsQuery.page,
      sessions_page_size: sessionsQuery.pageSize,
      ...(sessionsQuery.search ? { sessions_search: sessionsQuery.search } : {}),
      ...(sessionsQuery.source ? { sessions_source: sessionsQuery.source } : {}),
      ...(sessionsQuery.status ? { sessions_status: sessionsQuery.status } : {}),
      sessions_sort_by: sessionsQuery.sortBy,
      sessions_sort_dir: sessionsQuery.sortDir,

      activity_page: activityQuery.page,
      activity_page_size: activityQuery.pageSize,
      ...(activityQuery.search ? { activity_search: activityQuery.search } : {}),
      ...(activityQuery.action ? { activity_action: activityQuery.action } : {}),
      ...(activityQuery.status ? { activity_status: activityQuery.status } : {}),
      activity_sort_by: activityQuery.sortBy,
      activity_sort_dir: activityQuery.sortDir,
    }),
    [activityQuery, sessionsQuery]
  );

  const {
    data: detail,
    isLoading,
    error,
  } = useDashboardAnalyticsUserDetail(userId ?? null, detailQuery, Boolean(userId));

  useEffect(() => {
    if (!detail) {
      return;
    }

    const sessionsTotalPages = Math.max(
      1,
      Math.ceil(detail.recent_sessions_pagination.total / detail.recent_sessions_pagination.page_size)
    );

    if (sessionsQuery.page > sessionsTotalPages) {
      setSessionsQuery((previous) => ({ ...previous, page: sessionsTotalPages }));
    }

    const activityTotalPages = Math.max(
      1,
      Math.ceil(detail.recent_activity_pagination.total / detail.recent_activity_pagination.page_size)
    );

    if (activityQuery.page > activityTotalPages) {
      setActivityQuery((previous) => ({ ...previous, page: activityTotalPages }));
    }
  }, [detail, sessionsQuery.page, activityQuery.page]);

  const exportQuery = useMemo<DashboardUsersDetailExportQuery>(
    () => ({
      sessions_page: sessionsQuery.page,
      sessions_page_size: sessionsQuery.pageSize,
      ...(sessionsQuery.search ? { sessions_search: sessionsQuery.search } : {}),
      ...(sessionsQuery.source ? { sessions_source: sessionsQuery.source } : {}),
      ...(sessionsQuery.status ? { sessions_status: sessionsQuery.status } : {}),
      sessions_sort_by: sessionsQuery.sortBy === 'district' ? 'last_activity' : sessionsQuery.sortBy,
      sessions_sort_dir: sessionsQuery.sortDir,

      activity_page: activityQuery.page,
      activity_page_size: activityQuery.pageSize,
      ...(activityQuery.search ? { activity_search: activityQuery.search } : {}),
      ...(activityQuery.action ? { activity_action: activityQuery.action } : {}),
      activity_sort_by:
        activityQuery.sortBy === 'status' || activityQuery.sortBy === 'entity'
          ? 'occurred'
          : activityQuery.sortBy,
      activity_sort_dir: activityQuery.sortDir,
    }),
    [activityQuery, sessionsQuery]
  );

  const { isExporting, handleExportUserXlsx } = useDashboardAnalyticsUserDetailExport({
    userName: detail?.name,
    userEmail: detail?.email,
    query: exportQuery,
  });

  if (!userId) {
    return (
      <SidebarLayout sidebarVariant="analytics" className="bg-page" contentClassName="overflow-y-auto">
        <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Missing user id.
          </div>
        </div>
      </SidebarLayout>
    );
  }

  return (
    <SidebarLayout sidebarVariant="analytics" className="bg-page" contentClassName="overflow-y-auto">
      <div className="mx-auto w-full max-w-[1600px] px-6 py-8 pb-16 xl:px-8">
        <div className="mb-5 flex items-center gap-2 text-xs text-muted">
          <button
            type="button"
            onClick={() => navigate('/analytics/users')}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 font-medium text-text-secondary transition hover:bg-surface-muted"
          >
            <FiArrowLeft className="h-3.5 w-3.5" />
            Back to Users
          </button>
        </div>

        {error ? (
          <div className="rounded-2xl border border-app-danger-text/30 bg-app-danger-soft px-4 py-3 text-sm text-app-danger-text">
            Failed to load user detail: {error.message}
          </div>
        ) : isLoading || !detail ? (
          <UserDetailPageSkeleton />
        ) : (
          <UserDetailPageContext.Provider
            value={{
              detail,
              sessionsQuery,
              setSessionsQuery,
              activityQuery,
              setActivityQuery,
              isExporting,
              handleExportUserXlsx,
            }}
          >
            <UserDetailHeaderCard />
            <UserDetailChartsSection />
            <UserDetailSecondaryKpisSection />
            <UserDetailSessionsCard />
            <UserDetailActivityCard />
          </UserDetailPageContext.Provider>
        )}
      </div>
    </SidebarLayout>
  );
};
