export const formatCurrencyInput = (rawValue: string): string => {
  const sanitized = rawValue.replace(/[^\d.]/g, '');
  const [integerPart, decimalPart] = sanitized.split('.');
  const formattedInteger = integerPart ? Number(integerPart).toLocaleString('en-US') : '';

  if (!formattedInteger && !decimalPart) {
    return '';
  }

  if (decimalPart !== undefined) {
    return `${formattedInteger || '0'}.${decimalPart.slice(0, 2)}`;
  }

  return formattedInteger;
};

export const formatNumberInput = (rawValue: string): string => {
  const sanitized = rawValue.replace(/[^\d]/g, '');

  if (!sanitized) {
    return '';
  }

  return Number(sanitized).toLocaleString('en-US');
};
