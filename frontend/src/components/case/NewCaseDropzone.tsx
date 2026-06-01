import { useCallback, useState, type ReactElement } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';

/**
 * Inline new-case upload surface for the Draft v2 workspace.
 *
 * Architect-led layout: page-level H1 + lede, then a two-column body
 * with the dropzone on the left and a "What happens next" explainer on
 * the right. Top-aligned (not vertically centered) so whitespace below
 * reads as breathing room, not "the page forgot to load."
 *
 * The optimistic placeholder lifecycle (the sidebar's `Untitled` row +
 * the synthetic `selectedCaseId`) is owned by the page; this component
 * just renders the upload surface and surfaces inline validation
 * errors.
 */

interface NewCaseDropzoneProps {
  /** Async upload action. Resolves to true on success. */
  onSubmit: (file: File) => Promise<boolean>;
  isUploading: boolean;
}

const PDF_MIME = 'application/pdf';
const MAX_SIZE_BYTES = 25 * 1024 * 1024;

const formatBytes = (bytes: number): string => {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const PIPELINE_STEPS: ReadonlyArray<{ n: number; title: string; body: string }> = [
  {
    n: 1,
    title: 'Read the petition',
    body: 'Claude extracts the case number, debtor name(s), district, and chapter from the PDF.',
  },
  {
    n: 2,
    title: 'Index for retrieval',
    body: "Page-level chunks land in the case's vector collection so the assistant can quote from the petition later.",
  },
  {
    n: 3,
    title: 'Match prior communications',
    body: "Existing Gmail threads and Court Drive notices that reference this case number are pulled in automatically.",
  },
];

export const NewCaseDropzone = ({
  onSubmit,
  isUploading,
}: NewCaseDropzoneProps): ReactElement => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[], rejections: FileRejection[]) => {
    setLocalError(null);
    if (rejections.length > 0) {
      const rejection = rejections[0];
      const code = rejection?.errors[0]?.code;
      const file = rejection?.file;
      if (code === 'file-too-large' && file) {
        setLocalError(`That file is ${formatBytes(file.size)}. Max is 25 MB.`);
      } else if (code === 'file-invalid-type' && file) {
        const ext = file.name.split('.').pop()?.toLowerCase() ?? 'file';
        setLocalError(`That's a .${ext} — we need a PDF of the petition.`);
      } else {
        setLocalError(rejection?.errors[0]?.message ?? 'File rejected.');
      }
      return;
    }
    const file = accepted[0];
    if (file) setSelectedFile(file);
  }, []);

  const { getRootProps, getInputProps, isDragActive, isDragReject, open } = useDropzone({
    onDrop,
    accept: { [PDF_MIME]: ['.pdf'] },
    maxSize: MAX_SIZE_BYTES,
    multiple: false,
    noClick: true,
    noKeyboard: true,
    disabled: isUploading,
  });

  const handleUpload = async (): Promise<void> => {
    if (!selectedFile) {
      setLocalError('Pick a PDF file first.');
      return;
    }
    setLocalError(null);
    const ok = await onSubmit(selectedFile);
    if (!ok) {
      setLocalError('Upload failed. Try again or pick a different file.');
    }
  };

  return (
    <div>
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
          {/* Dropzone column */}
          <div className="flex flex-col gap-3">
            <div
              {...getRootProps()}
              onClick={isUploading ? undefined : open}
              className={`relative flex flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-8 py-14 text-center transition-all ${
                isUploading ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'
              } ${
                isDragReject
                  ? 'border-red-300 bg-app-danger-soft'
                  : isDragActive
                    ? 'border-indigo-500 bg-app-accent-soft'
                    : selectedFile
                      ? 'border-emerald-300 bg-app-success-soft'
                      : 'border-border bg-surface hover:border-indigo-300 hover:bg-surface-muted'
              }`}
              role="button"
              tabIndex={0}
              aria-label={
                selectedFile
                  ? `Selected file ${selectedFile.name}. Click to replace.`
                  : 'Drop the petition PDF here, or click anywhere in this box to choose a file'
              }
            >
              <input {...getInputProps()} />
              {selectedFile ? (
                <>
                  <span
                    aria-hidden="true"
                    className="grid h-14 w-14 place-items-center rounded-full bg-emerald-100 text-emerald-600"
                  >
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      strokeWidth={2}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                  <p className="mt-1 text-base font-semibold text-app-success-text">
                    {selectedFile.name}
                  </p>
                  <p className="text-xs text-muted">
                    {formatBytes(selectedFile.size)}
                    {!isUploading && ' · click to replace'}
                  </p>
                </>
              ) : (
                <>
                  <span
                    aria-hidden="true"
                    className={`grid h-14 w-14 place-items-center rounded-full ${
                      isDragActive ? 'bg-indigo-100 text-indigo-600' : 'bg-app-accent-soft text-app-accent-text'
                    } motion-safe:transition-transform ${isDragActive ? 'motion-safe:scale-105' : ''}`}
                  >
                    <svg
                      className="h-7 w-7"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                      strokeWidth={1.8}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M7 16a4 4 0 0 1-.88-7.9 5 5 0 0 1 9.9-.4 4 4 0 0 1 .98 7.8" />
                      <path d="M12 12v8" />
                      <path d="m8 16 4-4 4 4" />
                    </svg>
                  </span>
                  <p className="text-base font-semibold text-text-secondary">
                    {isDragActive ? 'Release to upload' : 'Drop the bankruptcy petition here'}
                  </p>
                  <p className="text-xs text-muted">
                    or click anywhere in this box to choose a file
                    <span className="mx-1.5" aria-hidden="true">·</span>
                    PDF, up to 25&nbsp;MB
                  </p>
                </>
              )}
            </div>

            {localError && (
              <div
                role="alert"
                className="rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-2 text-sm text-app-danger-text"
              >
                {localError}
              </div>
            )}

            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={handleUpload}
                disabled={!selectedFile || isUploading}
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
                {isUploading ? 'Uploading…' : 'Upload and continue'}
              </button>
            </div>
          </div>

          {/* Explainer column */}
          <aside className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
              What happens next
            </h2>
            <ol className="mt-4 space-y-5">
              {PIPELINE_STEPS.map((step) => (
                <li key={step.n} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-app-accent-soft text-[11px] font-bold text-app-accent-text"
                  >
                    {step.n}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-text-secondary">{step.title}</p>
                    <p className="mt-0.5 text-[13px] leading-relaxed text-muted">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-5 border-t border-border pt-4 text-[11px] leading-relaxed text-subtle">
              Indexing usually takes 10–30 seconds depending on petition length. You can switch to
              another case in the sidebar while it runs.
            </p>
          </aside>
        </div>
      </div>
  );
};

export default NewCaseDropzone;
