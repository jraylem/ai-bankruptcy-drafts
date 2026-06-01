import React from 'react';
import { FiLock } from 'react-icons/fi';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/common';
import { useAuthSession } from '@/features/auth/queries';
import { getDefaultAuthorizedPath } from '@/features/auth/permissions';

export const UnauthorizedPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthSession();

  return (
    <div className="flex min-h-screen w-full flex-1 items-center justify-center bg-page px-4">
      <div className="max-w-md text-center">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-app-danger-soft text-app-danger-text">
          <FiLock className="h-6 w-6" />
        </div>
        <h1 className="mt-5 font-poppins text-3xl font-semibold text-text">Not authorized</h1>
        <p className="mb-8 mt-3 text-sm leading-6 text-muted">
          Your account does not have permission to access this area. Contact a firm admin if you
          need access.
        </p>
        <Button onClick={() => navigate(getDefaultAuthorizedPath(user))} className="mx-auto">
          Go to workspace
        </Button>
      </div>
    </div>
  );
};
