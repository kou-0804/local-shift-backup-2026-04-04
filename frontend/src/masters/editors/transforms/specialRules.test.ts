import { describe, it, expect } from 'vitest';
import {
  weekdaysFromToken,
  tokenFromWeekdays,
  classifyRankCond,
  weekFromToken,
  tokenFromWeek,
} from './specialRules';

describe('specialRules transforms', () => {
  it('expands 水金 to [水, 金] and back', () => {
    expect(weekdaysFromToken('水金')).toEqual(['水', '金']);
    expect(tokenFromWeekdays(['水', '金'])).toBe('水金');
  });
  it('maps a single weekday and the all-days token', () => {
    expect(weekdaysFromToken('月')).toEqual(['月']);
    expect(weekdaysFromToken('-')).toEqual([]);
    expect(tokenFromWeekdays([])).toBe('-');
  });
  it('rejects an unsupported multi-day combo', () => {
    expect(() => tokenFromWeekdays(['月', '火'])).toThrow();
  });
  it('round-trips 対象週 1-5 and every', () => {
    expect(weekFromToken('-')).toBe('every');
    expect(weekFromToken('3')).toBe(3);
    expect(tokenFromWeek('every')).toBe('-');
    expect(tokenFromWeek(3)).toBe('3');
  });
  it('classifies rank conditions (numeric floor vs unenforced string)', () => {
    expect(classifyRankCond('A')).toBe('rank_floor');
    expect(classifyRankCond('D同士禁止')).toBe('unenforced');
    expect(classifyRankCond('-')).toBe('none');
  });
});
