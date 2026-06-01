import type {
  DashboardActivityLogEntityType,
  DashboardActivityLogEntry,
  DashboardActivityMetadataValue,
} from '@/features/analytics/types/dashboard.types';
import { ANALYTICS_TABLE_PAGE_SIZE_OPTIONS, toAnalyticsTitleCase } from './common.helpers';

export type ActivityLogSortKey = 'time' | 'actor' | 'action' | 'status' | 'duration';
export type ActivityLogSortDirection = 'asc' | 'desc';

export const ACTIVITY_LOG_PAGE_SIZE_OPTIONS = ANALYTICS_TABLE_PAGE_SIZE_OPTIONS;

export const ACTIVITY_LOG_ENTITY_TYPE_OPTIONS: Array<{
  label: string;
  value: DashboardActivityLogEntityType | '';
}> = [
  { label: 'All entity types', value: '' },
  { label: 'Motion', value: 'motion' },
  { label: 'Case', value: 'case' },
  { label: 'PDF', value: 'pdf' },
  { label: 'User', value: 'user' },
  { label: 'System', value: 'system' },
];

export const ACTIVITY_LOG_STATUS_OPTIONS = [
  { label: 'All statuses', value: '' },
  { label: 'success', value: 'success' },
  { label: 'accepted', value: 'accepted' },
  { label: 'completed', value: 'completed' },
  { label: 'pending', value: 'pending' },
  { label: 'failed', value: 'failed' },
  { label: 'denied', value: 'denied' },
  { label: 'archived', value: 'archived' },
  { label: 'cancelled', value: 'cancelled' },
  { label: '200', value: '200' },
  { label: '201', value: '201' },
  { label: '204', value: '204' },
  { label: '400', value: '400' },
  { label: '401', value: '401' },
  { label: '403', value: '403' },
  { label: '404', value: '404' },
  { label: '500', value: '500' },
  { label: '502', value: '502' },
  { label: '503', value: '503' },
];

export const formatActivityActionLabel = toAnalyticsTitleCase;

export const truncateActivityValue = (value: string, max = 44) =>
  value.length > max ? `${value.slice(0, max - 1)}...` : value;

const toDisplayText = (value: DashboardActivityMetadataValue | undefined) => {
  if (typeof value === 'string') return value.trim() || null;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
};

export const formatActivityActor = (entry: DashboardActivityLogEntry) => {
  if (!entry.actor) return '--';
  if (entry.actor.name?.trim()) return entry.actor.name.trim();
  if (entry.actor.email?.trim()) return entry.actor.email.trim();
  return entry.actor.user_id;
};

export const formatActivityEntitySummary = (entry: DashboardActivityLogEntry) => {
  if (entry.entity_label?.trim()) return entry.entity_label.trim();
  if (entry.entity_id?.trim()) return entry.entity_id.trim();
  return '--';
};

export const resolveActivityHttpMethod = (entry: DashboardActivityLogEntry) => {
  const raw = entry.metadata?.method;
  if (typeof raw === 'string' && raw.trim().length > 0) {
    return raw.trim().toUpperCase();
  }

  const detail = entry.detail?.trim();
  if (!detail) return null;
  const match = detail.match(/^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b/i);
  return match ? match[1].toUpperCase() : null;
};

export const resolveActivityApiPath = (entry: DashboardActivityLogEntry) => {
  const pathFromMetadata = entry.metadata?.path;
  if (typeof pathFromMetadata === 'string' && pathFromMetadata.trim().length > 0) {
    return pathFromMetadata.trim();
  }

  const detail = entry.detail?.trim();
  if (!detail) return null;

  const pathMatch = detail.match(/\/api\/[^\s]+/i);
  if (pathMatch) return pathMatch[0];

  return detail;
};

export const getActivityMethodBadgeClass = (method: string | null) => {
  if (!method) return 'border-border bg-surface-muted text-muted';
  if (method === 'GET') return 'border-border bg-app-accent-soft text-app-accent-text';
  if (method === 'POST') return 'border-border bg-app-success-soft text-app-success-text';
  if (method === 'PUT' || method === 'PATCH') {
    return 'border-border bg-app-warning-soft text-app-warning-text';
  }
  if (method === 'DELETE') return 'border-border bg-app-danger-soft text-app-danger-text';
  return 'border-border bg-surface-muted text-muted';
};

export const getActivityStatusBadgeClass = (status: string | null) => {
  if (!status) return 'border-border bg-surface-muted text-muted';

  const numericStatus = Number(status);
  if (Number.isFinite(numericStatus)) {
    if (numericStatus >= 500) return 'border-border bg-app-danger-soft text-app-danger-text';
    if (numericStatus >= 400) return 'border-border bg-app-warning-soft text-app-warning-text';
    if (numericStatus >= 300) return 'border-border bg-app-accent-soft text-app-accent-text';
    if (numericStatus >= 200) return 'border-border bg-app-success-soft text-app-success-text';
  }

  const normalized = status.toLowerCase();
  if (['success', 'accepted', 'completed'].includes(normalized)) {
    return 'border-border bg-app-success-soft text-app-success-text';
  }
  if (normalized === 'pending') return 'border-border bg-app-warning-soft text-app-warning-text';
  if (['failed', 'denied', 'error', 'archived', 'cancelled'].includes(normalized)) {
    return 'border-border bg-app-danger-soft text-app-danger-text';
  }
  return 'border-border bg-app-accent-soft text-app-accent-text';
};

export const resolveActivityDurationMs = (entry: DashboardActivityLogEntry) => {
  const direct =
    typeof entry.duration_ms === 'number' && Number.isFinite(entry.duration_ms)
      ? entry.duration_ms
      : null;
  if (direct !== null) return direct;

  const fromMetadata = entry.metadata?.duration_ms;
  if (typeof fromMetadata === 'number' && Number.isFinite(fromMetadata)) return fromMetadata;
  if (typeof fromMetadata === 'string') {
    const parsed = Number(fromMetadata);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
};

export const formatActivityDurationMs = (durationMs: number | null) => {
  if (durationMs === null) return null;
  if (durationMs < 1000) return `${Math.round(durationMs)}ms`;

  const seconds = durationMs / 1000;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds)}s`;
};

export const resolveActivityErrorInfo = (entry: DashboardActivityLogEntry) => {
  const directCode = toDisplayText(entry.error_code);
  const directMessage = entry.error_message?.trim() || null;

  if (directCode || directMessage) {
    return { code: directCode, message: directMessage };
  }

  return {
    code: toDisplayText(entry.metadata?.error_code),
    message: toDisplayText(entry.metadata?.error_message),
  };
};

const normalizeSortValue = (value: string | null) => (value ?? '').trim().toLowerCase();

export const sortActivityLogRows = (
  rows: DashboardActivityLogEntry[],
  sortKey: ActivityLogSortKey,
  sortDir: ActivityLogSortDirection
) => {
  if (!rows.length) return rows;

  const compare = (left: DashboardActivityLogEntry, right: DashboardActivityLogEntry) => {
    if (sortKey === 'time') {
      const leftTs = new Date(left.occurred_at).getTime();
      const rightTs = new Date(right.occurred_at).getTime();
      return leftTs - rightTs;
    }

    if (sortKey === 'duration') {
      const leftDuration = resolveActivityDurationMs(left) ?? -1;
      const rightDuration = resolveActivityDurationMs(right) ?? -1;
      return leftDuration - rightDuration;
    }

    if (sortKey === 'actor') {
      return normalizeSortValue(formatActivityActor(left)).localeCompare(
        normalizeSortValue(formatActivityActor(right))
      );
    }

    if (sortKey === 'status') {
      return normalizeSortValue(left.status).localeCompare(normalizeSortValue(right.status));
    }

    return normalizeSortValue(left.label || formatActivityActionLabel(left.action)).localeCompare(
      normalizeSortValue(right.label || formatActivityActionLabel(right.action))
    );
  };

  const sorted = [...rows].sort(compare);
  return sortDir === 'asc' ? sorted : sorted.reverse();
};
