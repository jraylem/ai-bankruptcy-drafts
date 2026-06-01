import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactElement,
} from 'react';

import {
  downloadCompletedDocumentAsPdf,
  getCompletedDocumentEnvelope,
} from '@/services/templateDraft.service';
import { useToastStore } from '@/stores/useToastStore';
import {
  sanitizeFilename,
  triggerBlobDownload,
  triggerFileDownload,
} from '@/utils/downloadFile';

/**
 * Small `Download ▾` dropdown rendered next to the close button in the
 * completed-draft viewer header. Offers DOCX (presigned R2 URL) and PDF
 * (server-side LibreOffice conversion, ~3-5s per request — no caching yet).
 *
 * Consumer shapes:
 *   - DOCX path: when `directUrl` is provided the menu uses it directly
 *     (the viewer already has the presigned URL in state); otherwise it
 *     fetches a fresh envelope via `getCompletedDocumentEnvelope`.
 *   - PDF path: always hits the BE `/download-pdf` endpoint. `childIndex`
 *     selects a bundle child; omit for the parent docx.
 */
interface DownloadMenuProps {
  logId: string;
  filename: string;
  directUrl?: string;
  childIndex?: number;
}

const DownloadIcon = (): ReactElement => (
  <svg
    className="h-3.5 w-3.5"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
  </svg>
);

const ChevronIcon = (): ReactElement => (
  <svg
    className="h-3 w-3"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export const DownloadMenu = ({
  logId,
  filename,
  directUrl,
  childIndex,
}: DownloadMenuProps): ReactElement => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [isBusy, setIsBusy] = useState<boolean>(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const addToast = useToastStore((state) => state.addToast);

  // Close on outside click + Escape.
  useEffect((): (() => void) | undefined => {
    if (!isOpen) return undefined;
    const handleOutsideClick = (event: MouseEvent): void => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    document.addEventListener('mousedown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    return (): void => {
      document.removeEventListener('mousedown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  const handleDownloadDocx = useCallback(
    async (event: ReactMouseEvent<HTMLButtonElement>): Promise<void> => {
      event.stopPropagation();
      setIsOpen(false);
      if (isBusy) return;
      const safeFilename: string = `${sanitizeFilename(filename)}.docx`;

      if (directUrl) {
        triggerFileDownload(directUrl, safeFilename);
        return;
      }

      setIsBusy(true);
      try {
        const result = await getCompletedDocumentEnvelope(logId);
        if (result.error || !result.data) {
          addToast(result.error ?? 'Failed to prepare download', 'error');
          return;
        }
        triggerFileDownload(result.data.parent_url, safeFilename);
      } finally {
        setIsBusy(false);
      }
    },
    [logId, filename, directUrl, addToast, isBusy],
  );

  const handleDownloadPdf = useCallback(
    async (event: ReactMouseEvent<HTMLButtonElement>): Promise<void> => {
      event.stopPropagation();
      setIsOpen(false);
      if (isBusy) return;
      const safeFilename: string = `${sanitizeFilename(filename)}.pdf`;

      setIsBusy(true);
      addToast('Converting to PDF — this can take a few seconds…', 'info');
      try {
        const blob: Blob = await downloadCompletedDocumentAsPdf(logId, { childIndex });
        triggerBlobDownload(blob, safeFilename);
      } catch (error: unknown) {
        const message: string =
          error instanceof Error ? error.message : 'PDF download failed';
        addToast(message, 'error');
      } finally {
        setIsBusy(false);
      }
    },
    [logId, filename, childIndex, addToast, isBusy],
  );

  const handleToggle = (event: ReactMouseEvent<HTMLButtonElement>): void => {
    event.stopPropagation();
    setIsOpen((previous) => !previous);
  };

  return (
    <div ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        onClick={handleToggle}
        disabled={isBusy}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Download document"
        title="Download document"
        className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full bg-app-accent px-3 text-xs font-semibold text-white shadow-sm transition hover:bg-app-accent/90 disabled:opacity-60"
      >
        <DownloadIcon />
        <span>Download</span>
        <ChevronIcon />
      </button>
      {isOpen && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-1 min-w-[7rem] overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg"
        >
          <button
            type="button"
            role="menuitem"
            onClick={handleDownloadDocx}
            disabled={isBusy}
            className="block w-full px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-text-secondary transition-colors hover:bg-surface-muted disabled:opacity-50"
          >
            DOCX
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={handleDownloadPdf}
            disabled={isBusy}
            className="block w-full px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-text-secondary transition-colors hover:bg-surface-muted disabled:opacity-50"
          >
            PDF
          </button>
        </div>
      )}
    </div>
  );
};
