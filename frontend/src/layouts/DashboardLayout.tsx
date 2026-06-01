import React, { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthSession } from '@/features/auth/queries';
import { APP_PERMISSIONS, hasPermission } from '@/features/auth/permissions';
import { useOnboardingStatusQuery } from '@/features/onboarding/queries';
import { useStudioStore } from '@/stores/useStudioStore';
import { Spinner } from '@/components/common';
import { AiInsightsChatWidget } from '@/features/analytics/sections/ai-insights/AiInsightsChatWidget';

export const DashboardLayout: React.FC = () => {
  const { isAuthenticated, isInitializing, user } = useAuthSession();
  const location = useLocation();
  const loadCases = useStudioStore((s) => s.loadCases);
  const isEmbedded = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('embedded') === '1';
  const isAnalyticsRoute =
    location.pathname === '/analytics' || location.pathname.startsWith('/analytics/');
  const canAccessAnalytics = hasPermission(user, APP_PERMISSIONS.analytics);
  const canAccessCases = hasPermission(user, APP_PERMISSIONS.caseManagement);
  const isOnboardingRoute = location.pathname === '/onboarding';
  const hasFirm = Boolean(user?.firm_id);
  const onboardingStatusQuery = useOnboardingStatusQuery(Boolean(isAuthenticated && hasFirm));
  const fallbackOnboardingStatus =
    user?.onboarding_status === 'pending' || user?.onboarding_status === 'completed'
      ? user.onboarding_status
      : undefined;
  const onboardingStatus = onboardingStatusQuery.data ?? fallbackOnboardingStatus;
  const isOnboardingPending = onboardingStatus === 'pending';
  const isOnboardingCompleted = onboardingStatus === 'completed';
  const isCheckingOnboarding = hasFirm && onboardingStatusQuery.isLoading && !onboardingStatus;

  useEffect(() => {
    if (!isEmbedded && isAuthenticated && user?.id && isOnboardingCompleted && canAccessCases) {
      // Bootstrap the case list once at the protected-layout level so the
      // RootRedirect at `/` has cases available without waiting for the
      // workspace page to mount. Idempotent — repeats are cheap.
      void loadCases();
    }
  }, [canAccessCases, isAuthenticated, isEmbedded, isOnboardingCompleted, user?.id, loadCases]);

  // Show loading state while checking the server-backed session.
  if (isInitializing) {
    return (
      <div className="h-screen bg-page flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (isCheckingOnboarding) {
    return (
      <div className="h-screen bg-page flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if ((!hasFirm || isOnboardingPending) && !isOnboardingRoute) {
    return <Navigate to="/onboarding" replace />;
  }

  if (isOnboardingCompleted && isOnboardingRoute) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="h-screen bg-page flex overflow-hidden">
      <Outlet />
      <AiInsightsChatWidget isVisible={canAccessAnalytics && isAnalyticsRoute} />
    </div>
  );
};
