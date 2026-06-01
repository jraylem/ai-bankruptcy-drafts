import React from 'react';

interface CaseInboxEmptyStateProps {
  /** Distinguishes the main inbox empty state from the archived one. */
  variant: 'inbox' | 'archived';
  lastUpdatedAt: number | null;
  onRefresh: () => void;
}

/**
 * Actionable empty state per the architect's note: no illustrations, no
 * Mailchimp vibe. Tells the paralegal what to expect + when last checked
 * + how to force a check.
 */
export const CaseInboxEmptyState: React.FC<CaseInboxEmptyStateProps> = ({
  variant,
  lastUpdatedAt,
  onRefresh,
}) => {
  if (variant === 'archived') {
    return (
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <h2 className="text-base font-semibold text-text">No archived petitions</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted">
          Archived petitions show up here. They include petitions that were
          dismissed by a paralegal and petitions the system aged out after 48
          hours of inactivity. Either can be reinstated back into an active case.
        </p>
      </div>
    );
  }

  const lastChecked = lastUpdatedAt
    ? ` Last check: ${secondsAgo(lastUpdatedAt)}.`
    : '';

  return (
    <div className="rounded-lg border border-border bg-surface p-8 text-center">
      <h2 className="text-base font-semibold text-text">Inbox is clear.</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">
        New petitions from Gmail / CM/ECF appear here within ~2 minutes of
        arrival.{lastChecked}
      </p>
      <button
        type="button"
        onClick={onRefresh}
        className="mt-4 rounded border border-border bg-surface px-4 py-1.5 text-sm font-semibold text-text-secondary transition hover:bg-surface-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent"
      >
        Check now
      </button>
    </div>
  );
};

function secondsAgo(ts: number, now: number = Date.now()): string {
  const diff = Math.max(0, Math.round((now - ts) / 1000));
  if (diff < 60) return `${diff}s ago`;
  const m = Math.round(diff / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  return `${h}h ago`;
}
