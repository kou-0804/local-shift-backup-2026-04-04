import { describe, it, expect } from 'vitest';
import * as v from './validators';

describe('master validators', () => {
  it('tech_id must be Tnnn', () => {
    expect(v.isTechId('T001')).toBe(true);
    expect(v.isTechId('X1')).toBe(false);
    expect(v.isTechId('T01')).toBe(false);
  });
  it('tech_id unique within set', () => {
    expect(() => v.assertTechIdUnique(new Set(['T001']), 'T001')).toThrow(v.ClientValidationError);
    expect(v.assertTechIdUnique(new Set(['T001']), 'T002')).toBeUndefined();
  });
  it('skill rank domain {A,B,C,D,-}', () => {
    ['A', 'B', 'C', 'D', '-'].forEach((r) => expect(v.isRank(r)).toBe(true));
    expect(v.isRank('E')).toBe(false);
  });
  it('gender/○×/status domains', () => {
    expect(v.isGender('男')).toBe(true);
    expect(v.isGender('x')).toBe(false);
    expect(v.isOX('○')).toBe(true);
    expect(v.isOX('o')).toBe(false);
    expect(v.isStatus('在籍')).toBe(true);
    expect(v.isStatus('休職')).toBe(false);
  });
  it('year_month must be zero-padded YYYY/MM (the #1 footgun)', () => {
    expect(v.isYearMonth('2026/04')).toBe(true);
    expect(v.isYearMonth('2026/4')).toBe(false);
    expect(v.isYearMonth('2026/13')).toBe(false);
  });
  it('full-width-space name must join (half-width space will not)', () => {
    const known = new Set(['石川　和弥']); // U+3000
    expect(() => v.assertNameJoins('石川 和弥', known)).toThrow(v.ClientValidationError);
    expect(v.assertNameJoins('石川　和弥', known)).toBeUndefined();
  });
  it('section-B power-balance code must reference a section-A location', () => {
    expect(() => v.assertPbLocationRef('存在しない', new Set(['病院MR', 'CT']))).toThrow();
    expect(v.assertPbLocationRef('病院MR', new Set(['病院MR', 'CT']))).toBeUndefined();
  });
  it('night-quota declared total must equal sum of entries', () => {
    expect(() => v.assertNightTotal([{ count: 2 }, { count: 1 }], 4)).toThrow();
    expect(v.assertNightTotal([{ count: 2 }, { count: 1 }], 3)).toBeUndefined();
  });
  it('training names must resolve to staff ids (sentinel allowed)', () => {
    expect(() => v.assertTrainingResolves(['T999'], new Set(['T001']))).toThrow();
    expect(v.assertTrainingResolves(['ランクA保持者'], new Set(['T001']))).toBeUndefined();
  });
  it('special-rule weekday and week domains', () => {
    expect(v.isWeekdayToken('水金')).toBe(true);
    expect(v.isWeekdayToken('Z')).toBe(false);
    expect(v.isWeekToken('every')).toBe(true);
    expect(v.isWeekToken(6)).toBe(false);
    expect(v.isWeekToken(3)).toBe(true);
  });
  it('flags unenforced special-rule string conditions', () => {
    expect(v.isUnenforcedRankCond('D同士禁止')).toBe(true);
    expect(v.isUnenforcedRankCond('CD上限')).toBe(true);
    expect(v.isUnenforcedRankCond('A')).toBe(false);
  });
});
