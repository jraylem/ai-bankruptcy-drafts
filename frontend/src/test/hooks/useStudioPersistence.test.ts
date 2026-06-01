import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearStudioEntry,
  readStudioEntry,
  writeStudioEntry,
  type StudioPersistedEntry,
} from '@/hooks/useStudioPersistence';
import type { TemplateVariable } from '@/types/studio';

const baseVariable: TemplateVariable = {
  template_variable: 'debtor_name',
  template_index: 0,
  source: 'case_vector',
  source_params: null,
  template_property_marker: null,
  template_variable_string: null,
  template_identifying_text_match: null,
  description: null,
  instruction: null,
};

const sampleEntry: Omit<StudioPersistedEntry, 'savedAt'> = {
  templateSpec: [baseVariable],
  dryRunResult: null,
  flowState: 'configuring',
  isDirty: true,
};

beforeEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

describe('storageKey scoping', () => {
  it('returns null when templateId is null (no key, no read/write)', () => {
    writeStudioEntry(null, sampleEntry);
    expect(localStorage.length).toBe(0);
    expect(readStudioEntry(null)).toBeNull();
    clearStudioEntry(null);
  });

  it('writes under vanhorn:studio:<templateId>', () => {
    writeStudioEntry('t1', sampleEntry);
    expect(localStorage.getItem('vanhorn:studio:t1')).not.toBeNull();
    expect(localStorage.getItem('vanhorn:studio:t2')).toBeNull();
  });

  it('readStudioEntry only returns entries written under the same id', () => {
    writeStudioEntry('t1', sampleEntry);
    expect(readStudioEntry('t1')?.templateSpec).toEqual([baseVariable]);
    expect(readStudioEntry('t2')).toBeNull();
  });
});

describe('readStudioEntry — TTL + parse failures', () => {
  it('returns null for missing entries', () => {
    expect(readStudioEntry('absent')).toBeNull();
  });

  it('returns null for malformed JSON', () => {
    localStorage.setItem('vanhorn:studio:bad', '{not valid json');
    expect(readStudioEntry('bad')).toBeNull();
  });

  it('returns null and removes entry once past 24h TTL', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-01T00:00:00Z'));
    writeStudioEntry('t1', sampleEntry);
    expect(readStudioEntry('t1')).not.toBeNull();
    vi.setSystemTime(new Date('2026-05-02T00:00:01Z'));
    expect(readStudioEntry('t1')).toBeNull();
    expect(localStorage.getItem('vanhorn:studio:t1')).toBeNull();
  });

  it('returns null when savedAt is missing from the stored payload', () => {
    localStorage.setItem(
      'vanhorn:studio:t1',
      JSON.stringify({ templateSpec: [], dryRunResult: null, flowState: 'new', isDirty: false }),
    );
    expect(readStudioEntry('t1')).toBeNull();
  });
});

describe('writeStudioEntry — silently swallows storage errors', () => {
  it('does not throw when localStorage.setItem rejects (quota exceeded)', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota exceeded', 'QuotaExceededError');
    });
    expect(() => writeStudioEntry('t1', sampleEntry)).not.toThrow();
    setItem.mockRestore();
  });

  it('stamps savedAt on every write', () => {
    writeStudioEntry('t1', sampleEntry);
    const raw = JSON.parse(localStorage.getItem('vanhorn:studio:t1')!) as StudioPersistedEntry;
    expect(raw.savedAt).toBeTruthy();
    expect(Number.isFinite(Date.parse(raw.savedAt))).toBe(true);
  });
});

describe('clearStudioEntry', () => {
  it('removes the entry for the given templateId', () => {
    writeStudioEntry('t1', sampleEntry);
    clearStudioEntry('t1');
    expect(localStorage.getItem('vanhorn:studio:t1')).toBeNull();
  });

  it('does not throw on a missing entry', () => {
    expect(() => clearStudioEntry('never-existed')).not.toThrow();
  });

  it('does not throw when removeItem rejects', () => {
    const removeItem = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('boom');
    });
    expect(() => clearStudioEntry('t1')).not.toThrow();
    removeItem.mockRestore();
  });
});
