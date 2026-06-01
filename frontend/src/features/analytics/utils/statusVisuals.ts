export const STATUS_COLOR = {
  success: '#0f766e',
  warning: '#f59e0b',
  danger: '#ef4444',
  neutral: 'var(--app-chart-axis)',
  neutralMuted: '#cbd5e1',
  neutralSoft: '#e2e8f0',
} as const;

export const CASE_STATUS_COLORS = {
  active: STATUS_COLOR.success,
  pending: STATUS_COLOR.warning,
  denied: STATUS_COLOR.danger,
  archived: STATUS_COLOR.neutralMuted,
  deleted: STATUS_COLOR.neutralSoft,
  inactive: STATUS_COLOR.neutral,
} as const;

export const MOTION_STATUS_COLORS = {
  completed: STATUS_COLOR.success,
  pending: STATUS_COLOR.warning,
  failed: STATUS_COLOR.danger,
  cancelled: STATUS_COLOR.neutral,
} as const;

