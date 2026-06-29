const pad = (n: number) => String(n).padStart(2, '0');

export const toIsoDate = (year: number, month: number, day: number) =>
  `${year}-${pad(month)}-${pad(day)}`;

export const parseDayFromIso = (iso: string) => Number(iso.slice(8, 10));

export type WeekendKind = 'sat' | 'sun' | null;
export const weekendKind = (weekdayChar: string): WeekendKind =>
  weekdayChar === '土' ? 'sat' : weekdayChar === '日' ? 'sun' : null;
