import React from 'react';
import { FiCalendar, FiCheckCircle, FiDownload, FiUser } from 'react-icons/fi';
import { SectionCard } from '@/features/analytics/components/SectionCard';
import { useUserDetailPageContext } from './UserDetailPageContext';

export const UserDetailSecondaryKpisSection: React.FC = () => {
  const { detail } = useUserDetailPageContext();

  return (
    <section className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <SectionCard
        title={
          <div className="flex items-center gap-2 text-sm">
            <FiCalendar className="h-4 w-4 text-app-accent" />
            <span>Active Days</span>
          </div>
        }
      >
        <p className="text-2xl font-semibold text-text">{detail.active_days_30d}</p>
        <p className="mt-1 text-xs text-subtle">In the past 30 days</p>
      </SectionCard>
      <SectionCard
        title={
          <div className="flex items-center gap-2 text-sm">
            <FiUser className="h-4 w-4 text-app-accent" />
            <span>Logins</span>
          </div>
        }
      >
        <p className="text-2xl font-semibold text-text">{detail.login_count_30d}</p>
        <p className="mt-1 text-xs text-subtle">Successful logins (30d)</p>
      </SectionCard>
      <SectionCard
        title={
          <div className="flex items-center gap-2 text-sm">
            <FiDownload className="h-4 w-4 text-app-accent" />
            <span>Docs Exported</span>
          </div>
        }
      >
        <p className="text-2xl font-semibold text-text">{detail.documents_exported_30d}</p>
        <p className="mt-1 text-xs text-subtle">Generated files exported (30d)</p>
      </SectionCard>
      <SectionCard
        title={
          <div className="flex items-center gap-2 text-sm">
            <FiCheckCircle className="h-4 w-4 text-app-accent" />
            <span>Motions Started</span>
          </div>
        }
      >
        <p className="text-2xl font-semibold text-text">{detail.motions_started_30d}</p>
        <p className="mt-1 text-xs text-subtle">Draft attempts (30d)</p>
      </SectionCard>
    </section>
  );
};
