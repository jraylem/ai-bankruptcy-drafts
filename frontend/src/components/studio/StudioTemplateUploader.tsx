import { useCallback, useState, type ReactElement } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import { Button } from '@/components/common';
import { UploadStateHero, type UploadVisualState } from '@/components/common/UploadStateHero';
import { useStudioStore } from '@/stores/useStudioStore';
import { DOCX_MIME, MAX_SIZE_BYTES, deriveTemplateName } from '@/utils/studio/templateUpload';

interface StudioTemplateUploaderProps {
  onUploadSuccess: (templateId: string) => void;
}

const SUCCESS_HOLD_MS = 600;

/**
 * Empty-state inline uploader for the studio main panel.
 *
 * Drop a DOCX → auto-derive the template name from the filename → kick off
 * `useStudioStore.uploadTemplate` → flow through hover / uploading / success
 * animation states → invoke `onUploadSuccess` with the new templateId. The
 * toolbar's "Upload" button still opens UploadTemplateModal — only the
 * main-panel empty-state uses this inline flow.
 */
export const StudioTemplateUploader = ({
  onUploadSuccess,
}: StudioTemplateUploaderProps): ReactElement => {
  const uploadTemplate = useStudioStore((s) => s.uploadTemplate);
  const [visualState, setVisualState] = useState<UploadVisualState>('idle');
  const [error, setError] = useState<string | null>(null);

  const handleAccepted = useCallback(
    async (file: File) => {
      setError(null);
      setVisualState('uploading');
      const name = deriveTemplateName(file.name);
      const result = await uploadTemplate(name, file);
      if (result.success && result.data) {
        const templateId = result.data;
        setVisualState('success');
        window.setTimeout(() => onUploadSuccess(templateId), SUCCESS_HOLD_MS);
      } else {
        setVisualState('idle');
        setError(result.error ?? 'Upload failed.');
      }
    },
    [uploadTemplate, onUploadSuccess],
  );

  const onDrop = useCallback(
    (accepted: File[], rejections: FileRejection[]) => {
      if (rejections.length > 0) {
        const code = rejections[0].errors[0]?.code;
        setError(
          code === 'file-too-large'
            ? 'File is larger than 10 MB.'
            : code === 'file-invalid-type'
              ? 'Only DOCX files are supported.'
              : (rejections[0].errors[0]?.message ?? 'File rejected.'),
        );
        return;
      }
      const file = accepted[0];
      if (file) void handleAccepted(file);
    },
    [handleAccepted],
  );

  const isLocked = visualState === 'uploading' || visualState === 'success';

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: { [DOCX_MIME]: ['.docx'] },
    maxSize: MAX_SIZE_BYTES,
    multiple: false,
    noClick: true,
    noKeyboard: true,
    disabled: isLocked,
  });

  const effectiveState: UploadVisualState =
    isDragActive && !isLocked ? 'hover' : visualState;
  const isIdleOrHover = effectiveState === 'idle' || effectiveState === 'hover';

  return (
    <div className="flex h-full w-full items-center justify-center px-6 py-6">
      <div
        {...getRootProps({
          'aria-label': 'DOCX dropzone',
          'aria-disabled': isLocked,
        })}
        className={`flex w-full max-w-xl flex-col items-center justify-center rounded-2xl border-2 border-dashed px-8 py-10 text-center shadow-sm transition-colors ${
          effectiveState === 'hover'
            ? 'border-app-accent bg-indigo-50 dark:bg-slate-800'
            : effectiveState === 'uploading' || effectiveState === 'success'
              ? 'border-emerald-400 bg-emerald-50 dark:bg-slate-800'
              : 'border-app-border-strong bg-surface-muted hover:border-app-accent hover:bg-indigo-50 dark:hover:bg-slate-800'
        }`}
      >
        <input {...getInputProps()} />
        <UploadStateHero state={effectiveState} fileTypeLabel="DOCX" />
        <h3 className="mb-2 text-lg font-semibold text-text">Upload Legal Document</h3>
        <p className="mb-2 text-sm text-muted">
          {effectiveState === 'uploading'
            ? 'Generating your template…'
            : effectiveState === 'success'
              ? 'Template ready — opening your workspace…'
              : effectiveState === 'hover'
                ? 'Release to start upload instantly.'
                : 'Drop a DOCX here or click the button below to browse.'}
        </p>
        <p className="mb-4 text-xs text-subtle">
          DOCX only · max 10 MB · auto-named from filename (rename later).
        </p>
        {error && (
          <div className="mb-3 rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-2 text-sm text-app-danger-text">
            {error}
          </div>
        )}
        {isIdleOrHover && (
          <Button
            onClick={(e) => {
              e.stopPropagation();
              open();
            }}
            className="inline-flex items-center gap-3 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg transition-all duration-200 hover:scale-[1.01] hover:from-indigo-700 hover:to-purple-700 hover:shadow-[0_16px_34px_-16px_rgba(99,102,241,0.55)]"
          >
            Select DOCX File
          </Button>
        )}
      </div>
    </div>
  );
};

export default StudioTemplateUploader;
