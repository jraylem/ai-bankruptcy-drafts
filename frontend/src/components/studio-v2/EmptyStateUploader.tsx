import { FiFileText, FiUploadCloud } from 'react-icons/fi';

interface EmptyStateUploaderProps {
  variant: 'no_templates' | 'no_selection';
  onUploadClick: () => void;
}

export const EmptyStateUploader = ({
  variant,
  onUploadClick,
}: EmptyStateUploaderProps) => {
  const isFirstTime = variant === 'no_templates';

  return (
    <div className="flex h-full min-h-0 items-center justify-center bg-surface-muted/40 px-6 py-8">
      <div className="flex w-full max-w-[640px] flex-col items-center gap-5 rounded-2xl border-2 border-dashed border-border bg-surface px-10 py-12 text-center shadow-sm">
        <span className="grid h-16 w-16 place-items-center rounded-full bg-app-accent-soft text-app-accent-text">
          {isFirstTime ? (
            <FiUploadCloud className="h-8 w-8" />
          ) : (
            <FiFileText className="h-8 w-8" />
          )}
        </span>

        <div className="space-y-1.5">
          <h2 className="text-lg font-semibold text-text-secondary">
            {isFirstTime
              ? 'Upload your first legal document'
              : 'Pick a template to get started'}
          </h2>
          <p className="text-sm text-text-secondary">
            {isFirstTime
              ? "Drop a .docx file here, or click below to browse. We'll extract the variables and set up a template for you."
              : 'Choose one of your templates from the list on the left, or upload a new one.'}
          </p>
        </div>

        <button
          type="button"
          onClick={onUploadClick}
          className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-app-accent px-5 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
        >
          <FiUploadCloud className="h-4 w-4" />
          {isFirstTime ? 'Choose file' : 'Upload new template'}
        </button>

        <p className="text-[11px] text-subtle">
          Accepts .docx files up to 10 MB.
        </p>
      </div>
    </div>
  );
};
