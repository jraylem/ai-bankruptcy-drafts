import { useState, type ReactElement } from 'react';
import { LuFileText } from 'react-icons/lu';

interface NewCaseExtractByNumberProps {
  onSubmit: (caseNumber: string) => Promise<boolean>;
  isUploading: boolean;
}

export const NewCaseExtractByNumber = ({
  onSubmit,
  isUploading,
}: NewCaseExtractByNumberProps): ReactElement => {
  const [caseNumber, setCaseNumber] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const handleExtract = async (): Promise<void> => {
    const trimmed = caseNumber.trim();
    if (!trimmed) {
      setLocalError('Enter a case number first.');
      return;
    }
    setLocalError(null);
    const ok = await onSubmit(trimmed);
    if (!ok) {
      setLocalError('Could not extract the petition. Double-check the case number and try again.');
    }
  };

  return (
    <div className="flex flex-col items-center justify-center gap-5 rounded-2xl border border-border bg-surface px-8 py-14 text-center">
      <span
        aria-hidden="true"
        className="grid h-14 w-14 place-items-center rounded-full bg-app-accent-soft text-app-accent-text"
      >
        <LuFileText className="h-7 w-7" />
      </span>

      <div className="flex flex-col gap-1">
        <p className="text-base font-semibold text-text-secondary">Extract Petition by Case Number</p>
        <p className="text-xs text-muted">Enter a case number to automatically download the petition.</p>
      </div>

      <input
        type="text"
        value={caseNumber}
        onChange={(e) => setCaseNumber(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !isUploading) {
            e.preventDefault();
            void handleExtract();
          }
        }}
        placeholder="8:25-bk-08103"
        disabled={isUploading}
        aria-label="Case number"
        autoComplete="off"
        className="w-full max-w-md rounded-lg border border-border bg-surface-muted/50 px-4 py-3 text-center text-sm text-text placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-app-accent disabled:cursor-not-allowed disabled:opacity-50"
      />

      {localError && (
        <div
          role="alert"
          className="w-full max-w-md rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-2 text-sm text-app-danger-text"
        >
          {localError}
        </div>
      )}

      <button
        type="button"
        onClick={handleExtract}
        disabled={!caseNumber.trim() || isUploading}
        className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:from-indigo-700 hover:to-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isUploading && (
          <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )}
        {isUploading ? 'Extracting…' : 'Extract Petition'}
      </button>
    </div>
  );
};

export default NewCaseExtractByNumber;
