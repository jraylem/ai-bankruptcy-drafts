import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/common';

export const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen items-center justify-center bg-page px-4">
      <div className="text-center">
        <h1 className="text-9xl font-bold text-indigo-600">404</h1>
        <h2 className="mt-4 text-3xl font-semibold text-text">Page Not Found</h2>
        <p className="mb-8 mt-4 text-muted">
          Sorry, the page you're looking for doesn't exist.
        </p>
        <Button onClick={() => navigate('/')} className="mx-auto">
          Go to workspace
        </Button>
      </div>
    </div>
  );
};
