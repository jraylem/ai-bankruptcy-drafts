import { describe, expect, it } from 'vitest';

import { deriveCaseInitials, formatCaseName } from '@/utils/studio/caseName';

describe('formatCaseName', () => {
  it('joins newline-separated debtors with " and "', () => {
    expect(formatCaseName('Ruben Soto\nRoxana Ampuero')).toBe(
      'Ruben Soto and Roxana Ampuero',
    );
  });

  it('returns single-debtor names unchanged', () => {
    expect(formatCaseName('John Doe')).toBe('John Doe');
  });

  it('trims whitespace from each segment', () => {
    expect(formatCaseName('  John  \n  Jane  ')).toBe('John and Jane');
  });
});

describe('deriveCaseInitials', () => {
  it.each([
    ['John Doe', 'JD'],
    ['John & Jane Smith', 'JJ'],
    ['Smith, John A.', 'JS'],
    ['Acme Holdings LLC', 'AH'],
    ['Acme', 'AC'],
    ['Doe', 'DO'],
    ['José García-López', 'JG'],
    ["Estate of Mary O'Brien", 'MO'],
    ['Smith, John & Jane', 'JJ'],
    ['In re: Acme Corp.', 'AC'],
    ['JOHN DOE', 'JD'],
    ['John Doe 24-12345', 'JD'],
    ['Mary Smith-Jones', 'MS'],
    ['John, Jane & Jim Smith', 'JJ'],
    ['김민준', '김민'],
  ])('derives "%s" → "%s"', (input, expected) => {
    expect(deriveCaseInitials(input)).toBe(expected);
  });

  it('returns empty string for null / undefined / empty / whitespace input', () => {
    expect(deriveCaseInitials('')).toBe('');
    expect(deriveCaseInitials(null)).toBe('');
    expect(deriveCaseInitials(undefined)).toBe('');
    expect(deriveCaseInitials('   ')).toBe('');
  });

  it('memoizes the result (stable reference across repeated calls)', () => {
    const first = deriveCaseInitials('John & Jane Smith');
    const second = deriveCaseInitials('John & Jane Smith');
    expect(first).toBe(second);
    expect(first).toBe('JJ');
  });

  it('handles newline-separated joint filings as a multi-debtor case', () => {
    expect(deriveCaseInitials('John Doe\nJane Smith')).toBe('JJ');
  });

  it('preserves CJK script and skips ASCII-fold for non-Latin', () => {
    expect(deriveCaseInitials('김민준')).toBe('김민');
  });
});
