export const ANALYTICS_TABLE_PAGE_SIZE_OPTIONS = [
  { label: '10 / page', value: '10' },
  { label: '25 / page', value: '25' },
  { label: '50 / page', value: '50' },
];

export const toAnalyticsTitleCase = (value: string) =>
  value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());

export const sanitizeAnalyticsFilenameToken = (value: string) => {
  const token = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

  return token.length ? token.slice(0, 48) : 'user';
};

export const downloadAnalyticsExportBlob = (blob: Blob, fallbackFilename: string) => {
  const objectUrl = window.URL.createObjectURL(blob);
  const link = window.document.createElement('a');
  link.href = objectUrl;
  link.download = fallbackFilename;
  window.document.body.appendChild(link);
  link.click();
  window.document.body.removeChild(link);
  window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60_000);
};
