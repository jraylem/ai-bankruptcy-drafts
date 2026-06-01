import type { DashboardActivityFeedItem } from '../types/dashboard.types';

export type ActivityTone = 'indigo' | 'amber' | 'emerald' | 'rose';
export type ActivityIconKey =
  | 'activity'
  | 'alert'
  | 'check'
  | 'clock'
  | 'download'
  | 'file'
  | 'inbox'
  | 'login'
  | 'refresh'
  | 'server'
  | 'upload'
  | 'users';

const formatAbsoluteActivityTime = (occurredAt: string) =>
  new Date(occurredAt).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

const resolveFallbackActivityDetail = (item: DashboardActivityFeedItem) => {
  const metadata = item.metadata ?? {};

  return typeof metadata.case_name === 'string'
    ? metadata.case_name
    : typeof metadata.filename === 'string'
      ? metadata.filename
      : typeof metadata.motion_type === 'string'
        ? metadata.motion_type
        : typeof metadata.document_type === 'string'
          ? metadata.document_type
          : typeof metadata.reason === 'string'
            ? metadata.reason
            : typeof metadata.status === 'string'
              ? metadata.status
              : formatActivityLabel(item);
};

const resolveActivityDetail = (item: DashboardActivityFeedItem) =>
  typeof item.detail === 'string' && item.detail.trim().length > 0
    ? item.detail.trim()
    : resolveFallbackActivityDetail(item);

export const formatRelativeActivityTime = (occurredAt: string) => {
  const now = Date.now();
  const time = new Date(occurredAt).getTime();
  const diffMs = now - time;
  const diffMinutes = Math.max(0, Math.floor(diffMs / 60_000));

  if (diffMinutes < 1) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes} min${diffMinutes === 1 ? '' : 's'} ago`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} hr${diffHours === 1 ? '' : 's'} ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`;

  return formatAbsoluteActivityTime(occurredAt);
};

export const formatActivityLabel = (item: DashboardActivityFeedItem) => {
  if (item.label && item.label !== item.action) return item.label;

  return item.action
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

export const formatActivityMeta = (item: DashboardActivityFeedItem) => {
  return [formatActivityDetails(item), formatRelativeActivityTime(item.occurred_at)]
    .filter(Boolean)
    .join(' • ');
};

export const formatActivityDetails = (item: DashboardActivityFeedItem) => {
  const detail = resolveActivityDetail(item);
  const actor =
    typeof item.actor_name === 'string' && item.actor_name.trim().length > 0
      ? item.actor_name.trim()
      : null;

  return [actor, detail].filter(Boolean).join(' • ');
};

const toCleanString = (value: unknown) => {
  if (typeof value === 'string') {
    const cleaned = value.trim();
    return cleaned.length > 0 ? cleaned : null;
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }

  return null;
};

const formatShortSessionId = (sessionId: string) =>
  sessionId.length > 12 ? `${sessionId.slice(0, 8)}…${sessionId.slice(-4)}` : sessionId;

export const getActivityHighlights = (item: DashboardActivityFeedItem, limit = 3) => {
  const metadata = item.metadata ?? {};
  const detail = resolveActivityDetail(item).toLowerCase();
  const highlights: string[] = [];
  const seen = new Set<string>();
  const push = (label: string, rawValue: unknown, transform?: (value: string) => string) => {
    const value = toCleanString(rawValue);
    if (!value) return;

    const transformedValue = transform ? transform(value) : value;
    const normalized = transformedValue.toLowerCase();
    const composed = `${label}: ${transformedValue}`;
    const dedupeKey = composed.toLowerCase();

    if (seen.has(dedupeKey)) return;
    if (normalized === detail || detail.includes(normalized)) return;

    seen.add(dedupeKey);
    highlights.push(composed);
  };

  if (item.session_id) {
    push('Session', formatShortSessionId(item.session_id));
  }

  push('Case', metadata.case_name);
  push('Case #', metadata.case_number);
  push('Motion', metadata.motion_type);
  push('File', metadata.filename);
  push('Source', metadata.source);
  push('Email', metadata.email);
  push('Status', metadata.status_code);
  push('Latency', metadata.duration_ms, (value) => `${value}ms`);
  push('Format', metadata.format, (value) => value.toUpperCase());

  const method = toCleanString(metadata.method);
  const path = toCleanString(metadata.path);
  if (method && path) {
    push('API', `${method.toUpperCase()} ${path}`);
  }

  return highlights.slice(0, Math.max(0, limit));
};

export const getActivityTone = (action: string): ActivityTone => {
  const normalized = action.toLowerCase();

  if (normalized.includes('error') || normalized.includes('fail')) return 'rose';
  if (
    normalized.includes('upload') ||
    normalized.includes('pending') ||
    normalized.includes('download')
  ) {
    return 'amber';
  }
  if (
    normalized.includes('review') ||
    normalized.includes('session') ||
    normalized.includes('user') ||
    normalized.includes('login')
  ) {
    return 'emerald';
  }

  return 'indigo';
};

export const getActivityIconKey = (action: string): ActivityIconKey => {
  const normalized = action.toLowerCase();

  if (normalized.includes('login') || normalized.includes('sign_in')) return 'login';
  if (normalized.includes('download')) return 'download';
  if (normalized.includes('upload')) return 'upload';
  if (normalized.includes('review')) return 'file';
  if (normalized.includes('complete') || normalized.includes('success')) return 'check';
  if (normalized.includes('error') || normalized.includes('fail')) return 'alert';
  if (
    normalized.includes('system') ||
    normalized.includes('worker') ||
    normalized.includes('poll') ||
    normalized.includes('queue')
  ) {
    return 'server';
  }
  if (normalized.includes('regenerate') || normalized.includes('refresh')) return 'refresh';
  if (normalized.includes('pending') || normalized.includes('inbox')) return 'inbox';
  if (
    normalized.includes('session') ||
    normalized.includes('user') ||
    normalized.includes('account')
  ) {
    return 'users';
  }

  return 'activity';
};
