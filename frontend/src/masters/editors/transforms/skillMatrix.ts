import type { Rank, SkillRow } from '../../types';

/** The 5 skill locations whose rank ≥B feeds night-shift eligibility
 *  (matches data_loader.py's ≥B derivation). */
export const NIGHT_LOCS = ['病院MR', 'CLMR', 'ア', '心', 'HB'] as const;

/** Per-tech PUT body carrying only the single changed cell. */
export const cellEditPayload = (loc: string, rank: Rank): Record<string, Rank> => ({ [loc]: rank });

export const rankAtLeastB = (r: Rank | string): boolean => r === 'A' || r === 'B';

export type NightChange = 'lost' | 'gained' | 'none';

/** Did this rank edit change night-shift eligibility? Only the 5 NIGHT_LOCS matter. */
export function nightEligibilityChange(loc: string, oldR: Rank, newR: Rank): NightChange {
  if (!(NIGHT_LOCS as readonly string[]).includes(loc)) return 'none';
  const was = rankAtLeastB(oldR);
  const now = rankAtLeastB(newR);
  if (was && !now) return 'lost';
  if (!was && now) return 'gained';
  return 'none';
}

/** Column codes = the union of all rows' cell keys, in first-seen order. */
export function deriveColumns(rows: SkillRow[]): string[] {
  const seen: string[] = [];
  for (const row of rows) {
    for (const code of Object.keys(row.cells)) {
      if (!seen.includes(code)) seen.push(code);
    }
  }
  return seen;
}
