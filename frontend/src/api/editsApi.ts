import { postJson } from './http';
import type { EditOp } from '../domain/editOps';
import type { WireEditResponse } from '../domain/wire';

export const postEdit = (rid: string, op: EditOp, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/edits`, { ...op, expected_version: expectedVersion });

export const postUndo = (rid: string, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/undo`, { expected_version: expectedVersion });

export const postRedo = (rid: string, expectedVersion: number) =>
  postJson<WireEditResponse>(`/rosters/${rid}/redo`, { expected_version: expectedVersion });

export const postConfirm = (rid: string, expectedVersion: number) =>
  postJson<{ status: string }>(`/rosters/${rid}/confirm`, { expected_version: expectedVersion });

// P2b dark-launch: resolve is mocked until the re-solve backend lands.
export const postResolve = async (
  _rid: string,
  _expectedVersion: number,
): Promise<WireEditResponse> => {
  throw new Error('resolve is not available until P2b');
};
