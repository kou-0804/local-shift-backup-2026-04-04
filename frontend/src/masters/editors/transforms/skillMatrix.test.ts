import { describe, it, expect } from 'vitest';
import { cellEditPayload, nightEligibilityChange, NIGHT_LOCS, deriveColumns } from './skillMatrix';

describe('skillMatrix transforms', () => {
  it('builds a per-tech PUT body containing only the changed cell', () => {
    expect(cellEditPayload('病院MR', 'C')).toEqual({ 病院MR: 'C' });
  });
  it('detects a night-eligibility loss when an MR rank drops below B', () => {
    expect(nightEligibilityChange('病院MR', 'A', 'C')).toBe('lost');
    expect(nightEligibilityChange('病院MR', 'C', 'B')).toBe('gained');
    expect(nightEligibilityChange('病院MR', 'A', 'B')).toBe('none');
  });
  it('only the 5 night-relevant locations trigger the side effect', () => {
    expect(NIGHT_LOCS).toEqual(['病院MR', 'CLMR', 'ア', '心', 'HB']);
    expect(nightEligibilityChange('CT', 'A', '-')).toBe('none');
  });
  it('derives columns as the union of cell keys in first-seen order', () => {
    expect(
      deriveColumns([
        { tech_id: 'T001', name: 'a', cells: { 病院MR: 'A', CT: 'B' } },
        { tech_id: 'T002', name: 'b', cells: { CT: 'C', ア: 'A' } },
      ]),
    ).toEqual(['病院MR', 'CT', 'ア']);
  });
});
