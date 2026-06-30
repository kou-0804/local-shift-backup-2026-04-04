import { describe, it, expect } from 'vitest';
import { sumCounts, reconcile } from './nightQuota';

describe('nightQuota transforms', () => {
  it('sums entry counts', () => {
    expect(sumCounts([{ count: 2 }, { count: 1 }])).toBe(3);
  });
  it('reconciles declared total vs sum and vs required_on_call', () => {
    expect(reconcile([{ count: 2 }, { count: 1 }], 3, 3)).toEqual({ totalOk: true, requiredMismatch: false });
    expect(reconcile([{ count: 2 }], 3, 4)).toEqual({ totalOk: false, requiredMismatch: true });
  });
});
