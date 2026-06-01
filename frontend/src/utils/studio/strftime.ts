
const MONTH_FULL = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const;

const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

export const strftime = (date: Date, format: string): string => {
  const year = date.getFullYear();
  const monthIdx = date.getMonth();
  const day = date.getDate();

  const Y = String(year);
  const y = Y.slice(-2);
  const m = String(monthIdx + 1).padStart(2, '0');
  const dashM = String(monthIdx + 1);
  const d = String(day).padStart(2, '0');
  const dashD = String(day);

  return format
    .replace(/%Y/g, Y)
    .replace(/%y/g, y)
    .replace(/%-m/g, dashM)
    .replace(/%m/g, m)
    .replace(/%-d/g, dashD)
    .replace(/%d/g, d)
    .replace(/%B/g, MONTH_FULL[monthIdx]!)
    .replace(/%b/g, MONTH_ABBR[monthIdx]!);
};
