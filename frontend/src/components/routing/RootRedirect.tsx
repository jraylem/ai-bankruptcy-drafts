import React from 'react';
import { Navigate } from 'react-router-dom';

import { Spinner } from '@/components/common';
import { useAuthSession } from '@/features/auth/queries';
import {
  APP_PERMISSIONS,
  getDefaultAuthorizedPath,
  hasPermission,
} from '@/features/auth/permissions';
import { useStudioStore } from '@/stores/useStudioStore';

/**
 * Resolves the root path `/` into a real workspace URL.
 *
 *   cases loaded + present → /case/:latest-id  (most-recently-created)
 *   cases loaded + empty   → /case/new          (drop-zone for first upload)
 *   cases still loading    → spinner            (DashboardLayout bootstraps the list)
 *
 * `cases` is populated by DashboardLayout's mount-effect (`loadCases()`), so by
 * the time this component renders we're either mid-fetch or done. We pick
 * `cases[0]` because the API returns cases ordered by `created_at DESC`.
 */
export const RootRedirect: React.FC = () => {
  const { user } = useAuthSession();
  const cases = useStudioStore((s) => s.cases);
  const isLoadingCases = useStudioStore((s) => s.isLoadingCases);

  if (!hasPermission(user, APP_PERMISSIONS.caseManagement)) {
    return <Navigate to={getDefaultAuthorizedPath(user)} replace />;
  }

  if (isLoadingCases && cases.length === 0) {
    return (
      <div className="h-screen bg-page flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (cases.length === 0) {
    return <Navigate to="/case/new" replace />;
  }

  return <Navigate to={`/case/${cases[0].id}`} replace />;
};
