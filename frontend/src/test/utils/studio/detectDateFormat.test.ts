import { describe, it, expect } from 'vitest';
import { detectDateFormat } from '@/utils/studio/detectDateFormat';

describe('detectDateFormat', () => {
  it.each([
    ['April 1, 2026', '%B %-d, %Y', '2026-04-01'],
    ['Apr 1, 2026', '%b %-d, %Y', '2026-04-01'],
    ['1 April 2026', '%-d %B %Y', '2026-04-01'],
    ['04/01/2026', '%m/%d/%Y', '2026-04-01'],
    ['4/1/2026', '%-m/%-d/%Y', '2026-04-01'],
    ['2026-04-01', '%Y-%m-%d', '2026-04-01'],
  ])('detects %s as %s', (input, strftime, sampleIso) => {
    const got = detectDateFormat(input);
    expect(got).not.toBeNull();
    expect(got!.strftime).toBe(strftime);
    expect(got!.sampleIso).toBe(sampleIso);
  });

  it('returns null for null/empty input', () => {
    expect(detectDateFormat(null)).toBeNull();
    expect(detectDateFormat(undefined)).toBeNull();
    expect(detectDateFormat('')).toBeNull();
  });

  it('rejects ordinal suffixes (no strftime equivalent)', () => {
    expect(detectDateFormat('April 1st, 2026')).toBeNull();
    expect(detectDateFormat('Apr 2nd, 2026')).toBeNull();
    expect(detectDateFormat('1st April 2026')).toBeNull();
  });

  it('rejects partial dates', () => {
    expect(detectDateFormat('April 2026')).toBeNull();
    expect(detectDateFormat('April 1')).toBeNull();
    expect(detectDateFormat('2026')).toBeNull();
  });

  it('rejects impossible calendar dates', () => {
    expect(detectDateFormat('February 30, 2026')).toBeNull();
    expect(detectDateFormat('13/01/2026')).toBeNull();
    expect(detectDateFormat('1/0/2026')).toBeNull();
    expect(detectDateFormat('1/32/2026')).toBeNull();
    expect(detectDateFormat('0/15/2026')).toBeNull();
  });

  it('finds a date embedded in a longer sentence and returns its span', () => {
    const found = detectDateFormat('Filed on April 1, 2026 in the Eastern District.');
    expect(found).not.toBeNull();
    expect(found!.strftime).toBe('%B %-d, %Y');
    expect(found!.sampleIso).toBe('2026-04-01');
    expect(found!.start).toBe(9);
    expect(found!.end).toBe(22);
  });

  it('prefers the more specific 2-digit slash format over the 1-or-2-digit fallback', () => {
    
    const got = detectDateFormat('04/01/2026');
    expect(got!.strftime).toBe('%m/%d/%Y');
  });

  it('rejects out-of-range years', () => {
    expect(detectDateFormat('April 1, 1899')).toBeNull();
    expect(detectDateFormat('April 1, 2201')).toBeNull();
  });
});
