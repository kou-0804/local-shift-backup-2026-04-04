import type { NightQuotaEntry } from '../../types';

export function sumCounts(entries: Pick<NightQuotaEntry, 'count'>[]): number {
  return entries.reduce((acc, e) => acc + (e.count ?? 0), 0);
}

/** Reconcile a declared total against the running sum and the required-on-call figure. */
export function reconcile(
  entries: Pick<NightQuotaEntry, 'count'>[],
  total: number,
  requiredOnCall: number,
): { totalOk: boolean; requiredMismatch: boolean } {
  return { totalOk: sumCounts(entries) === total, requiredMismatch: total !== requiredOnCall };
}
