import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthSession } from '@/features/auth/queries';
import { Spinner } from '@/components/common';

export const StudioV2Layout: React.FC = () => {
  const { isAuthenticated, isInitializing } = useAuthSession();

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

  return (
    <div className="h-screen bg-page overflow-hidden">
      <Outlet />
    </div>
  );
};
