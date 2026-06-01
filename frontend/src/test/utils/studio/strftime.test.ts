import { describe, it, expect } from 'vitest';
import { strftime } from '@/utils/studio/strftime';

describe('strftime', () => {
  
  const apr1 = new Date(2026, 3, 1);

  it('formats %B %-d, %Y like the BE date pipeline', () => {
    expect(strftime(apr1, '%B %-d, %Y')).toBe('April 1, 2026');
  });

  it('formats %b %-d, %Y with abbreviated month', () => {
    expect(strftime(apr1, '%b %-d, %Y')).toBe('Apr 1, 2026');
  });

  it('zero-pads %m and %d (vs unpadded %-m / %-d)', () => {
    expect(strftime(apr1, '%m/%d/%Y')).toBe('04/01/2026');
    expect(strftime(apr1, '%-m/%-d/%Y')).toBe('4/1/2026');
  });

  it('emits ISO format %Y-%m-%d', () => {
    expect(strftime(apr1, '%Y-%m-%d')).toBe('2026-04-01');
  });

  it('emits 2-digit year via %y', () => {
    expect(strftime(apr1, '%y')).toBe('26');
  });

  it('processes %-m before %m so the dash variant is consumed first', () => {
    
    const nov15 = new Date(2026, 10, 15);
    expect(strftime(nov15, '%-m/%-d/%Y')).toBe('11/15/2026');
    expect(strftime(nov15, '%m/%d/%Y')).toBe('11/15/2026');
  });

  it('processes %Y before %y to avoid clobbering the 4-digit year', () => {
    
    expect(strftime(apr1, '%Y')).toBe('2026');
  });

  it('preserves literal characters around tokens', () => {
    expect(strftime(apr1, 'Filed on %B %-d, %Y.')).toBe('Filed on April 1, 2026.');
  });
});
