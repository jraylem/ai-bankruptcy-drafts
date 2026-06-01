import React from 'react';
import { FiTrendingUp } from 'react-icons/fi';
import { useDashboardCases } from '../../hooks/useDashboardCases';
import { useDashboardMotions } from '../../hooks/useDashboardMotions';
import { useDashboardUsers } from '../../hooks/useDashboardUsers';
import { InlineValueSkeleton, SkeletonBlock } from '../AnalyticsSkeleton';
import { formatCompactNumber } from '../../utils/dashboard.mappers';
import { formatDistrictLabel } from '../../utils/districtLabels';

export const OperationalSnapshotCard: React.FC = () => {
  const { data: cases, isLoading: isCasesLoading } = useDashboardCases();
  const { data: users, isLoading: isUsersLoading } = useDashboardUsers();
  const { data: motions, isLoading: isMotionsLoading } = useDashboardMotions();
  const isLoading =
    isCasesLoading || isUsersLoading || isMotionsLoading || !cases || !users || !motions;

  const districtActive = cases?.by_district_active;
  const activeCases = cases?.active_cases;
  const inactiveCases = cases?.inactive_cases;
  const districtEntries = [
    { code: 'flnb', value: districtActive?.flnb ?? 0 },
    { code: 'flmb', value: districtActive?.flmb ?? 0 },
    { code: 'flsb', value: districtActive?.flsb ?? 0 },
    { code: 'pawb', value: districtActive?.pawb ?? 0 },
    { code: 'other', value: districtActive?.other ?? 0 },
  ];
  const topDistrict = districtEntries.sort((a, b) => b.value - a.value)[0];
  const intakeEntries = [
    { label: 'Manual', value: activeCases?.manual ?? 0 },
    { label: 'Summoned', value: activeCases?.summoned ?? 0 },
    { label: 'Converted from Pending', value: activeCases?.from_pending ?? 0 },
  ];
  const topIntakeSource = intakeEntries.sort((a, b) => b.value - a.value)[0];
  const districtCoverage = districtEntries.filter((item) => item.value > 0).length;
  const highlights = [
    {
      label: 'Most Active District',
      value: formatDistrictLabel(topDistrict?.code, { fallback: 'N/A' }),
      detail: `${formatCompactNumber(topDistrict?.value ?? 0)} active cases`,
    },
    {
      label: 'Primary Intake Source',
      value: topIntakeSource?.label ?? 'N/A',
      detail: `${formatCompactNumber(topIntakeSource?.value ?? 0)} active cases entered this way`,
    },
    {
      label: 'District Coverage',
      value: formatCompactNumber(districtCoverage),
      detail: `${formatCompactNumber(districtCoverage)} ${
        districtCoverage === 1 ? 'district' : 'districts'
      } currently have active cases`,
    },
    {
      label: 'Inactive Cases',
      value: formatCompactNumber(inactiveCases?.sum ?? 0),
      detail: `${formatCompactNumber(inactiveCases?.denied ?? 0)} denied, ${formatCompactNumber(
        inactiveCases?.archived ?? 0,
      )} archived, ${formatCompactNumber(inactiveCases?.deleted ?? 0)} deleted`,
    },
  ];

  return (
    <section className="h-full rounded-2xl bg-linear-to-br from-indigo-600 via-violet-600 to-fuchsia-500 p-6 text-white">
      <div className="mb-5 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/16 text-white backdrop-blur-sm">
          <FiTrendingUp className="h-5 w-5" />
        </div>
        <div>
          <h4 className="font-poppins text-lg font-semibold text-white">Highlights</h4>
          <p className="text-xs text-violet-100">Live snapshot from current dashboard metrics</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {highlights.map((item) => (
          <div
            key={item.label}
            className="rounded-[18px] border border-white/15 bg-white/10 px-4 py-3 backdrop-blur-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-violet-100/80">
                  {item.label}
                </p>
                {isLoading ? (
                  <InlineValueSkeleton className="mt-2 h-5 w-24 bg-white/25" />
                ) : (
                  <p className="mt-1 text-[15px] font-semibold leading-5 text-white">
                    {item.value}
                  </p>
                )}
              </div>
            </div>
            {isLoading ? (
              <SkeletonBlock className="mt-2 h-8 w-full rounded-xl bg-white/20" />
            ) : (
              <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-violet-100/85">
                {item.detail}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
};
