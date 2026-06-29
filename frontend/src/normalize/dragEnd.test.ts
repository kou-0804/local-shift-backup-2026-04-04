import { describe, it, expect } from 'vitest';
import { moveFromDragEnd } from './dragEnd';
import type { DragEndEvent } from '@dnd-kit/core';

const ev = (active: string, over: string | null): DragEndEvent =>
  ({ active: { id: active }, over: over ? { id: over } : null }) as unknown as DragEndEvent;

const resolve = () => 'CT';

describe('moveFromDragEnd', () => {
  it('returns one move op with nested endpoints for same-staff day→day drag', () => {
    expect(moveFromDragEnd(ev('T013:3', 'T013:5'), 2026, 6, resolve)).toEqual({
      op: 'move',
      staff_id: 'T013',
      from: { date: '2026-06-03', location: 'CT' },
      to: { date: '2026-06-05', location: 'CT' },
    });
  });
  it('returns null when dropped outside a target', () => {
    expect(moveFromDragEnd(ev('T013:3', null), 2026, 6, resolve)).toBeNull();
  });
  it('returns null for cross-staff drag', () => {
    expect(moveFromDragEnd(ev('T013:3', 'T020:3'), 2026, 6, resolve)).toBeNull();
  });
});
