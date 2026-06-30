import { describe, it, expect } from 'vitest';
import { validateLocationSet, groupPbByCode, deadPbRows } from './locationPb';

const SET = {
  locations: [
    { loc_code: '病院MR', loc_name: 'MRI', category: 'MR', mon: 1, tue: 1, wed: 1, thu: 1, fri: 1, sat: 0, sun: 0, gender_constraint: 'なし', display_order: 1, active: '○' },
    { loc_code: 'PICC', loc_name: 'PICC', category: 'x', mon: 0, tue: 0, wed: 0, thu: 0, fri: 0, sat: 0, sun: 0, gender_constraint: 'なし', display_order: 2, active: '×' },
  ],
  power_balance: [
    { loc_code: '病院MR', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' },
    { loc_code: '病院MR', min_rank: 'B', min_count: 2, cd_cap: null, d_solo_ban: '' },
    { loc_code: 'PICC', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' },
  ],
} as const;

describe('locationPb transforms', () => {
  it('groups additive PB rows by code (病院MR appears twice)', () => {
    expect(groupPbByCode([...SET.power_balance]).get('病院MR')).toHaveLength(2);
  });
  it('rejects a PB row whose code has no section-A location', () => {
    const bad = {
      ...SET,
      power_balance: [...SET.power_balance, { loc_code: '幽霊', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' }],
    };
    expect(() => validateLocationSet(bad as never)).toThrow(/幽霊/);
  });
  it('rejects a duplicate section-A code', () => {
    const dup = { ...SET, locations: [...SET.locations, SET.locations[0]] };
    expect(() => validateLocationSet(dup as never)).toThrow();
  });
  it('flags PB rows pointing at an inactive (有効=×) location as dead', () => {
    expect(deadPbRows(SET as never).map((r) => r.loc_code)).toEqual(['PICC']);
  });
});
