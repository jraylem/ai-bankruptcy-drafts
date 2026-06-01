import React from 'react';
import { formatAnalyticsNumber } from '../utils/dashboard.mappers';

interface AnalyticsChartTooltipProps {
  active?: boolean;
  label?: string | number;
  payload?: Array<{
    color?: string;
    dataKey?: string;
    name?: string;
    value?: number | string;
    payload?: {
      name?: string;
      label?: string;
    };
  }>;
}

const formatMetricLabel = (value?: string) => {
  if (!value) return 'Value';

  const normalizedKey = value.trim().toLowerCase();
  const labelMap: Record<string, string> = {
    active: 'Active Cases',
    inactive: 'Inactive Cases',
    pending: 'Pending',
    completed: 'Completed',
    cancelled: 'Cancelled',
    failed: 'Failed',
    success: 'Successful Calls',
    error: 'Errors',
    total: 'Total',
  };

  if (labelMap[normalizedKey]) {
    return labelMap[normalizedKey];
  }

  return value
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const isZeroLikeValue = (value: number | string | undefined) => {
  if (typeof value === 'number') {
    return Number.isFinite(value) && value === 0;
  }

  if (typeof value === 'string') {
    const normalized = value.trim();
    if (/^-?\d+(\.\d+)?$/.test(normalized)) {
      const numericValue = Number(normalized);
      return Number.isFinite(numericValue) && numericValue === 0;
    }
  }

  return false;
};

const formatTooltipValue = (value?: number | string) => {
  if (typeof value === 'number') {
    return formatAnalyticsNumber(value, {
      maximumFractionDigits: Number.isInteger(value) ? 0 : 1,
    });
  }

  if (typeof value === 'string') {
    const normalized = value.trim();
    if (/^-?\d+(\.\d+)?$/.test(normalized)) {
      const numericValue = Number(normalized);
      return formatAnalyticsNumber(numericValue, {
        maximumFractionDigits: Number.isInteger(numericValue) ? 0 : 1,
      });
    }
  }

  return value ?? '--';
};

export const AnalyticsChartTooltip: React.FC<AnalyticsChartTooltipProps> = ({
  active,
  label,
  payload,
}) => {
  if (!active || !payload?.length) return null;

  const visiblePayload = payload.filter((entry) => !isZeroLikeValue(entry.value));
  if (!visiblePayload.length) return null;

  return (
    <div className="min-w-[112px] rounded-xl border border-border/70 bg-surface-muted/95 px-3 py-2.5 shadow-[0_18px_42px_rgba(15,23,42,0.14)] backdrop-blur-sm">
      {label ? <p className="text-[11px] font-semibold leading-4 text-text">{label}</p> : null}
      <div className={`${label ? 'mt-1.5' : ''} space-y-1`}>
        {visiblePayload.map((entry, index) => {
          const metricLabel = formatMetricLabel(
            entry.name || entry.payload?.name || entry.payload?.label || entry.dataKey
          );

          return (
            <div
              key={`${metricLabel}-${index}`}
              className="flex items-center gap-1.5 text-[10px] leading-4"
            >
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: entry.color || 'var(--app-accent)' }}
              />
              <span className="font-medium text-muted">{metricLabel}</span>
              <span className="text-subtle">:</span>
              <span className="font-semibold text-app-accent-text">
                {formatTooltipValue(entry.value)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
