import { describe, it, expect, beforeEach } from 'vitest';
import { useMastersStore } from './mastersStore';

beforeEach(() => useMastersStore.getState().reset());

describe('mastersStore', () => {
  it('selects set + master', () => {
    useMastersStore.getState().selectSet(1, true);
    useMastersStore.getState().selectMaster('staff');
    const s = useMastersStore.getState();
    expect(s.selectedSetId).toBe(1);
    expect(s.selectedMaster).toBe('staff');
    expect(s.pristine).toBe(true);
  });
  it('clone re-targets the set and clears pristine', () => {
    useMastersStore.getState().selectSet(1, true);
    useMastersStore.getState().onCloned({ master_set_id: 2 });
    expect(useMastersStore.getState().selectedSetId).toBe(2);
    expect(useMastersStore.getState().pristine).toBe(false);
  });
  it('tracks dirty', () => {
    useMastersStore.getState().markDirty();
    expect(useMastersStore.getState().dirty).toBe(true);
    useMastersStore.getState().clearDirty();
    expect(useMastersStore.getState().dirty).toBe(false);
  });
});
