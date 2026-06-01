import type {
  AnalyticsKpiCard,
  DashboardAnalyticsResponse,
} from '../types/dashboard.types';

type AnalyticsNumberOptions = Intl.NumberFormatOptions & {
  fallback?: string;
};

export const formatAnalyticsNumber = (
  value: number | string | null | undefined,
  options: AnalyticsNumberOptions = {},
) => {
  const { fallback = '0', ...intlOptions } = options;

  if (value === null || value === undefined || value === '') {
    return fallback;
  }

  const numericValue =
    typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Number(value.replace(/,/g, ''))
        : Number.NaN;

  if (!Number.isFinite(numericValue)) {
    return String(value);
  }

  return new Intl.NumberFormat('en-US', intlOptions).format(numericValue);
};

export const formatCompactNumber = (value: number) =>
  formatAnalyticsNumber(value, { maximumFractionDigits: 0 });

export const formatAnalyticsRangeLabel = (start: string, end: string) => {
  const format = (value: string) =>
    new Date(value).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });

  return `${format(start)} - ${format(end)}`;
};

export const mapDashboardKpiCards = (analytics: DashboardAnalyticsResponse): AnalyticsKpiCard[] => [
  {
    label: 'Total Cases',
    value: formatCompactNumber(analytics.cases.total),
    iconKey: 'totalCases',
  },
  {
    label: 'Active Cases',
    value: formatCompactNumber(analytics.cases.active_cases.sum),
    valueClass: 'text-indigo-600',
    iconKey: 'activeCases',
  },
  {
    label: 'Pending Cases',
    value: formatCompactNumber(analytics.cases.pending_cases),
    valueClass: 'text-amber-500',
    iconKey: 'pendingCases',
  },
  {
    label: 'Total Users',
    value: formatCompactNumber(analytics.users.total),
    iconKey: 'totalUsers',
  },
  {
    label: 'New Users',
    value: formatCompactNumber(analytics.users.new_in_range),
    valueClass: 'text-emerald-500',
    iconKey: 'newUsers',
  },
  {
    label: 'Motions Drafted',
    value: formatCompactNumber(analytics.motions.total),
    valueClass: 'text-violet-600',
    iconKey: 'motionsDrafted',
  },
];
