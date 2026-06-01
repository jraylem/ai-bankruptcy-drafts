const monthNames = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

export const parseSuggestionDateToInput = (value?: string | null): string => {
  if (!value) {
    return '';
  }

  const trimmed = value.trim();
  if (!trimmed || trimmed.toUpperCase() === 'N/A') {
    return '';
  }

  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) {
    return '';
  }

  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const day = String(parsed.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export const formatSuggestionDateForApi = (value?: string | null): string => {
  if (!value) {
    return '';
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }

  const match = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return trimmed;
  }

  const [, year, month, day] = match;
  const monthIndex = Number.parseInt(month, 10) - 1;
  const dayNumber = Number.parseInt(day, 10);

  if (monthIndex < 0 || monthIndex >= monthNames.length || Number.isNaN(dayNumber)) {
    return trimmed;
  }

  return `${monthNames[monthIndex]} ${dayNumber}, ${year}`;
};
