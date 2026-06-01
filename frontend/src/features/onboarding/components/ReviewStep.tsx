import { useFormContext } from 'react-hook-form';
import { getPracticeTypeLabel } from '../practiceTypes';
import type { InvitedMember } from '../types';
import type { OnboardingFormValues } from '../types';

interface ReviewStepProps {
  invites: InvitedMember[];
  isConfirmed: boolean;
  onConfirmedChange: (isConfirmed: boolean) => void;
}

export const ReviewStep = ({ invites, isConfirmed, onConfirmedChange }: ReviewStepProps) => {
  const { watch } = useFormContext<OnboardingFormValues>();
  const firmName = watch('firmName');
  const firmAddress = watch('firmAddress');
  const contactNumber = watch('contactNumber');
  const practiceType = watch('practiceType');
  const ownerName = watch('ownerName');
  const ownerEmail = watch('ownerEmail');

  return (
    <section>
      <h1 className="font-poppins text-2xl font-semibold text-app-accent-text">Review & Confirm</h1>
      <p className="mt-2 text-sm text-text-secondary">
        Step 3: Confirm the firm details before opening the dashboard.
      </p>

      <div className="mt-12">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-text-secondary">
          Firm
        </p>
        <p className="mt-3 font-poppins text-2xl font-bold tracking-tight text-text">
          {firmName || 'Firm name'}
        </p>
        <div className="mt-5 max-w-xl space-y-3 text-sm">
          <div className="flex items-center justify-between gap-4">
            <span className="text-text-secondary">Practice type</span>
            <span className="font-medium text-text-secondary">
              {getPracticeTypeLabel(practiceType)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-text-secondary">Firm email address</span>
            <span className="text-right font-medium text-text-secondary">
              {firmAddress || 'Firm email address'}
            </span>
          </div>
          {contactNumber ? (
            <div className="flex items-center justify-between gap-4">
              <span className="text-text-secondary">Firm contact number</span>
              <span className="text-right font-medium text-text-secondary">{contactNumber}</span>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-4">
            <span className="text-text-secondary">Account owner</span>
            <span className="font-medium text-text-secondary">{ownerName || 'Owner'}</span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-text-secondary">Owner email</span>
            <span className="truncate font-medium text-text-secondary">{ownerEmail}</span>
          </div>
        </div>
      </div>

      <div className="mt-10">
        <h2 className="font-poppins text-lg font-semibold text-text-secondary">Member list</h2>
        <div className="mt-4 divide-y divide-border overflow-hidden rounded-xl border border-border">
          <div className="flex items-center justify-between gap-4 px-4 py-3">
            <span className="truncate text-sm font-medium text-text-secondary">{ownerEmail}</span>
            <span className="shrink-0 rounded-lg bg-app-accent px-3 py-1 text-xs font-semibold text-white">
              Superadmin (you)
            </span>
          </div>
          {invites.map((member) => (
            <div key={member.email} className="flex items-center justify-between gap-4 px-4 py-3">
              <span className="truncate text-sm font-medium text-text-secondary">
                {member.email}
              </span>
              <span className="shrink-0 rounded-lg bg-app-accent-soft px-3 py-1 text-xs font-semibold capitalize text-app-accent-text">
                {member.role}
              </span>
            </div>
          ))}
        </div>
      </div>

      <label className="mt-8 flex cursor-pointer items-start gap-3 rounded-2xl bg-surface-muted p-4 text-sm text-text-secondary">
        <input
          type="checkbox"
          checked={isConfirmed}
          onChange={(event) => onConfirmedChange(event.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-border text-app-accent focus:ring-app-accent-soft"
        />
        <span>I confirm these firm details are ready to use for this workspace.</span>
      </label>
    </section>
  );
};
