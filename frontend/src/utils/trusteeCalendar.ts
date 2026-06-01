const TRUSTEE_CALENDAR_SLASH_PATTERN =
  /^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:,)?\s+at\s+(\d{1,2}):(\d{2})\s*([AP]\.?M\.?)$/i;

const normalizeDate = (value?: string | null): string => {
  return value && value !== 'N/A' ? value.trim() : '';
};

export const parseTrusteeCalendarToDateTimeLocal = (value?: string | null): string => {
  const normalized = normalizeDate(value);
  if (!normalized) return '';

  const slashMatch = normalized.match(TRUSTEE_CALENDAR_SLASH_PATTERN);
  if (slashMatch) {
    const [, monthRaw, dayRaw, year, hourRaw, minute, meridiemRaw] = slashMatch;
    const month = Number.parseInt(monthRaw, 10);
    const day = Number.parseInt(dayRaw, 10);
    let hour = Number.parseInt(hourRaw, 10);
    const meridiem = meridiemRaw.replace(/\./g, '').toUpperCase();

    if (meridiem === 'PM' && hour < 12) {
      hour += 12;
    } else if (meridiem === 'AM' && hour === 12) {
      hour = 0;
    }

    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T${String(hour).padStart(2, '0')}:${minute}`;
  }

  const attempt = new Date(normalized.replace(/\bat\b/gi, ' '));
  if (Number.isNaN(attempt.getTime())) {
    return '';
  }

  const year = attempt.getFullYear();
  const month = String(attempt.getMonth() + 1).padStart(2, '0');
  const day = String(attempt.getDate()).padStart(2, '0');
  const hours = String(attempt.getHours()).padStart(2, '0');
  const minutes = String(attempt.getMinutes()).padStart(2, '0');

  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

export const formatTrusteeCalendarForApi = (value?: string | null): string => {
  const normalized = normalizeDate(value);
  if (!normalized) return '';

  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) {
    return normalized;
  }

  const dateOptions: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  };
  const timeOptions: Intl.DateTimeFormatOptions = {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  };

  const formattedDate = date.toLocaleDateString('en-US', dateOptions);
  const formattedTime = date.toLocaleTimeString('en-US', timeOptions).toUpperCase();
  return `${formattedDate}, at ${formattedTime}`;
};
