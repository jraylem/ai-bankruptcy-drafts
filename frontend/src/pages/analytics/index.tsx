import React from 'react';
import {
  ActiveCasesByDistrictCard,
  ApiCallVolumeCard,
  AnalyticsErrorBanner,
  AnalyticsKpiGrid,
  CasesByIntakeSourceCard,
  CaseStatusCard,
  CasesDailyTrendCard,
  MotionStatusCard,
  MotionsByTypeCard,
  MotionsDailyTrendCard,
  OperationalSnapshotCard,
  RecentActivityCard,
  SystemHealthCard,
  UsersOverviewCard,
} from '@/features/analytics/components/dashboard';
import { AnalyticsLayout } from '@/features/analytics/components/shared';

export const AnalyticsPage: React.FC = () => (
  <AnalyticsLayout title="Analytics Overview">
    <AnalyticsErrorBanner />

    <AnalyticsKpiGrid />

    <section className="mb-8 grid gap-8 xl:grid-cols-2">
      <CasesDailyTrendCard />
      <MotionsDailyTrendCard />
    </section>

    <section className="mb-8 grid gap-8 xl:grid-cols-3">
      <CaseStatusCard />
      <UsersOverviewCard />
      <OperationalSnapshotCard />
    </section>

    <section className="mb-8 grid gap-8 xl:grid-cols-2">
      <CasesByIntakeSourceCard />
      <ActiveCasesByDistrictCard />
    </section>

    <section className="mb-8 grid items-stretch gap-8 xl:grid-cols-3">
      <MotionsByTypeCard />
      <MotionStatusCard />
      <SystemHealthCard />
    </section>

    <section className="mb-8 grid items-stretch gap-8 xl:grid-cols-2">
      <ApiCallVolumeCard />
      <RecentActivityCard />
    </section>
  </AnalyticsLayout>
);
