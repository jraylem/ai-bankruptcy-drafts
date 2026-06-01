import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AuthLayout, DashboardLayout, StudioV2Layout } from '@/layouts';
import { RootRedirect } from '@/components/routing/RootRedirect';
import { RequirePermission } from '@/components/routing/RequirePermission';
import { APP_PERMISSIONS } from '@/features/auth/permissions';
import { LoginPage } from '@/pages/auth/login';
import { RegisterPage } from '@/pages/auth/register';
import { AcceptInvitePage } from '@/pages/auth/accept-invite';
import { UserApprovalPage } from '@/pages/auth/user-approval';
import { VerifyEmailPage } from '@/pages/auth/verify-email';
import { AnalyticsPage } from '@/pages/analytics';
import { AnalyticsUsersPage } from '@/pages/analytics/users';
import { AnalyticsUserDetailPage } from '@/pages/analytics/users/detail';
import { AnalyticsCasesPage } from '@/pages/analytics/cases';
import { AnalyticsCaseDetailPage } from '@/pages/analytics/cases/detail';
import { AnalyticsMotionsPage } from '@/pages/analytics/motions';
import { AnalyticsMotionSessionDetailPage } from '@/pages/analytics/motions/detail';
import { AnalyticsActivityLogPage } from '@/pages/analytics/activity-log';
import { BillingPage } from '@/pages/billing';
import { BillingCancelPage, BillingSuccessPage } from '@/pages/billing/checkout-return';
import { CaseInboxArchivedPage } from '@/pages/case-inbox/archived';
import { CaseInboxPage } from '@/pages/case-inbox';
import { CostCenterPage } from '@/pages/cost-center';
import { CaseWorkspacePage } from '@/pages/case';
import { OnboardingPage } from '@/pages/onboarding';
import { PricingPage } from '@/pages/pricing';
import { SettingsPage } from '@/pages/settings';
import { StudioPage } from '@/pages/studio';
import { StudioV2Page } from '@/pages/studio-v2';
import { NotFoundPage } from '@/pages/not-found';
import { UnauthorizedPage } from '@/pages/unauthorized';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Navigate to="/dashboard" replace />,
  },
  {
    path: '/pricing',
    element: <PricingPage />,
  },
  {
    path: '/',
    element: <AuthLayout />,
    children: [
      {
        path: 'login',
        element: <LoginPage />,
      },
      {
        path: 'register',
        element: <RegisterPage />,
      },
    ],
  },
  {
    path: '/verify-email',
    element: <VerifyEmailPage />,
  },
  {
    path: '/accept-invite',
    element: <AcceptInvitePage />,
  },
  {
    path: '/user-approval',
    element: <UserApprovalPage />,
  },
  {
    path: '/',
    element: <DashboardLayout />,
    children: [
      {
        index: true,
        element: <RootRedirect />,
      },
      {
        path: 'analytics',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsPage />
          </RequirePermission>
        ),
      },
      {
        path: 'analytics/users',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsUsersPage />
          </RequirePermission>
        ),
      },
      {
        path: 'analytics/users/:userId',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsUserDetailPage />
          </RequirePermission>
        ),
      },
      {
        path: 'analytics/cases',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsCasesPage />
          </RequirePermission>
        ),
      },
      {
        path: 'analytics/cases/:sessionId',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsCaseDetailPage />
          </RequirePermission>
        ),
      },
      {
        path: 'analytics/motions',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsMotionsPage />
          </RequirePermission>
        ),
      },
      {
        path: 'analytics/motions/sessions/:sessionId',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsMotionSessionDetailPage />
          </RequirePermission>
        ),
      },
      {
        path: 'analytics/activity-log',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.analytics}>
            <AnalyticsActivityLogPage />
          </RequirePermission>
        ),
      },
      {
        path: 'billing',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.adminDashboard}>
            <BillingPage />
          </RequirePermission>
        ),
      },
      {
        path: 'billing/success',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.adminDashboard}>
            <BillingSuccessPage />
          </RequirePermission>
        ),
      },
      {
        path: 'billing/cancel',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.adminDashboard}>
            <BillingCancelPage />
          </RequirePermission>
        ),
      },
      {
        path: 'settings',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.adminDashboard}>
            <SettingsPage />
          </RequirePermission>
        ),
      },
      {
        path: 'settings/members',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.manageMembers}>
            <SettingsPage />
          </RequirePermission>
        ),
      },
      {
        path: 'settings/usage',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.adminDashboard}>
            <SettingsPage />
          </RequirePermission>
        ),
      },
      {
        path: 'settings/security',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.adminDashboard}>
            <SettingsPage />
          </RequirePermission>
        ),
      },
      {
        path: 'cost-center',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.adminDashboard}>
            <CostCenterPage />
          </RequirePermission>
        ),
      },
      {
        path: 'inbox',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.caseManagement}>
            <CaseInboxPage />
          </RequirePermission>
        ),
      },
      {
        path: 'inbox/archived',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.caseManagement}>
            <CaseInboxArchivedPage />
          </RequirePermission>
        ),
      },
      {
        path: 'studio',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.motionStudio}>
            <StudioPage />
          </RequirePermission>
        ),
      },
      {
        path: 'studio/template/:templateId',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.motionStudio}>
            <StudioPage />
          </RequirePermission>
        ),
      },
      {
        path: 'case/new',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.caseManagement}>
            <CaseWorkspacePage />
          </RequirePermission>
        ),
      },
      {
        path: 'case/:caseId',
        element: (
          <RequirePermission permission={APP_PERMISSIONS.caseManagement}>
            <CaseWorkspacePage />
          </RequirePermission>
        ),
      },
      {
        path: 'onboarding',
        element: <OnboardingPage />,
      },
      {
        path: 'unauthorized',
        element: <UnauthorizedPage />,
      },
    ],
  },
  {
    path: '/studio-v2',
    element: <StudioV2Layout />,
    children: [
      {
        index: true,
        element: <StudioV2Page />,
      },
      {
        // Template-scoped URL — clicking a template in the rail or
        // opening a completed dry-run card lands here. `?tab=draft`
        // query param signals the Syncfusion preview should open on
        // the Draft tab (filled docx) instead of the Template tab.
        path: ':templateId',
        element: <StudioV2Page />,
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
]);
