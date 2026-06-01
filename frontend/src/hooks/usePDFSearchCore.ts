import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

export interface PDFIndexedTextItem {
  str: string;
}

export interface PDFSearchMatch {
  end: number;
  itemIndex: number;
  pageNumber: number;
  start: number;
}

export interface PDFHighlightRange {
  end: number;
  isActive: boolean;
  start: number;
}

export interface PDFTextDocumentSource {
  numPages: number;
  getPage: (pageNumber: number) => Promise<{
    getTextContent: () => Promise<{ items: unknown[] }>;
  }>;
}

interface UsePDFSearchCoreOptions<TItem extends PDFIndexedTextItem> {
  debounceMs?: number;
  indexedTextByPage: TItem[][];
  onActivateMatchPage?: (pageNumber: number) => void;
}

interface IndexPDFTextByPageOptions<TInput, TOutput extends PDFIndexedTextItem> {
  isTextItem: (item: unknown) => item is TInput;
  pdfDocument: PDFTextDocumentSource;
  selectItem: (item: TInput) => TOutput;
  shouldAbort?: () => boolean;
}

interface UsePDFSearchCoreResult {
  activeMatchIndex: number;
  clearSearch: () => void;
  goToMatch: (nextIndex: number) => void;
  goToNextMatch: () => void;
  goToPreviousMatch: () => void;
  hasMatches: boolean;
  matchLabel: string;
  matchLookupByPageAndItem: Map<number, Map<number, PDFHighlightRange[]>>;
  matches: PDFSearchMatch[];
  resetSearch: () => void;
  searchInputValue: string;
  searchKeyword: string;
  setSearchInputValue: Dispatch<SetStateAction<string>>;
}

const DEFAULT_SEARCH_INPUT_DEBOUNCE_MS = 180;

export const indexPDFTextByPage = async <TInput, TOutput extends PDFIndexedTextItem>({
  isTextItem,
  pdfDocument,
  selectItem,
  shouldAbort,
}: IndexPDFTextByPageOptions<TInput, TOutput>): Promise<TOutput[][]> => {
  const nextIndexedTextByPage: TOutput[][] = [];

  for (let pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber += 1) {
    if (shouldAbort?.()) {
      return nextIndexedTextByPage;
    }

    const page = await pdfDocument.getPage(pageNumber);
    if (shouldAbort?.()) {
      return nextIndexedTextByPage;
    }

    const textContent = await page.getTextContent();
    if (shouldAbort?.()) {
      return nextIndexedTextByPage;
    }

    const pageItems = (textContent.items as unknown[]).filter(isTextItem).map(selectItem);
    nextIndexedTextByPage.push(pageItems);
  }

  return nextIndexedTextByPage;
};

export const usePDFSearchCore = <TItem extends PDFIndexedTextItem>({
  debounceMs = DEFAULT_SEARCH_INPUT_DEBOUNCE_MS,
  indexedTextByPage,
  onActivateMatchPage,
}: UsePDFSearchCoreOptions<TItem>): UsePDFSearchCoreResult => {
  const [searchInputValue, setSearchInputValue] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [matches, setMatches] = useState<PDFSearchMatch[]>([]);
  const [activeMatchIndex, setActiveMatchIndex] = useState(-1);

  const debounceTimerRef = useRef<number | null>(null);
  const onActivateMatchPageRef = useRef(onActivateMatchPage);

  useEffect(() => {
    onActivateMatchPageRef.current = onActivateMatchPage;
  }, [onActivateMatchPage]);

  const resetSearch = useCallback(() => {
    setSearchInputValue('');
    setSearchKeyword('');
    setMatches([]);
    setActiveMatchIndex(-1);
  }, []);

  const clearSearch = useCallback(() => {
    resetSearch();
  }, [resetSearch]);

  useEffect(() => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }

    debounceTimerRef.current = window.setTimeout(() => {
      setSearchKeyword(searchInputValue.trim());
      debounceTimerRef.current = null;
    }, debounceMs);

    return () => {
      if (debounceTimerRef.current !== null) {
        window.clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
  }, [debounceMs, searchInputValue]);

  useEffect(() => {
    if (!searchKeyword) {
      setMatches([]);
      setActiveMatchIndex(-1);
      return;
    }

    const normalizedQuery = searchKeyword.toLowerCase();
    const nextMatches: PDFSearchMatch[] = [];

    indexedTextByPage.forEach((pageItems, pageIndex) => {
      pageItems.forEach((item, itemIndex) => {
        const normalizedText = item.str.toLowerCase();
        if (!normalizedText) return;

        let fromIndex = 0;
        while (fromIndex < normalizedText.length) {
          const matchIndex = normalizedText.indexOf(normalizedQuery, fromIndex);
          if (matchIndex === -1) break;

          nextMatches.push({
            pageNumber: pageIndex + 1,
            itemIndex,
            start: matchIndex,
            end: matchIndex + normalizedQuery.length,
          });

          fromIndex = matchIndex + Math.max(normalizedQuery.length, 1);
        }
      });
    });

    setMatches(nextMatches);
    if (nextMatches.length > 0) {
      setActiveMatchIndex(0);
      onActivateMatchPageRef.current?.(nextMatches[0]!.pageNumber);
    } else {
      setActiveMatchIndex(-1);
    }
  }, [indexedTextByPage, searchKeyword]);

  const matchLookupByPageAndItem = useMemo(() => {
    const pageLookup = new Map<number, Map<number, PDFHighlightRange[]>>();

    matches.forEach((match, index) => {
      const pageLookupByItem = pageLookup.get(match.pageNumber) ?? new Map<number, PDFHighlightRange[]>();
      const itemMatches = pageLookupByItem.get(match.itemIndex) ?? [];
      itemMatches.push({
        start: match.start,
        end: match.end,
        isActive: index === activeMatchIndex,
      });
      pageLookupByItem.set(match.itemIndex, itemMatches);
      pageLookup.set(match.pageNumber, pageLookupByItem);
    });

    pageLookup.forEach((lookupByItem) => {
      lookupByItem.forEach((itemMatches) => {
        itemMatches.sort((a, b) => a.start - b.start);
      });
    });

    return pageLookup;
  }, [activeMatchIndex, matches]);

  const goToMatch = useCallback(
    (nextIndex: number) => {
      const match = matches[nextIndex];
      if (!match) return;
      setActiveMatchIndex(nextIndex);
      onActivateMatchPageRef.current?.(match.pageNumber);
    },
    [matches]
  );

  const goToPreviousMatch = useCallback(() => {
    if (matches.length === 0) return;
    const nextIndex = activeMatchIndex <= 0 ? matches.length - 1 : activeMatchIndex - 1;
    goToMatch(nextIndex);
  }, [activeMatchIndex, goToMatch, matches.length]);

  const goToNextMatch = useCallback(() => {
    if (matches.length === 0) return;
    const nextIndex = activeMatchIndex >= matches.length - 1 ? 0 : activeMatchIndex + 1;
    goToMatch(nextIndex);
  }, [activeMatchIndex, goToMatch, matches.length]);

  const hasMatches = matches.length > 0;
  const matchLabel = hasMatches ? `${activeMatchIndex + 1} / ${matches.length}` : '0 / 0';

  return {
    activeMatchIndex,
    clearSearch,
    goToMatch,
    goToNextMatch,
    goToPreviousMatch,
    hasMatches,
    matchLabel,
    matchLookupByPageAndItem,
    matches,
    resetSearch,
    searchInputValue,
    searchKeyword,
    setSearchInputValue,
  };
};
