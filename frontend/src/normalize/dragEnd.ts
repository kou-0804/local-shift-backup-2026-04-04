import type { DragEndEvent } from '@dnd-kit/core';
import { buildMovePayload } from './mergeEdit';
import type { EditOp } from '../domain/editOps';

/** dnd-kit drop → one `move` op. The moved assignment's location is resolved from
 *  the source cell so the nested {date,location} payload is complete. Dropped
 *  outside a target, cross-staff, or empty source → null. */
export function moveFromDragEnd(
  e: DragEndEvent,
  year: number,
  month: number,
  resolveLocation: (staffId: string, day: number) => string,
): Extract<EditOp, { op: 'move' }> | null {
  if (!e.over) return null;
  const sourceId = String(e.active.id);
  const [sSid, sDay] = sourceId.split(':');
  const location = resolveLocation(sSid, Number(sDay));
  return buildMovePayload(sourceId, String(e.over.id), year, month, location);
}
