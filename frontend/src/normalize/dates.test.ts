import { describe, it, expect } from 'vitest';
import { toIsoDate, parseDayFromIso, weekendKind } from './dates';

describe('dates', () => {
  it('builds zero-padded ISO dates', () => {
    expect(toIsoDate(2026, 6, 7)).toBe('2026-06-07');
    expect(toIsoDate(2026, 12, 31)).toBe('2026-12-31');
  });
  it('parses the day-of-month from an ISO date', () => {
    expect(parseDayFromIso('2026-06-16')).toBe(16);
    expect(parseDayFromIso('2026-06-01')).toBe(1);
  });
  it('classifies weekend shading from the weekday char', () => {
    expect(weekendKind('土')).toBe('sat');
    expect(weekendKind('日')).toBe('sun');
    expect(weekendKind('水')).toBeNull();
  });
});
