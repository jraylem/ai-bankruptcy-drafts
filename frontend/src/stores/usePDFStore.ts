import { create } from 'zustand';
import { PDF_CONFIG } from '@/constants';
import type { PDFDocument } from '@/types';
import * as pdfjsLib from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { useToastStore } from './useToastStore';
import { pdfService } from '@/services/pdf.service';

// Configure PDF.js worker
pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;

interface CachedPDF {
  pdf: PDFDocument;
  pdfDocument: PDFDocumentProxy;
}

/**
 * Per-document slice. The store holds these keyed by an arbitrary
 * string (`session-<id>` for the legacy session flow, `case-<id>` for
 * the case workspace, `inbox-<id>` for the inbox drawer) so two
 * consumers (e.g. the split-screen case panes) can each display their
 * own PDF without fighting over a global active doc.
 */
export interface PDFSlice {
  pdf: PDFDocument | null;
  pdfDocument: PDFDocumentProxy | null;
  currentPage: number;
  numPages: number;
  scale: number;
  isLoadingPDF: boolean;
  error: string | null;
}

export const EMPTY_PDF_SLICE: PDFSlice = Object.freeze({
  pdf: null,
  pdfDocument: null,
  currentPage: 1,
  numPages: 0,
  scale: PDF_CONFIG.DEFAULT_SCALE,
  isLoadingPDF: false,
  error: null,
});

interface PDFState {
  /** Per-key slices. Reads should fall back to EMPTY_PDF_SLICE. */
  byKey: Record<string, PDFSlice>;
  isDeleting: boolean;
  pdfCache: Map<string, CachedPDF>;

  setPDFForKey: (
    key: string,
    pdf: PDFDocument,
    pdfDocument: PDFDocumentProxy,
  ) => void;
  /** Legacy session flow — fetches via /api/sessions/{id}/pdfs. */
  loadPDFForSession: (sessionId: string) => Promise<void>;
  /**
   * Activate a PDF in the viewer by URL — used for case-keyed flows that
   * don't go through the legacy /api/sessions/{id}/pdfs endpoint (e.g.
   * Draft v2's per-case petition preview). `cacheKey` is an arbitrary
   * namespaced string (e.g. `case-{case_id}`); subsequent calls with the
   * same key hit the cache and switch instantly.
   *
   * Returns true on success, false on any fetch/decode failure. The
   * caller can use the return value to drive a fallback (e.g. re-sign
   * the URL and retry) without having to subscribe to the error state.
   */
  loadPDFFromUrl: (
    cacheKey: string,
    url: string,
    displayName: string,
  ) => Promise<boolean>;
  deletePDF: (sessionId: string) => Promise<void>;
  setCurrentPage: (key: string, page: number) => void;
  setScale: (key: string, scale: number) => void;
  /** Drop a single key's slice. */
  clearPDF: (key: string) => void;
  clearCache: (sessionId?: string) => void;
  nextPage: (key: string) => void;
  prevPage: (key: string) => void;
  zoomIn: (key: string) => void;
  zoomOut: (key: string) => void;
}

type StoreSet = (
  partial:
    | Partial<PDFState>
    | ((state: PDFState) => Partial<PDFState>),
) => void;

function patchSlice(
  set: StoreSet,
  key: string,
  patch: Partial<PDFSlice>,
): void {
  set((state) => {
    const prior = state.byKey[key] ?? EMPTY_PDF_SLICE;
    return {
      byKey: {
        ...state.byKey,
        [key]: { ...prior, ...patch },
      },
    };
  });
}

export const usePDFStore = create<PDFState>((set, get) => ({
  byKey: {},
  isDeleting: false,
  pdfCache: new Map(),

  setPDFForKey: (key, pdf, pdfDocument) => {
    set((state) => {
      const newCache = new Map(state.pdfCache);
      newCache.set(key, { pdf, pdfDocument });
      const prior = state.byKey[key] ?? EMPTY_PDF_SLICE;
      return {
        pdfCache: newCache,
        byKey: {
          ...state.byKey,
          [key]: {
            ...prior,
            pdf,
            pdfDocument,
            currentPage: 1,
            numPages: pdfDocument.numPages,
            scale: PDF_CONFIG.DEFAULT_SCALE,
            isLoadingPDF: false,
            error: null,
          },
        },
      };
    });
  },

  setCurrentPage: (key, page) => {
    const slice = get().byKey[key];
    if (!slice) return;
    if (page >= 1 && page <= slice.numPages) {
      patchSlice(set, key, { currentPage: page });
    }
  },

  setScale: (key, scale) => {
    const clampedScale = Math.max(PDF_CONFIG.MIN_SCALE, Math.min(PDF_CONFIG.MAX_SCALE, scale));
    const slice = get().byKey[key];
    if (slice && slice.scale === clampedScale) return;
    patchSlice(set, key, { scale: clampedScale });
  },

  clearPDF: (key) => {
    set((state) => {
      if (!(key in state.byKey)) return state;
      const nextByKey = { ...state.byKey };
      delete nextByKey[key];
      return { byKey: nextByKey };
    });
  },

  clearCache: (sessionId?: string) => {
    set((state) => {
      const newCache = new Map(state.pdfCache);
      if (sessionId) {
        newCache.delete(sessionId);
      } else {
        newCache.clear();
      }
      return { pdfCache: newCache };
    });
  },

  nextPage: (key) => {
    const slice = get().byKey[key];
    if (!slice) return;
    if (slice.currentPage < slice.numPages) {
      patchSlice(set, key, { currentPage: slice.currentPage + 1 });
    }
  },

  prevPage: (key) => {
    const slice = get().byKey[key];
    if (!slice) return;
    if (slice.currentPage > 1) {
      patchSlice(set, key, { currentPage: slice.currentPage - 1 });
    }
  },

  zoomIn: (key) => {
    const slice = get().byKey[key];
    if (!slice) return;
    const newScale = Math.min(slice.scale + PDF_CONFIG.SCALE_STEP, PDF_CONFIG.MAX_SCALE);
    patchSlice(set, key, { scale: newScale });
  },

  zoomOut: (key) => {
    const slice = get().byKey[key];
    if (!slice) return;
    const newScale = Math.max(slice.scale - PDF_CONFIG.SCALE_STEP, PDF_CONFIG.MIN_SCALE);
    patchSlice(set, key, { scale: newScale });
  },

  deletePDF: async (sessionId: string) => {
    set({ isDeleting: true });
    patchSlice(set, sessionId, { error: null });

    try {
      const response = await pdfService.deletePDFFromSession(sessionId);

      if (response.error) {
        patchSlice(set, sessionId, { error: response.error });
        set({ isDeleting: false });
        useToastStore.getState().addToast(response.error, 'error');
        return;
      }

      set((state) => {
        const newCache = new Map(state.pdfCache);
        newCache.delete(sessionId);
        const nextByKey = { ...state.byKey };
        delete nextByKey[sessionId];
        return {
          pdfCache: newCache,
          byKey: nextByKey,
          isDeleting: false,
        };
      });

      useToastStore.getState().addToast('PDF deleted successfully', 'success');
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : 'Failed to delete PDF';
      patchSlice(set, sessionId, { error: errorMsg });
      set({ isDeleting: false });
      useToastStore.getState().addToast(errorMsg, 'error');
    }
  },

  loadPDFForSession: async (sessionId: string) => {
    if (!sessionId) return;

    // Check cache first for instant switching
    const cached = get().pdfCache.get(sessionId);
    if (cached) {
      patchSlice(set, sessionId, {
        pdf: cached.pdf,
        pdfDocument: cached.pdfDocument,
        currentPage: 1,
        numPages: cached.pdfDocument.numPages,
        scale: PDF_CONFIG.DEFAULT_SCALE,
        isLoadingPDF: false,
        error: null,
      });
      return;
    }

    patchSlice(set, sessionId, { isLoadingPDF: true, error: null });

    try {
      const response = await pdfService.listPDFsBySession(sessionId);

      if (response.error) {
        patchSlice(set, sessionId, {
          error: response.error,
          isLoadingPDF: false,
          pdf: null,
          pdfDocument: null,
        });
        return;
      }

      const pdfs = response.data?.pdfs;

      if (!pdfs || !Array.isArray(pdfs) || pdfs.length === 0) {
        patchSlice(set, sessionId, {
          pdf: null,
          pdfDocument: null,
          currentPage: 1,
          numPages: 0,
          isLoadingPDF: false,
        });
        return;
      }

      const pdfMetadata = pdfs[0];

      if (!pdfMetadata || !pdfMetadata.id) {
        console.error('Invalid PDF metadata received:', pdfMetadata);
        patchSlice(set, sessionId, {
          pdf: null,
          pdfDocument: null,
          currentPage: 1,
          numPages: 0,
          isLoadingPDF: false,
        });
        return;
      }

      const blob = await pdfService.downloadPDF(pdfMetadata.id);
      const arrayBuffer = await blob.arrayBuffer();
      const loadingTask = pdfjsLib.getDocument({
        data: arrayBuffer,
        verbosity: 0,
      });
      const pdf = await loadingTask.promise;

      if (!pdf || !pdf.numPages) {
        throw new Error('Invalid PDF file or corrupted document.');
      }

      const pdfDocument: PDFDocument = {
        id: pdfMetadata.id,
        name: pdfMetadata.original_filename || pdfMetadata.filename,
        url: pdfMetadata.download_url,
        uploadedAt: new Date(pdfMetadata.uploaded_at),
        numPages: pdf.numPages,
      };

      get().setPDFForKey(sessionId, pdfDocument, pdf);
    } catch (error) {
      console.error('Error loading PDF for session:', sessionId, error);
      patchSlice(set, sessionId, {
        error: null,
        isLoadingPDF: false,
        pdf: null,
        pdfDocument: null,
      });
    }
  },

  loadPDFFromUrl: async (cacheKey: string, url: string, displayName: string): Promise<boolean> => {
    if (!cacheKey || !url) return false;

    const cached = get().pdfCache.get(cacheKey);
    if (cached) {
      patchSlice(set, cacheKey, {
        pdf: cached.pdf,
        pdfDocument: cached.pdfDocument,
        currentPage: 1,
        numPages: cached.pdfDocument.numPages,
        scale: PDF_CONFIG.DEFAULT_SCALE,
        isLoadingPDF: false,
        error: null,
      });
      return true;
    }

    patchSlice(set, cacheKey, { isLoadingPDF: true, error: null });

    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Failed to download PDF (${response.status})`);
      const arrayBuffer = await response.arrayBuffer();
      const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer, verbosity: 0 });
      const pdf = await loadingTask.promise;
      if (!pdf || !pdf.numPages) throw new Error('Invalid PDF file or corrupted document.');

      const pdfDocument: PDFDocument = {
        id: cacheKey,
        name: displayName,
        url,
        uploadedAt: new Date(),
        numPages: pdf.numPages,
      };

      get().setPDFForKey(cacheKey, pdfDocument, pdf);
      return true;
    } catch (error) {
      console.error('Error loading PDF from url:', cacheKey, error);
      const message = error instanceof Error ? error.message : 'Failed to load PDF';
      patchSlice(set, cacheKey, {
        pdf: null,
        pdfDocument: null,
        isLoadingPDF: false,
        error: message,
      });
      return false;
    }
  },
}));
