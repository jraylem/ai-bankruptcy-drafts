import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { FiAlertCircle, FiCheckCircle, FiLoader, FiXCircle } from 'react-icons/fi';
import { authService } from '@/services/auth.service';

type ApprovalAction = 'approve' | 'deny';
type ApprovalStatus = 'idle' | 'loading' | 'success' | 'error';
type ApprovalResponse = Awaited<ReturnType<typeof authService.approveUserAccess>>;

const approvalRequests = new Map<string, Promise<ApprovalResponse>>();

const getDisplayAction = (action: ApprovalAction | null) => {
  if (action === 'approve') return 'approving';
  if (action === 'deny') return 'rejecting';
  return 'processing';
};

const getCompletedAction = (action: ApprovalAction | null) => {
  if (action === 'approve') return 'approved';
  if (action === 'deny') return 'rejected';
  return 'processed';
};

const normalizeAction = (action: string | null): ApprovalAction | null => {
  if (action === 'approve' || action === 'deny') return action;
  return null;
};

export const UserApprovalPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token')?.trim() || '';
  const action = normalizeAction(searchParams.get('action')?.trim().toLowerCase() || null);
  const email = searchParams.get('email')?.trim() || searchParams.get('user_email')?.trim() || '';
  const firm = searchParams.get('firm')?.trim() || searchParams.get('firm_name')?.trim() || '';
  const [status, setStatus] = React.useState<ApprovalStatus>('idle');
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!token || !action) return undefined;

    let cancelled = false;
    let closeTimer: number | undefined;

    const submitApproval = async () => {
      setStatus('loading');
      setError(null);

      const requestKey = `${token}:${action}`;
      let approvalRequest = approvalRequests.get(requestKey);

      if (!approvalRequest) {
        approvalRequest = authService.approveUserAccess(token, action);
        approvalRequests.set(requestKey, approvalRequest);
      }

      const response = await approvalRequest;
      if (cancelled) return;

      if (response.error) {
        approvalRequests.delete(requestKey);
        setStatus('error');
        setError(response.error);
        return;
      }

      setStatus('success');
      closeTimer = window.setTimeout(() => {
        window.close();
      }, 900);
    };

    void submitApproval();

    return () => {
      cancelled = true;
      if (closeTimer) window.clearTimeout(closeTimer);
    };
  }, [action, token]);

  const isInvalid = !token || !action;
  const isApproving = action === 'approve';
  const Icon = isInvalid
    ? FiAlertCircle
    : status === 'success'
      ? FiCheckCircle
      : status === 'error'
        ? FiXCircle
        : FiLoader;
  const iconClassName = isInvalid
    ? 'bg-app-warning-soft text-app-warning-text'
    : status === 'success'
      ? isApproving
        ? 'bg-emerald-50 text-emerald-600'
        : 'bg-rose-50 text-rose-600'
      : status === 'error'
        ? 'bg-app-danger-soft text-app-danger-text'
        : isApproving
          ? 'bg-emerald-50 text-emerald-600'
          : 'bg-rose-50 text-rose-600';
  const titleClassName =
    !isInvalid && status !== 'error'
      ? isApproving
        ? 'text-emerald-600'
        : 'text-rose-600'
      : 'text-text';
  const titleText = isInvalid
    ? 'Invalid link'
    : status === 'success'
      ? `User ${getCompletedAction(action)}`
      : status === 'error'
        ? 'Could not update user'
        : `${getDisplayAction(action).charAt(0).toUpperCase()}${getDisplayAction(action).slice(1)} user`;

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-gradient-to-br from-auth-bg-from via-auth-bg-via to-auth-bg-to px-4 py-10 text-text">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -right-40 -top-40 h-80 w-80 animate-blob rounded-full bg-auth-blob-purple opacity-70 mix-blend-multiply blur-xl" />
        <div className="animation-delay-2000 absolute -bottom-40 -left-40 h-80 w-80 animate-blob rounded-full bg-auth-blob-indigo opacity-70 mix-blend-multiply blur-xl" />
        <div className="animation-delay-4000 absolute left-40 top-40 h-80 w-80 animate-blob rounded-full bg-auth-blob-pink opacity-70 mix-blend-multiply blur-xl" />
      </div>

      <section className="relative z-10 w-full max-w-md overflow-hidden rounded-2xl border border-border bg-surface/95 p-8 text-center shadow-xl backdrop-blur-sm">
        <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl transition duration-500 hover:scale-105 hover:rotate-3">
          <img
            src="/logo.png"
            alt="Jurisgentic logo"
            className="h-14 w-14 object-contain logo-on-dark"
          />
        </div>

        <div
          className={`mx-auto flex h-12 w-12 items-center justify-center rounded-full ${iconClassName}`}
        >
          <Icon className={`h-6 w-6 ${status === 'loading' ? 'animate-spin' : ''}`} />
        </div>

        <h1 className={`mt-5 font-poppins text-2xl font-semibold ${titleClassName}`}>
          {titleText}
        </h1>

        <p className="mt-3 text-sm leading-6 text-text-secondary">
          {isInvalid
            ? 'This approval link is missing a valid token or action.'
            : status === 'success'
              ? 'This tab will close automatically.'
              : status === 'error'
                ? error || 'The approval link could not be processed.'
                : 'Please wait while we update this user.'}
        </p>

        {!isInvalid ? (
          <div className="mt-6 space-y-3 rounded-xl bg-surface-muted px-4 py-4 text-left">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Email</p>
              <p className="mt-1 break-all text-sm font-semibold text-text-secondary">
                {email || 'Not provided'}
              </p>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Firm</p>
              <p className="mt-1 text-sm font-semibold text-text-secondary">
                {firm || 'Not provided'}
              </p>
            </div>
          </div>
        ) : null}

        {status === 'success' ? (
          <p className="mt-5 text-xs text-muted">
            If your browser does not allow automatic closing, you can close this tab.
          </p>
        ) : null}
      </section>
    </main>
  );
};
