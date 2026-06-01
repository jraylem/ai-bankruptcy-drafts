import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthSession } from '@/features/auth/queries';
import { Spinner } from '@/components/common';

export const AuthLayout: React.FC = () => {
  const { isAuthenticated, isInitializing } = useAuthSession();

  // Show loading state while checking the server-backed session.
  if (isInitializing) {
    return (
      <div className="flex h-screen items-center justify-center bg-page">
        <Spinner size="lg" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
};
