import type { RosterState, Row } from '../domain/model';
import type { HeatmapMode } from '../store/uiStore';

// Temporary compile shim — replaced in full by Task 11.
export function heatColorForCell(
  _m: HeatmapMode,
  _s: RosterState,
  _r: Row,
  _d: number,
): string | null {
  return null;
}
