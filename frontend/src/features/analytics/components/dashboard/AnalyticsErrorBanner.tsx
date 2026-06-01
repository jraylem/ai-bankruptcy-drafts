import React from 'react';
import { useDashboardApiCalls } from '../../hooks/useDashboardApiCalls';
import { useDashboardCases } from '../../hooks/useDashboardCases';
import { useDashboardMotions } from '../../hooks/useDashboardMotions';
import { useDashboardUsers } from '../../hooks/useDashboardUsers';

export const AnalyticsErrorBanner: React.FC = () => {
  const { error: apiCallsError } = useDashboardApiCalls();
  const { error: casesError } = useDashboardCases();
  const { error: usersError } = useDashboardUsers();
  const { error: motionsError } = useDashboardMotions();

  const error = apiCallsError ?? casesError ?? usersError ?? motionsError;

  if (!error) {
    return null;
  }

  return (
    <div className="mb-6 rounded-[20px] border border-app-danger-text/30 bg-app-danger-soft px-5 py-4 text-sm font-medium text-app-danger-text">
      {error instanceof Error ? error.message : 'Failed to load dashboard analytics'}
    </div>
  );
};
