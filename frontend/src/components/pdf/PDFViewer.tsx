import React, { useCallback, useEffect, useRef, useState } from 'react';
import { EMPTY_PDF_SLICE, usePDFStore } from '@/stores/usePDFStore';
import * as pdfjsLib from 'pdfjs-dist';
import type { RenderTask } from 'pdfjs-dist';
import { PDF_CONFIG } from '@/constants';
import {
  indexPDFTextByPage,
  usePDFSearchCore,
  type PDFTextDocumentSource,
} from '@/hooks/usePDFSearchCore';

interface PDFViewerProps {
  /**
   * Identifies which slice in `usePDFStore.byKey` this viewer renders.
   * Matches the `cacheKey` passed to `loadPDFFromUrl`/`setPDFForKey`
   * (`case-<caseId>` for case workspace, `inbox-<entryId>` for inbox).
   */
  pdfKey: string;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  showPageJumpInput?: boolean;
}

interface IndexedTextItem {
  height: number;
  str: string;
  transform: number[];
  width: number;
}

const SEARCH_INPUT_DEBOUNCE_MS = 180;

const isIndexedTextItem = (item: unknown): item is IndexedTextItem => {
  if (typeof item !== 'object' || item === null) return false;
  const candidate = item as {
    height?: unknown;
    str?: unknown;
    transform?: unknown;
    width?: unknown;
  };

  return (
    typeof candidate.str === 'string' &&
    Array.isArray(candidate.transform) &&
    candidate.transform.every((entry) => typeof entry === 'number') &&
    typeof candidate.width === 'number' &&
    typeof candidate.height === 'number'
  );
};

export const PDFViewer: React.FC<PDFViewerProps> = ({
  pdfKey,
  isCollapsed = false,
  onToggleCollapse,
  showPageJumpInput = false,
}) => {
  const slice = usePDFStore((s) => s.byKey[pdfKey] ?? EMPTY_PDF_SLICE);
  const {
    pdf: currentPDF,
    pdfDocument,
    currentPage,
    numPages,
    scale,
  } = slice;

  const prevPageAction = usePDFStore((s) => s.prevPage);
  const nextPageAction = usePDFStore((s) => s.nextPage);
  const zoomInAction = usePDFStore((s) => s.zoomIn);
  const zoomOutAction = usePDFStore((s) => s.zoomOut);
  const setScaleAction = usePDFStore((s) => s.setScale);
  const setCurrentPageAction = usePDFStore((s) => s.setCurrentPage);

  const prevPage = useCallback(() => prevPageAction(pdfKey), [prevPageAction, pdfKey]);
  const nextPage = useCallback(() => nextPageAction(pdfKey), [nextPageAction, pdfKey]);
  const zoomIn = useCallback(() => zoomInAction(pdfKey), [zoomInAction, pdfKey]);
  const zoomOut = useCallback(() => zoomOutAction(pdfKey), [zoomOutAction, pdfKey]);
  const setScale = useCallback(
    (next: number) => setScaleAction(pdfKey, next),
    [setScaleAction, pdfKey],
  );
  const setCurrentPage = useCallback(
    (page: number) => setCurrentPageAction(pdfKey, page),
    [setCurrentPageAction, pdfKey],
  );

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const renderTaskRef = useRef<RenderTask | null>(null);
  const textLayerTaskRef = useRef<{ cancel: () => void; promise: Promise<void> } | null>(null);
  const isRenderingRef = useRef(false);
  const resizeFrameRef = useRef<number | null>(null);
  const lastAppliedScaleRef = useRef<number | null>(null);
  const indexRunIdRef = useRef(0);

  const [indexedTextByPage, setIndexedTextByPage] = useState<IndexedTextItem[][]>([]);
  const [isIndexingText, setIsIndexingText] = useState(false);
  const [pageInputValue, setPageInputValue] = useState('1');

  const {
    clearSearch,
    goToNextMatch,
    goToPreviousMatch,
    hasMatches,
    matchLabel,
    matchLookupByPageAndItem,
    resetSearch,
    searchInputValue,
    searchKeyword,
    setSearchInputValue,
  } = usePDFSearchCore<IndexedTextItem>({
    indexedTextByPage,
    onActivateMatchPage: setCurrentPage,
    debounceMs: SEARCH_INPUT_DEBOUNCE_MS,
  });

  const resolveAdaptiveScale = (containerWidth: number) => {
    if (containerWidth >= 2200) return 2.75;
    if (containerWidth >= 1700) return 2.25;
    if (containerWidth >= 1150) return 1.25;
    return 1.0;
  };

  useEffect(() => {
    if (isCollapsed || !pdfDocument || !containerRef.current) {
      return;
    }

    lastAppliedScaleRef.current = null;

    const applyAdaptiveScale = (width: number) => {
      const nextScale = Math.max(
        PDF_CONFIG.MIN_SCALE,
        Math.min(PDF_CONFIG.MAX_SCALE, resolveAdaptiveScale(width))
      );

      if (lastAppliedScaleRef.current === nextScale) {
        return;
      }

      lastAppliedScaleRef.current = nextScale;
      setScale(nextScale);
    };

    const element = containerRef.current;
    applyAdaptiveScale(element.clientWidth);

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;

      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
      }

      resizeFrameRef.current = window.requestAnimationFrame(() => {
        applyAdaptiveScale(entry.contentRect.width);
      });
    });

    resizeObserver.observe(element);

    return () => {
      resizeObserver.disconnect();
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
        resizeFrameRef.current = null;
      }
    };
  }, [isCollapsed, pdfDocument, setScale]);

  useEffect(() => {
    indexRunIdRef.current += 1;
    const runId = indexRunIdRef.current;

    resetSearch();
    setIndexedTextByPage([]);

    if (!pdfDocument) {
      setIsIndexingText(false);
      return;
    }

    let cancelled = false;
    setIsIndexingText(true);

    const indexAllPages = async () => {
      try {
        const nextIndexedTextByPage = await indexPDFTextByPage({
          pdfDocument: pdfDocument as PDFTextDocumentSource,
          isTextItem: isIndexedTextItem,
          selectItem: (item) => ({
            str: item.str,
            transform: item.transform,
            width: item.width,
            height: item.height,
          }),
          shouldAbort: () => cancelled || runId !== indexRunIdRef.current,
        });

        if (cancelled || runId !== indexRunIdRef.current) return;
        setIndexedTextByPage(nextIndexedTextByPage);
      } catch (error) {
        if (cancelled || runId !== indexRunIdRef.current) return;
        console.error('Error indexing PDF text:', error);
      } finally {
        if (!cancelled && runId === indexRunIdRef.current) {
          setIsIndexingText(false);
        }
      }
    };

    void indexAllPages();

    return () => {
      cancelled = true;
    };
  }, [pdfDocument, resetSearch]);

  useEffect(() => {
    setPageInputValue(String(currentPage));
  }, [currentPage]);

  const commitPageInput = useCallback(() => {
    if (!numPages) return;

    const parsedPage = Number.parseInt(pageInputValue.trim(), 10);
    if (Number.isNaN(parsedPage)) {
      setPageInputValue(String(currentPage));
      return;
    }

    const clampedPage = Math.min(Math.max(parsedPage, 1), numPages);
    setCurrentPage(clampedPage);
    setPageInputValue(String(clampedPage));
  }, [currentPage, numPages, pageInputValue, setCurrentPage]);

  const drawHighlights = useCallback(
    (
      context: CanvasRenderingContext2D,
      viewport: { scale: number; transform: number[] },
      pageMatches: Map<number, Array<{ end: number; isActive: boolean; start: number }>>,
      pageTextItems: IndexedTextItem[]
    ) => {
      pageMatches.forEach((itemMatches, itemIndex) => {
        const textItem = pageTextItems[itemIndex];
        if (!textItem || !textItem.str) return;

        const transformed = pdfjsLib.Util.transform(viewport.transform, textItem.transform) as number[];
        const x = transformed[4];
        const y = transformed[5];
        const angle = Math.atan2(transformed[1], transformed[0]);
        const fontHeight = Math.max(Math.hypot(transformed[2], transformed[3]), 8);
        const scaledWidth = Math.max(
          textItem.width * viewport.scale,
          fontHeight * 0.35 * textItem.str.length
        );

        if (![x, y, fontHeight, scaledWidth].every((value) => Number.isFinite(value))) {
          return;
        }

        const textLength = Math.max(textItem.str.length, 1);
        const baselineOffset = fontHeight * 0.82;
        const boxHeight = Math.max(fontHeight * 1.08, 10);

        context.save();
        context.translate(x, y);
        if (angle) {
          context.rotate(angle);
        }

        itemMatches.forEach((match) => {
          const startRatio = Math.min(Math.max(match.start / textLength, 0), 1);
          const endRatio = Math.min(Math.max(match.end / textLength, 0), 1);
          const segmentX = scaledWidth * startRatio;
          const segmentWidth = Math.max(scaledWidth * (endRatio - startRatio), 2);

          context.fillStyle = match.isActive ? 'rgba(245, 158, 11, 0.72)' : 'rgba(250, 204, 21, 0.32)';
          context.fillRect(segmentX, -baselineOffset, segmentWidth, boxHeight);
        });

        context.restore();
      });
    },
    []
  );

  useEffect(() => {
    let isCancelled = false;
    const textLayerElement = textLayerRef.current;

    const renderPage = async () => {
      if (isCollapsed || !pdfDocument || !canvasRef.current) return;

      if (renderTaskRef.current) {
        try {
          renderTaskRef.current.cancel();
        } catch {
          // Ignore cancellation errors
        }
        renderTaskRef.current = null;
      }

      while (isRenderingRef.current && !isCancelled) {
        await new Promise((resolve) => setTimeout(resolve, 10));
      }

      if (isCancelled) return;
      isRenderingRef.current = true;

      try {
        const page = await pdfDocument.getPage(currentPage);

        if (isCancelled) {
          isRenderingRef.current = false;
          return;
        }

        const viewport = page.getViewport({ scale });

        const canvas = canvasRef.current;
        if (!canvas || isCancelled) {
          isRenderingRef.current = false;
          return;
        }

        const context = canvas.getContext('2d');
        if (!context || isCancelled) {
          isRenderingRef.current = false;
          return;
        }

        const devicePixelRatio = window.devicePixelRatio || 1;

        context.setTransform(1, 0, 0, 1, 0, 0);
        context.clearRect(0, 0, canvas.width, canvas.height);

        canvas.width = viewport.width * devicePixelRatio;
        canvas.height = viewport.height * devicePixelRatio;

        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        canvas.style.backgroundColor = '#ffffff';

        context.scale(devicePixelRatio, devicePixelRatio);
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, viewport.width, viewport.height);

        if (isCancelled) {
          isRenderingRef.current = false;
          return;
        }

        const renderContext = {
          canvasContext: context,
          viewport: viewport,
        };

        renderTaskRef.current = page.render(renderContext);
        await renderTaskRef.current.promise;

        const pageMatches = matchLookupByPageAndItem.get(currentPage);
        if (pageMatches && searchKeyword) {
          const pageTextItems = indexedTextByPage[currentPage - 1];
          if (pageTextItems && pageTextItems.length > 0) {
            drawHighlights(context, viewport, pageMatches, pageTextItems);
          }
        }

        if (textLayerTaskRef.current) {
          try {
            textLayerTaskRef.current.cancel();
          } catch {
            // Ignore cancellation errors
          }
          textLayerTaskRef.current = null;
        }

        const textLayerDiv = textLayerRef.current;
        if (textLayerDiv && !isCancelled) {
          textLayerDiv.replaceChildren();
          textLayerDiv.style.width = `${viewport.width}px`;
          textLayerDiv.style.height = `${viewport.height}px`;
          textLayerDiv.style.setProperty('--scale-factor', String(viewport.scale));

          const textContent = await page.getTextContent();

          if (!isCancelled) {
            textLayerTaskRef.current = pdfjsLib.renderTextLayer({
              textContentSource: textContent,
              container: textLayerDiv,
              viewport,
              textDivs: [],
            });
            try {
              await textLayerTaskRef.current.promise;
            } catch (error) {
              if (!isCancelled) {
                console.warn('Text layer render failed:', error);
              }
            } finally {
              if (!isCancelled) {
                textLayerTaskRef.current = null;
              }
            }
          }
        }

        if (!isCancelled) {
          renderTaskRef.current = null;
        }
        isRenderingRef.current = false;
      } catch (error: unknown) {
        isRenderingRef.current = false;
        renderTaskRef.current = null;

        if (
          error &&
          typeof error === 'object' &&
          'name' in error &&
          error.name === 'RenderingCancelledException'
        ) {
          return;
        }

        if (isCancelled) return;

        console.error('Error rendering page:', error);
        const canvas = canvasRef.current;
        if (canvas) {
          const context = canvas.getContext('2d');
          if (context) {
            context.clearRect(0, 0, canvas.width, canvas.height);
            context.font = '16px Arial';
            context.fillStyle = '#ff0000';
            context.textAlign = 'center';
            context.fillText('Error rendering page', canvas.width / 2, canvas.height / 2);
          }
        }
      }
    };

    void renderPage();

    return () => {
      isCancelled = true;
      if (renderTaskRef.current) {
        try {
          renderTaskRef.current.cancel();
        } catch {
          // Ignore cancellation errors
        }
        renderTaskRef.current = null;
      }
      if (textLayerTaskRef.current) {
        try {
          textLayerTaskRef.current.cancel();
        } catch {
          // Ignore cancellation errors
        }
        textLayerTaskRef.current = null;
      }
      if (textLayerElement) {
        textLayerElement.replaceChildren();
      }
    };
  }, [
    currentPage,
    drawHighlights,
    indexedTextByPage,
    isCollapsed,
    matchLookupByPageAndItem,
    pdfDocument,
    scale,
    searchKeyword,
  ]);

  if (!currentPDF || !pdfDocument) return null;

  const canGoPrevious = currentPage > 1;
  const canGoNext = currentPage < numPages;

  if (isCollapsed) {
    return (
      <div className="flex h-full w-16 flex-col items-center border-l border-border bg-surface py-3">
        <button
          onClick={onToggleCollapse}
          className="h-8 w-8 cursor-pointer rounded-lg text-muted transition-colors hover:bg-surface-muted hover:text-text-secondary"
          title="Expand PDF viewer"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M11 19l-7-7 7-7M18 5v14"
            />
          </svg>
        </button>

        <div className="mt-3 p-2 text-indigo-500">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>

        <div className="mt-1 text-xs text-muted">
          {currentPage}/{numPages}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col bg-page">
      <div className="pointer-events-none absolute inset-x-0 top-3 z-10 flex justify-center px-2">
        <div className="pointer-events-auto flex max-w-full items-center justify-center overflow-x-auto rounded-full bg-pdf-control px-3 py-1.5 backdrop-blur-xl">
          <div className="flex items-center gap-0.5 text-pdf-control-text">
            <button
              onClick={prevPage}
              disabled={!canGoPrevious}
              className="rounded-full p-1.5 transition-colors hover:bg-pdf-control-hover disabled:cursor-not-allowed disabled:opacity-40"
              title="Previous Page"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
            </button>

            <div className="flex w-[152px] flex-shrink-0 items-center justify-center gap-1 px-1 text-center text-xs font-medium text-pdf-control-text whitespace-nowrap">
              <span>Page</span>
              {showPageJumpInput ? (
                <input
                  type="text"
                  inputMode="numeric"
                  value={pageInputValue}
                  onChange={(event) =>
                    setPageInputValue(event.target.value.replace(/[^0-9]/g, ''))
                  }
                  onBlur={commitPageInput}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      commitPageInput();
                      event.currentTarget.blur();
                    }
                  }}
                  className="h-6 w-11 rounded border border-pdf-control-divider/80 bg-black/10 px-1 text-center text-xs text-pdf-control-text placeholder:text-pdf-control-text/70 focus:outline-none focus:ring-1 focus:ring-pdf-control-text/35"
                  aria-label="Jump to page"
                />
              ) : (
                <span>{currentPage}</span>
              )}
              <span className="whitespace-nowrap">of {numPages}</span>
            </div>

            <button
              onClick={nextPage}
              disabled={!canGoNext}
              className="rounded-full p-1.5 transition-colors hover:bg-pdf-control-hover disabled:cursor-not-allowed disabled:opacity-40"
              title="Next Page"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5l7 7-7 7"
                />
              </svg>
            </button>

            <div className="mx-1.5 h-5 w-px bg-pdf-control-divider" />

            <button
              onClick={zoomOut}
              className="rounded-full p-1.5 transition-colors hover:bg-pdf-control-hover"
              title="Zoom Out"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM13 10H7"
                />
              </svg>
            </button>

            <div className="min-w-[48px] text-center text-xs font-semibold text-pdf-control-text">
              {Math.round(scale * 100)}%
            </div>

            <button
              onClick={zoomIn}
              className="rounded-full p-1.5 transition-colors hover:bg-pdf-control-hover"
              title="Zoom In"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v6m3-3H7"
                />
              </svg>
            </button>

            <div className="mx-1.5 h-5 w-px bg-pdf-control-divider" />

            <div className="relative">
              <input
                type="text"
                value={searchInputValue}
                onChange={(event) => setSearchInputValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    if (event.shiftKey) {
                      goToPreviousMatch();
                    } else {
                      goToNextMatch();
                    }
                  }
                }}
                placeholder="Search"
                className="h-7 w-40 rounded-md border border-pdf-control-divider/80 bg-black/10 px-2 pr-6 text-xs text-pdf-control-text placeholder:text-pdf-control-text/70 focus:outline-none focus:ring-1 focus:ring-pdf-control-text/35"
                aria-label="Search PDF text"
              />
              {searchInputValue && (
                <button
                  onClick={clearSearch}
                  className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-0.5 text-pdf-control-text/70 transition-colors hover:bg-pdf-control-hover hover:text-pdf-control-text"
                  title="Clear Search"
                  aria-label="Clear Search"
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
            </div>

            <button
              onClick={goToPreviousMatch}
              disabled={!hasMatches}
              className="rounded-full p-1.5 transition-colors hover:bg-pdf-control-hover disabled:cursor-not-allowed disabled:opacity-40"
              title="Previous Match"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
              </svg>
            </button>

            <button
              onClick={goToNextMatch}
              disabled={!hasMatches}
              className="rounded-full p-1.5 transition-colors hover:bg-pdf-control-hover disabled:cursor-not-allowed disabled:opacity-40"
              title="Next Match"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            <div className="min-w-[60px] px-1 text-center text-xs font-medium text-pdf-control-text">
              {matchLabel}
            </div>

            {isIndexingText && (
              <div className="px-1 text-[11px] text-pdf-control-text/75">Indexing...</div>
            )}
          </div>
        </div>
      </div>

      <div
        ref={containerRef}
        className="flex-1 overflow-auto bg-transparent px-4 pb-4 pt-16"
        style={{ scrollbarColor: 'var(--app-border-strong) transparent' }}
      >
        <div className="inline-block min-w-full text-center">
          <div className="relative inline-block bg-white shadow-lg align-top">
            <canvas ref={canvasRef} className="block" />
            <div ref={textLayerRef} className="textLayer" />
          </div>
        </div>
      </div>
    </div>
  );
};
