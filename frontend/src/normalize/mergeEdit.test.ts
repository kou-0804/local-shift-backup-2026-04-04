import { describe, it, expect } from 'vitest';
import { normalizeGrid } from './normalizeGrid';
import { mergeEditResponse, applyOptimistic, buildMovePayload } from './mergeEdit';
import { gridFixture, nightEditResponseFixture } from '../test/fixtures';

const base = () => normalizeGrid('R1', gridFixture);

describe('mergeEditResponse', () => {
  it('applies changed_cells (date→day, category→kind, # fill), bumps version, replaces warnings/flags', () => {
    const s = mergeEditResponse(base(), nightEditResponseFixture);
    expect(s.version).toBe(5);
    const t13 = s.rows.find((r) => r.staffId === 'T013')!;
    // D+1 明け cell the client could not predict is now present, authoritative
    expect(t13.cells.get(16)).toEqual({ day: 16, text: '○', kind: 'akemei', fill: '#FFC0CB', locked: false });
    expect(t13.cells.get(15)!.text).toBe('病CT夜');
    expect(t13.stats!['夜勤']).toBe(3); // authoritative recomputed stat
    expect(s.warnings.coverage).toHaveLength(1);
    expect(s.undoAvailable).toBe(true);
    expect(s.redoAvailable).toBe(false);
  });

  it('clears the pending flag on merged cells', () => {
    const s0 = applyOptimistic(base(), { op: 'assign', staff_id: 'T013', date: '2026-06-15', location: '病CT夜' });
    expect(s0.rows.find((r) => r.staffId === 'T013')!.cells.get(15)!.pending).toBe(true);
    const s1 = mergeEditResponse(s0, nightEditResponseFixture);
    expect(s1.rows.find((r) => r.staffId === 'T013')!.cells.get(15)!.pending).toBeUndefined();
  });

  it('flips has_work=false when server returns stats:null for a staff', () => {
    const resp = { ...nightEditResponseFixture, stats: { T013: null } };
    const s = mergeEditResponse(base(), resp);
    expect(s.rows.find((r) => r.staffId === 'T013')!.hasWork).toBe(false);
  });
});

describe('applyOptimistic', () => {
  it('assign sets text+local fill+pending without touching stats', () => {
    const s = applyOptimistic(base(), { op: 'assign', staff_id: 'T013', date: '2026-06-04', location: 'MG' });
    const c = s.rows.find((r) => r.staffId === 'T013')!.cells.get(4)!;
    expect(c).toMatchObject({ text: 'MG', fill: null, pending: true });
    // stats untouched optimistically — server is authoritative
    expect(s.rows.find((r) => r.staffId === 'T013')!.stats!['CT']).toBe(7);
  });
  it('unassign blanks the cell text optimistically', () => {
    const s = applyOptimistic(base(), { op: 'unassign', staff_id: 'T013', date: '2026-06-01' });
    expect(s.rows.find((r) => r.staffId === 'T013')!.cells.get(1)!.text).toBe('');
  });
});

describe('buildMovePayload', () => {
  it('builds one move op with nested {date,location} endpoints for same-staff day→day drag', () => {
    const p = buildMovePayload('T013:3', 'T013:4', 2026, 6, 'CT');
    expect(p).toEqual({
      op: 'move',
      staff_id: 'T013',
      from: { date: '2026-06-03', location: 'CT' },
      to: { date: '2026-06-04', location: 'CT' },
    });
  });
  it('returns null for cross-staff drag (no single move op)', () => {
    expect(buildMovePayload('T013:3', 'T020:3', 2026, 6, 'CT')).toBeNull();
  });
  it('returns null for a drop onto the same cell', () => {
    expect(buildMovePayload('T013:3', 'T013:3', 2026, 6, 'CT')).toBeNull();
  });
  it('returns null when the source has no assignment to move', () => {
    expect(buildMovePayload('T013:3', 'T013:4', 2026, 6, '')).toBeNull();
  });
});
