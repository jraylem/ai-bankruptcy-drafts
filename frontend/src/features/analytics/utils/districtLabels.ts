const DISTRICT_FULL_NAMES: Record<string, string> = {
  flnb: 'Northern District of Florida',
  flmb: 'Middle District of Florida',
  flsb: 'Southern District of Florida',
  pawb: 'Western District of Pennsylvania',
};

const DISTRICT_SHORT_NAMES: Record<string, string> = {
  flnb: 'N.D. Florida',
  flmb: 'M.D. Florida',
  flsb: 'S.D. Florida',
  pawb: 'W.D. Pennsylvania',
};

export const DISTRICT_FILTER_KEYS = ['flnb', 'flmb', 'flsb', 'pawb', 'other'] as const;

type DistrictLabelOptions = {
  includeCode?: boolean;
  variant?: 'full' | 'short';
  fallback?: string;
};

const normalizeDistrictKey = (value: string | null | undefined) =>
  typeof value === 'string' ? value.trim().toLowerCase() : '';

export const getDistrictCode = (value: string | null | undefined) => {
  const key = normalizeDistrictKey(value);
  if (!key || key === 'other') return null;
  return DISTRICT_FULL_NAMES[key] ? key.toUpperCase() : (value?.toUpperCase() ?? null);
};

export const getDistrictName = (
  value: string | null | undefined,
  variant: 'full' | 'short' = 'full'
) => {
  const key = normalizeDistrictKey(value);
  if (!key || key === 'other') return null;

  if (variant === 'short') {
    return DISTRICT_SHORT_NAMES[key] ?? null;
  }

  return DISTRICT_FULL_NAMES[key] ?? null;
};

export const formatDistrictLabel = (
  value: string | null | undefined,
  options: DistrictLabelOptions = {}
) => {
  const { includeCode = true, variant = 'full', fallback = '--' } = options;
  const key = normalizeDistrictKey(value);

  if (!key) return fallback;
  if (key === 'other') return '';

  const code = getDistrictCode(value);
  const name = getDistrictName(value, variant);

  if (!code && !name) return fallback;
  if (!includeCode) return name ?? code ?? fallback;
  if (!name) return code ?? fallback;

  return `${code} - ${name}`;
};
