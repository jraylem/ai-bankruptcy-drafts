export const CASE_NUMBER_FORMAT_ERROR =
  'Invalid format. Use: X:XX-bk-XXXXX · XX-XXXXX or XX-XXXXX-AAA (e.g., 3:26-bk-00635 · 26-11993 · 25-31154-KKS)';

const CASE_NUMBER_PATTERNS = [
  /^\d:\d{2}-bk-\d{5}$/i,
  /^\d{2}-\d{5}$/,
  /^\d{2}-\d{5}-[A-Za-z]{3}$/,
];

export const normalizeCaseNumberInput = (value: string): string => value.trim();

export const isSupportedCaseNumberFormat = (value: string): boolean => {
  const normalizedValue = normalizeCaseNumberInput(value);
  return CASE_NUMBER_PATTERNS.some((pattern) => pattern.test(normalizedValue));
};
