import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import { Modal } from '@/components/common';
import { useStudioStore } from '@/stores/useStudioStore';
import { useToastStore } from '@/stores/useToastStore';

interface NewCaseModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const PDF_MIME = 'application/pdf';
const MAX_SIZE_BYTES = 25 * 1024 * 1024;

export const NewCaseModal = ({ isOpen, onClose }: NewCaseModalProps): ReactElement => {
  const createCase = useStudioStore((state) => state.createCase);
  const isCreatingCase = useStudioStore((state) => state.isCreatingCase);
  const addToast = useToastStore((state) => state.addToast);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setSelectedFile(null);
      setLocalError(null);
    }
  }, [isOpen]);

  const onDrop = useCallback((accepted: File[], rejections: FileRejection[]) => {
    setLocalError(null);
    if (rejections.length > 0) {
      const code = rejections[0].errors[0]?.code;
      if (code === 'file-too-large') setLocalError('File is larger than 25 MB.');
      else if (code === 'file-invalid-type') setLocalError('Only PDF files are supported.');
      else setLocalError(rejections[0].errors[0]?.message || 'File rejected.');
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
  });

  const handleUpload = async () => {
    if (!selectedFile) {
      setLocalError('Pick a PDF file first.');
      return;
    }
    setLocalError(null);
    const result = await createCase(selectedFile);
    if (result.success && result.data) {
      const { case: created, case_file_chunks_indexed, gmail_emails_indexed, courtdrive_emails_indexed } = result.data;
      addToast(
        `Case ${created.case_number} ingested · ${case_file_chunks_indexed} PDF chunks · ${gmail_emails_indexed} Gmail · ${courtdrive_emails_indexed} Court Drive`,
        'success'
      );
      onClose();
    } else {
      setLocalError(result.error ?? 'Failed to create case.');
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl">
      <div className="flex flex-col">
        <header className="border-b border-border px-6 py-5">
          <h2 className="text-base font-semibold text-text-secondary">Upload Petition</h2>
          <p className="mt-1 text-xs text-muted">
            Claude will read the PDF to extract the case number and debtor name, then index the
            petition and matching Gmail / Court Drive emails into the case's vector collections.
          </p>
        </header>

        <div className="space-y-4 px-6 py-5">
          <div
            {...getRootProps()}
            onClick={open}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              isDragReject
                ? 'border-red-300 bg-app-danger-soft'
                : isDragActive
                  ? 'border-indigo-400 bg-app-accent-soft'
                  : selectedFile
                    ? 'border-emerald-300 bg-app-success-soft'
                    : 'border-border bg-surface-muted hover:border-indigo-300 hover:bg-surface-muted'
            }`}
          >
            <input {...getInputProps()} />
            {selectedFile ? (
              <>
                <svg
                  className="h-10 w-10 text-emerald-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                  />
                </svg>
                <p className="text-sm font-semibold text-app-success-text">{selectedFile.name}</p>
                <p className="text-xs text-muted">
                  {(selectedFile.size / 1024).toFixed(1)} KB · click to replace
                </p>
              </>
            ) : (
              <>
                <svg
                  className="h-10 w-10 text-indigo-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 17v-2a4 4 0 014-4h3m-7 6h10a2 2 0 002-2V7a2 2 0 00-2-2h-5l-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2h2"
                  />
                </svg>
                <p className="text-sm font-semibold text-text-secondary">
                  {isDragActive ? 'Drop it here' : 'Drop a bankruptcy petition PDF or click to browse'}
                </p>
                <p className="text-xs text-muted">PDF only · max 25 MB</p>
              </>
            )}
          </div>

          {localError && (
            <div className="rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-2 text-sm text-app-danger-text">
              {localError}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border bg-surface-muted px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border bg-surface px-4 py-2 text-sm text-text-secondary hover:bg-surface-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile || isCreatingCase}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:from-indigo-700 hover:to-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isCreatingCase && (
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
            {isCreatingCase ? 'Uploading…' : 'Upload'}
          </button>
        </footer>
      </div>
    </Modal>
  );
};

export default NewCaseModal;
