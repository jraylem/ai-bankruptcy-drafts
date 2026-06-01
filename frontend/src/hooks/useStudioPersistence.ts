import type { DryRunResult, StudioFlowState, TemplateVariable } from '@/types/studio';

export interface StudioPersistedEntry {
  templateSpec: TemplateVariable[];
  dryRunResult: DryRunResult | null;
  flowState: StudioFlowState;
  isDirty: boolean;
  savedAt: string;
}

const STORAGE_PREFIX = 'vanhorn:studio:';
const TTL_MS = 24 * 60 * 60 * 1000;

const storageKey = (templateId: string | null): string | null =>
  templateId ? `${STORAGE_PREFIX}${templateId}` : null;

export const readStudioEntry = (templateId: string | null): StudioPersistedEntry | null => {
  const key = storageKey(templateId);
  if (!key) return null;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StudioPersistedEntry;
    if (!parsed?.savedAt) return null;
    if (Date.now() - Date.parse(parsed.savedAt) > TTL_MS) {
      localStorage.removeItem(key);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

export const writeStudioEntry = (
  templateId: string | null,
  entry: Omit<StudioPersistedEntry, 'savedAt'>,
): void => {
  const key = storageKey(templateId);
  if (!key) return;
  try {
    localStorage.setItem(
      key,
      JSON.stringify({ ...entry, savedAt: new Date().toISOString() }),
    );
  } catch {
    void 0;
  }
};

export const clearStudioEntry = (templateId: string | null): void => {
  const key = storageKey(templateId);
  if (!key) return;
  try {
    localStorage.removeItem(key);
  } catch {
    void 0;
  }
};
