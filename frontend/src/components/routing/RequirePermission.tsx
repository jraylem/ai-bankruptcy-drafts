import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spinner } from '@/components/common';
import { useAuthSession } from '@/features/auth/queries';
import { hasPermission, type AppPermission } from '@/features/auth/permissions';

export const RequirePermission = ({
  children,
  permission,
}: {
  children: React.ReactNode;
  permission: AppPermission;
}) => {
  const { isInitializing, user } = useAuthSession();
  const location = useLocation();

  if (isInitializing) {
    return (
      <div className="h-screen bg-page flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!hasPermission(user, permission)) {
    return <Navigate to="/unauthorized" replace state={{ from: location }} />;
  }

  return <>{children}</>;
};
