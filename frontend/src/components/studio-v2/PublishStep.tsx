import { FiAlertCircle, FiAlertTriangle, FiCheckCircle, FiClock, FiUploadCloud, FiX } from 'react-icons/fi';
import { formatRelativeTime } from '@/utils/studioV2/adapter';

interface PublishStepProps {
  publishedAt: string | null;
  hasUnpublishedChanges: boolean;
  configuredCount: number;
  totalCount: number;
  isPublishing: boolean;
  validationErrors: string[];
  onPublishClick: () => void;
  onDismissValidationErrors: () => void;
}

interface StatusMeta {
  label: string;
  body: string;
  tone: 'draft' | 'published' | 'dirty';
  icon: React.ReactNode;
}

const computeStatus = (
  publishedAt: string | null,
  hasUnpublishedChanges: boolean,
): StatusMeta => {
  if (publishedAt === null) {
    return {
      label: 'Not published yet',
      body: 'Drafting and the /v2 chat command ignore unpublished templates. Publish to make this available for paralegals to draft from.',
      tone: 'draft',
      icon: <FiClock className="h-3.5 w-3.5" />,
    };
  }
  if (hasUnpublishedChanges) {
    return {
      label: `Published ${formatRelativeTime(publishedAt)} · changes pending`,
      body: "Your latest edits aren't live yet. The published version is frozen at the last publish — re-publish to push the current spec to drafting.",
      tone: 'dirty',
      icon: <FiAlertCircle className="h-3.5 w-3.5" />,
    };
  }
  return {
    label: `Live · published ${formatRelativeTime(publishedAt)}`,
    body: 'The published version matches your working draft. Drafting + chat /v2 reach this template.',
    tone: 'published',
    icon: <FiCheckCircle className="h-3.5 w-3.5" />,
  };
};

const TONE_STYLES: Record<StatusMeta['tone'], string> = {
  draft: 'border-border bg-surface-muted/50 text-text-secondary',
  published: 'border-app-accent/30 bg-app-accent-soft/40 text-app-accent-text',
  dirty: 'border-amber-300 bg-amber-50 text-amber-900',
};

export const PublishStep = ({
  publishedAt,
  hasUnpublishedChanges,
  configuredCount,
  totalCount,
  isPublishing,
  validationErrors,
  onPublishClick,
  onDismissValidationErrors,
}: PublishStepProps) => {
  const status = computeStatus(publishedAt, hasUnpublishedChanges);
  const allFieldsConfigured = totalCount > 0 && configuredCount === totalCount;
  const showProgressNudge = !allFieldsConfigured;
  const hasErrors = validationErrors.length > 0;

  // The publish CTA label tracks the lifecycle so paralegals see the
  // verb that matches what's about to happen.
  const ctaLabel = isPublishing
    ? 'Publishing…'
    : publishedAt === null
      ? 'Publish template'
      : 'Re-publish changes';

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider text-app-accent-text">
          Step 3 · Publish
        </p>
        <p className="mt-0.5 text-[11px] text-subtle">
          Lock the current spec so paralegals can draft from it.
        </p>
      </div>

      <div className={`rounded-lg border px-3 py-2.5 ${TONE_STYLES[status.tone]}`}>
        <div className="flex items-start gap-2">
          <span className="mt-0.5 shrink-0">{status.icon}</span>
          <div className="space-y-1">
            <p className="text-xs font-semibold">{status.label}</p>
            <p className="text-[11px] leading-snug opacity-90">{status.body}</p>
          </div>
        </div>
      </div>

      {hasErrors && (
        <div className="rounded-lg border border-app-danger-soft bg-app-danger-soft/40 px-3 py-2.5">
          <div className="flex items-start gap-2">
            <FiAlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-app-danger-text" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <p className="text-xs font-semibold text-app-danger-text">
                {validationErrors.length === 1
                  ? '1 issue is blocking publish'
                  : `${validationErrors.length} issues are blocking publish`}
              </p>
              <ul className="space-y-1">
                {validationErrors.map((err, i) => (
                  <li
                    key={`${err}-${i}`}
                    className="text-[11px] leading-snug text-text-secondary"
                  >
                    • {err}
                  </li>
                ))}
              </ul>
            </div>
            <button
              type="button"
              onClick={onDismissValidationErrors}
              aria-label="Dismiss validation errors"
              className="shrink-0 rounded p-1 text-subtle transition-colors hover:bg-app-danger-soft hover:text-app-danger-text"
            >
              <FiX className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      {showProgressNudge && !hasErrors && (
        <p className="text-[11px] italic text-subtle">
          {configuredCount} of {totalCount} fields configured. Unconfigured
          fields will block publish.
        </p>
      )}

      <button
        type="button"
        onClick={onPublishClick}
        disabled={isPublishing}
        className="inline-flex w-full cursor-pointer items-center justify-center gap-2 rounded-md bg-app-accent px-3 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <FiUploadCloud className="h-3.5 w-3.5" />
        {ctaLabel}
      </button>
    </div>
  );
};
