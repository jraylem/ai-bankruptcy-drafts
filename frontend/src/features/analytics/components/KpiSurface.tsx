import React from 'react';
import {
  FiActivity,
  FiArchive,
  FiClock,
  FiFileText,
  FiFolder,
  FiShield,
  FiUserPlus,
  FiUsers,
} from 'react-icons/fi';
import type { AnalyticsKpiCard } from '../types/dashboard.types';
import { InlineValueSkeleton } from './AnalyticsSkeleton';

interface KpiSurfaceProps extends AnalyticsKpiCard {
  loading?: boolean;
  helperText?: string;
  footer?: React.ReactNode;
}

const KPI_ICONS = {
  totalCases: FiFolder,
  activeCases: FiActivity,
  pendingCases: FiClock,
  inactiveCases: FiArchive,
  totalUsers: FiUsers,
  newUsers: FiUserPlus,
  motionsDrafted: FiFileText,
  systemStatus: FiShield,
} as const;

export const KpiSurface: React.FC<KpiSurfaceProps> = ({
  label,
  value,
  valueClass,
  iconKey,
  loading = false,
  helperText,
  footer,
}) => {
  const Icon = iconKey ? KPI_ICONS[iconKey] : null;

  return (
    <div className="rounded-2xl bg-surface p-5">
      <div className="mb-2 flex items-center gap-2">
        {Icon ? <Icon className="h-3.5 w-3.5 text-subtle" /> : null}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-subtle">{label}</p>
      </div>
      {loading ? (
        <InlineValueSkeleton className="mt-2 h-8 w-16" />
      ) : (
        <h3 className={`font-poppins text-2xl font-bold tracking-tight ${valueClass ?? 'text-text'}`}>
          {value}
        </h3>
      )}
      {helperText ? <p className="mt-1 text-[11px] leading-4 text-subtle">{helperText}</p> : null}
      {footer ? <div className="mt-2">{footer}</div> : null}
    </div>
  );
};
