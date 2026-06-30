import { create } from 'zustand';
import type { CloneResult, MasterKind } from '../types';

// Transient UI state for the masters section — NEVER server data (that lives in
// TanStack Query). `pristine` marks the seeded read-only set; the first edit clones it.
interface MastersState {
  selectedSetId: number | null;
  selectedMaster: MasterKind;
  pristine: boolean;
  dirty: boolean;
  selectSet: (id: number, pristine: boolean) => void;
  selectMaster: (m: MasterKind) => void;
  onCloned: (res: CloneResult) => void;
  markDirty: () => void;
  clearDirty: () => void;
  reset: () => void;
}

const INITIAL = {
  selectedSetId: null as number | null,
  selectedMaster: 'staff' as MasterKind,
  pristine: true,
  dirty: false,
};

export const useMastersStore = create<MastersState>((set) => ({
  ...INITIAL,
  selectSet: (id, pristine) => set({ selectedSetId: id, pristine }),
  selectMaster: (m) => set({ selectedMaster: m }),
  onCloned: (res) => set({ selectedSetId: res.master_set_id, pristine: false }),
  markDirty: () => set({ dirty: true }),
  clearDirty: () => set({ dirty: false }),
  reset: () => set({ ...INITIAL }),
}));
