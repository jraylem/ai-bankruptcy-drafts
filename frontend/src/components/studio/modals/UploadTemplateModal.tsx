import { useCallback, useEffect, useState, type ReactElement } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import Lottie from 'lottie-react';
import { FiUploadCloud, FiCheckCircle } from 'react-icons/fi';
import { useStudioStore } from '@/stores/useStudioStore';
import { DOCX_MIME, MAX_SIZE_BYTES, deriveTemplateName } from '@/utils/studio/templateUpload';
import uploadSearchAnimation from '@/assets/lottie/upload-search.json';

interface UploadTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadSuccess?: (templateId: string) => void;
}

const PROCESSING_PHRASES: Array<[string, string]> = [
  ['Reviewing', 'the record'],
  ['Examining', 'the pleadings'],
  ['Construing', 'the clauses'],
  ['Adjudicating', 'the exhibits'],
  ['Parsing', 'the recitals'],
  ['Deliberating', 'on precedent'],
  ['Annotating', 'the margins'],
  ['Redlining', 'the draft'],
  ['Interpreting', 'the statute'],
  ['Cross-referencing', 'citations'],
  ['Marshalling', 'the evidence'],
  ['Stipulating', 'the facts'],
  ['Brief-checking', 'the footnotes'],
  ['Calendaring', 'deadlines'],
];

export const UploadTemplateModal = ({ isOpen, onClose, onUploadSuccess }: UploadTemplateModalProps): ReactElement | null => {
  const { uploadTemplate, isUploadingTemplate } = useStudioStore();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [templateName, setTemplateName] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);
  const [verbIndex, setVerbIndex] = useState(0);

  useEffect(() => {
    if (!isOpen) {
      setSelectedFile(null);
      setTemplateName('');
      setLocalError(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isUploadingTemplate) return;
    setVerbIndex(0);
    const id = window.setInterval(() => {
      setVerbIndex((i) => (i + 1) % PROCESSING_PHRASES.length);
    }, 1800);
    return () => window.clearInterval(id);
  }, [isUploadingTemplate]);

  const onDrop = useCallback((accepted: File[], rejections: FileRejection[]) => {
    setLocalError(null);

    if (rejections.length > 0) {
      const firstRejection = rejections[0];
      const reason = firstRejection.errors[0]?.code;
      if (reason === 'file-too-large') {
        setLocalError('File is larger than 10 MB.');
      } else if (reason === 'file-invalid-type') {
        setLocalError('Only DOCX files are supported.');
      } else {
        setLocalError(firstRejection.errors[0]?.message || 'File rejected.');
      }
      return;
    }

    const file = accepted[0];
    if (!file) return;

    setSelectedFile(file);
    setTemplateName((prev) => prev || deriveTemplateName(file.name));
  }, []);

  const { getRootProps, getInputProps, isDragActive, isDragReject, open } = useDropzone({
    onDrop,
    accept: { [DOCX_MIME]: ['.docx'] },
    maxSize: MAX_SIZE_BYTES,
    multiple: false,
    noClick: true,
    noKeyboard: true,
  });

  const handleUpload = async () => {
    if (!selectedFile) {
      setLocalError('Pick a DOCX file first.');
      return;
    }
    if (!templateName.trim()) {
      setLocalError('Template name is required.');
      return;
    }
    setLocalError(null);
    const result = await uploadTemplate(templateName.trim(), selectedFile);
    if (result.success && result.data) {
      onUploadSuccess?.(result.data);
      onClose();
    } else {
      setLocalError(result.error ?? 'Upload failed.');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-app-overlay p-4 backdrop-blur-sm">
      <div className="flex w-full max-w-xl flex-col rounded-2xl bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-text-secondary">Upload Legal Document</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={isUploadingTemplate}
            className="rounded-lg p-1 text-subtle hover:bg-surface-muted hover:text-muted disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </header>

        {isUploadingTemplate ? (
          <div className="flex flex-col items-center justify-center gap-3 px-6 py-6">
            <Lottie
              animationData={uploadSearchAnimation}
              loop
              autoplay
              className="h-72 w-full"
            />
            <p
              key={verbIndex}
              className="animate-verb-in text-base font-semibold text-text-secondary"
            >
              {PROCESSING_PHRASES[verbIndex][0]} {PROCESSING_PHRASES[verbIndex][1]}…
            </p>
            <p className="text-sm text-muted">
              {selectedFile?.name ?? 'your file'} — this can take a moment.
            </p>
          </div>
        ) : (
        <>
        <div className="space-y-4 px-6 py-5">
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-muted">
              Document Name
            </label>
            <input
              type="text"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              placeholder="e.g. Motion to Extend Automatic Stay"
              className="w-full rounded-lg border border-border px-3 py-2 text-sm placeholder:text-subtle focus:border-app-accent focus:outline-none focus:ring-2 focus:ring-app-accent-soft"
            />
          </div>

          <div
            {...getRootProps()}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              isDragReject
                ? 'border-red-300 bg-app-danger-soft'
                : isDragActive
                  ? 'border-indigo-400 bg-app-accent-soft'
                  : selectedFile
                    ? 'border-emerald-300 bg-app-success-soft'
                    : 'border-border bg-surface-muted hover:border-indigo-300 hover:bg-surface-muted'
            }`}
            onClick={open}
          >
            <input {...getInputProps()} />
            {selectedFile ? (
              <>
                <FiCheckCircle className="h-12 w-12 text-emerald-500" strokeWidth={1.75} />
                <p className="text-sm font-semibold text-app-success-text">{selectedFile.name}</p>
                <p className="text-xs text-muted">
                  {(selectedFile.size / 1024).toFixed(1)} KB · click to replace
                </p>
              </>
            ) : (
              <>
                <FiUploadCloud className="h-12 w-12 text-indigo-500" strokeWidth={1.75} />
                <p className="text-sm font-semibold text-text-secondary">
                  {isDragActive ? 'Drop it here' : 'Drop a DOCX here or click to browse'}
                </p>
                <p className="text-xs text-muted">DOCX only · max 10 MB</p>
              </>
            )}
          </div>

          {localError && (
            <div className="rounded-lg border border-app-danger-soft bg-app-danger-soft px-4 py-2 text-sm text-app-danger-text">
              {localError}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-text-secondary hover:bg-surface-muted"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile}
            className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:from-indigo-700 hover:to-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Upload
          </button>
        </footer>
        </>
        )}
      </div>
    </div>
  );
};

export default UploadTemplateModal;
