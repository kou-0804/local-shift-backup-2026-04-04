import { postJson } from './http';
import type { EditOp } from '../domain/editOps';
import type { WireEditResponse, WireGrid, WireWarnings } from '../domain/wire';

/** POST /rosters/{id}/resolve — partial-lock re-solve. Holds locked=1 day cells
 *  fixed, regenerates the rest, re-freezes, records an undoable op='resolve'.
 *  Runs the CP-SAT solver synchronously (minutes). Returns the fresh grid; a
 *  non-empty `unlockable` means some locks could not be honored and were dropped. */
export interface WireResolveResponse {
  version: number;
  grid: WireGrid;
  warnings: WireWarnings;
  unlockable?: unknown[];
}

export const postEdit = (rid: string, op: EditOp, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/edits`, { ...op, expected_version: expectedVersion });

export const postUndo = (rid: string, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/undo`, { expected_version: expectedVersion });

export const postRedo = (rid: string, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/redo`, { expected_version: expectedVersion });

export const postConfirm = (rid: string, expectedVersion: number) =>
  postJson<{ status: string }>(`/rosters/${rid}/confirm`, { expected_version: expectedVersion });

// Partial-lock re-solve. No body/expected_version: the backend re-solves the
// current locked set. On 422 (impossible lock set) postJson throws
// ServerValidationError carrying the conflict detail.
export const postResolve = (rid: string) =>
  postJson<WireResolveResponse>(`/rosters/${rid}/resolve`, {});
