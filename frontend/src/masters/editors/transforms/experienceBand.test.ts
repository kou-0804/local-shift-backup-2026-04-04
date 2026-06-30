import { describe, it, expect } from 'vitest';
import {
  EXPERIENCE_OPTIONS,
  expToOptionValue,
  optionValueToExp,
  B10_15_REP,
  B15_PLUS_REP,
} from './experienceBand';

describe('experienceBand', () => {
  it('offers 0–10 exact plus two buckets', () => {
    const values = EXPERIENCE_OPTIONS.map((o) => o.value);
    expect(values).toEqual([...Array.from({ length: 11 }, (_, n) => String(n)), 'B10_15', 'B15_plus']);
  });

  it('maps an exact value (0–10) to itself', () => {
    expect(expToOptionValue(0)).toBe('0');
    expect(expToOptionValue(7)).toBe('7');
    expect(expToOptionValue(10)).toBe('10');
    expect(optionValueToExp('7')).toBe(7);
  });

  it('maps 11–15 to the 10〜15年 bucket and 16+ to 15年以上', () => {
    expect(expToOptionValue(11)).toBe('B10_15');
    expect(expToOptionValue(15)).toBe('B10_15');
    expect(expToOptionValue(16)).toBe('B15_plus');
    expect(expToOptionValue(30)).toBe('B15_plus');
  });

  it('picking a bucket stores its representative integer (>7 → scheduler-equivalent)', () => {
    expect(optionValueToExp('B10_15')).toBe(B10_15_REP);
    expect(optionValueToExp('B15_plus')).toBe(B15_PLUS_REP);
    expect(B10_15_REP).toBeGreaterThan(7);
    expect(B15_PLUS_REP).toBeGreaterThan(7);
  });

  it('an existing senior value (e.g. 30) displays as 15年以上 — the stored value is only rewritten if the band is changed', () => {
    // expToOptionValue is display-only; the editor keeps the original number in state,
    // so a no-op save preserves 30 (byte-fidelity). Changing band → representative int.
    expect(expToOptionValue(30)).toBe('B15_plus');
  });
});
