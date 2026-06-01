import { useCallback, useEffect, useState } from 'react';
import type { AwaitingInputResult } from '@/types/studio';

export interface AwaitingDraftState {
  groupDropdown: Record<string, number>;
  singleValue: Record<string, string>;
  supportingDocs: Record<string, { user_text: string; file_urls: string[] }>;
  /** Picks for multi_select_from_case_vector fields — the picked option
   * strings keyed by field name. Sent back in MultiSelectPick. */
  multiSelect: Record<string, string[]>;
}

export const emptyAwaitingDraftState = (): AwaitingDraftState => ({
  groupDropdown: {},
  singleValue: {},
  supportingDocs: {},
  multiSelect: {},
});

interface PersistedEntry {
  awaiting: AwaitingInputResult;
  picks: AwaitingDraftState;
  savedAt: string;
}

const STORAGE_PREFIX = 'vanhorn:drafting:';
const TTL_MS = 24 * 60 * 60 * 1000;

const storageKey = (templateId: string | null, caseId: string | null): string | null => {
  if (!templateId || !caseId) return null;
  return `${STORAGE_PREFIX}${templateId}:${caseId}`;
};

const readEntry = (key: string): PersistedEntry | null => {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedEntry;
    if (!parsed?.savedAt) return null;
    if (Date.now() - Date.parse(parsed.savedAt) > TTL_MS) {
      localStorage.removeItem(key);
      return null;
    }
    parsed.picks = {
      ...emptyAwaitingDraftState(),
      ...(parsed.picks ?? {}),
    };
    return parsed;
  } catch {
    return null;
  }
};

const writeEntry = (key: string, entry: PersistedEntry): void => {
  try {
    localStorage.setItem(key, JSON.stringify(entry));
  } catch {
    // storage full or disabled — silently skip
  }
};

const clearEntry = (key: string): void => {
  try {
    localStorage.removeItem(key);
  } catch {
    // noop
  }
};

interface UseDraftingPersistenceResult {
  awaiting: AwaitingInputResult | null;
  setAwaiting: (next: AwaitingInputResult | null) => void;
  picks: AwaitingDraftState;
  setPicks: (updater: (prev: AwaitingDraftState) => AwaitingDraftState) => void;
  resetPicks: () => void;
}

/**
 * Persists an in-flight awaiting-input session (server envelope + user's
 * partial picks) to localStorage, keyed by (template_id, case_id). If the
 * user refreshes mid-session, the modal re-opens with their selections
 * intact. Clears on successful resume or explicit cancel.
 */
export const useDraftingPersistence = (
  templateId: string | null,
  caseId: string | null
): UseDraftingPersistenceResult => {
  const [awaiting, setAwaitingState] = useState<AwaitingInputResult | null>(null);
  const [picks, setPicksState] = useState<AwaitingDraftState>(emptyAwaitingDraftState);

  // Restore on mount / when template+case pair changes.
  useEffect(() => {
    const key = storageKey(templateId, caseId);
    if (!key) {
      setAwaitingState(null);
      setPicksState(emptyAwaitingDraftState());
      return;
    }
    const entry = readEntry(key);
    if (entry) {
      setAwaitingState(entry.awaiting);
      setPicksState(entry.picks);
    } else {
      setAwaitingState(null);
      setPicksState(emptyAwaitingDraftState());
    }
  }, [templateId, caseId]);

  const setAwaiting = useCallback(
    (next: AwaitingInputResult | null) => {
      const key = storageKey(templateId, caseId);
      setAwaitingState(next);
      if (!key) return;
      if (next === null) {
        clearEntry(key);
        setPicksState(emptyAwaitingDraftState());
      } else {
        writeEntry(key, {
          awaiting: next,
          picks: emptyAwaitingDraftState(),
          savedAt: new Date().toISOString(),
        });
        setPicksState(emptyAwaitingDraftState());
      }
    },
    [templateId, caseId]
  );

  const setPicks = useCallback(
    (updater: (prev: AwaitingDraftState) => AwaitingDraftState) => {
      setPicksState(updater);
    },
    []
  );

  // Debounce the localStorage write — `awaiting` can be hundreds of KB
  // (every dropdown's options list, etc.), and JSON.stringify + setItem
  // on the keystroke path stalls plain-text inputs. 300 ms after the
  // last edit is fast enough for refresh-recovery, slow enough to keep
  // typing snappy.
  useEffect(() => {
    const key = storageKey(templateId, caseId);
    if (!key || !awaiting) return;
    const timer = setTimeout(() => {
      writeEntry(key, {
        awaiting,
        picks,
        savedAt: new Date().toISOString(),
      });
    }, 300);
    return () => clearTimeout(timer);
  }, [picks, awaiting, templateId, caseId]);

  const resetPicks = useCallback(() => {
    setPicksState(emptyAwaitingDraftState());
    const key = storageKey(templateId, caseId);
    if (key && awaiting) {
      writeEntry(key, {
        awaiting,
        picks: emptyAwaitingDraftState(),
        savedAt: new Date().toISOString(),
      });
    }
  }, [templateId, caseId, awaiting]);

  return { awaiting, setAwaiting, picks, setPicks, resetPicks };
};
