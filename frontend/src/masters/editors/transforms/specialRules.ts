import { ClientValidationError, isUnenforcedRankCond } from '../../validation/validators';

const WEEKDAY_SINGLES = ['月', '火', '水', '木', '金', '土', '日'];

/** Wire weekday token → UI weekday list. '-' = all days = []; '水金' = the Wed+Fri pair. */
export function weekdaysFromToken(token: string): string[] {
  if (token === '-' || token === '') return [];
  if (token === '水金') return ['水', '金'];
  if (WEEKDAY_SINGLES.includes(token)) return [token];
  return [];
}

/** UI weekday list → wire token. The loader only special-cases 水金, so the UI restricts
 *  multi-select to a single day, the all-days option ([]), or the 水金 pair. */
export function tokenFromWeekdays(days: string[]): string {
  if (days.length === 0) return '-';
  if (days.length === 1) return days[0];
  const set = new Set(days);
  if (set.size === 2 && set.has('水') && set.has('金')) return '水金';
  throw new ClientValidationError(
    '対象曜日',
    '対応していない曜日の組み合わせです（単一曜日・水金・全日のみ）',
  );
}

export type Week = number | 'every';

export function weekFromToken(token: string): Week {
  return token === '-' || token === '' ? 'every' : Number(token);
}

export function tokenFromWeek(w: Week): string {
  return w === 'every' ? '-' : String(w);
}

export type RankCondKind = 'rank_floor' | 'unenforced' | 'none';

/** numeric rank-floor (A/B/C/D) vs the unenforced string conditions vs none. */
export function classifyRankCond(cond: string): RankCondKind {
  if (cond === '-' || cond === '') return 'none';
  if (isUnenforcedRankCond(cond)) return 'unenforced';
  return 'rank_floor';
}
