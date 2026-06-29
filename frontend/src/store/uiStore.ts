import { create } from 'zustand';

export type HeatmapMode = 'off' | 'load' | 'shortfall';
export interface CellRef {
  staffId: string;
  day: number;
}

const cellKey = (c: CellRef) => `${c.staffId}:${c.day}`;
const NEXT: Record<HeatmapMode, HeatmapMode> = { off: 'load', load: 'shortfall', shortfall: 'off' };

interface UiState {
  heatmapMode: HeatmapMode;
  selectedCell: CellRef | null;
  highlighted: Set<string>;
  historyOpen: boolean;
  cycleHeatmap: () => void;
  selectCell: (c: CellRef | null) => void;
  highlight: (cells: CellRef[]) => void;
  clearHighlight: () => void;
  toggleHistory: () => void;
  reset: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  heatmapMode: 'off',
  selectedCell: null,
  highlighted: new Set<string>(),
  historyOpen: false,
  cycleHeatmap: () => set((s) => ({ heatmapMode: NEXT[s.heatmapMode] })),
  selectCell: (c) => set({ selectedCell: c }),
  highlight: (cells) => set({ highlighted: new Set(cells.map(cellKey)) }),
  clearHighlight: () => set({ highlighted: new Set<string>() }),
  toggleHistory: () => set((s) => ({ historyOpen: !s.historyOpen })),
  reset: () => set({ heatmapMode: 'off', selectedCell: null, highlighted: new Set<string>(), historyOpen: false }),
}));

export { cellKey };
