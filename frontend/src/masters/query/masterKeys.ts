import type { MasterKind } from '../types';

/** TanStack Query key for the master-set list. */
export const masterSetsKey = ['master-sets'] as const;

/** Per-master query key, scoped by set id + master kind (+ optional sub-scope,
 *  e.g. the night_quota year_month). */
export const masterKey = (set: number, master: MasterKind | string, scope?: string) =>
  ['master', set, master, scope ?? ''] as const;
