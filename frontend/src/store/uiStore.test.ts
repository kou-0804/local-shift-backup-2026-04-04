import { describe, it, expect, beforeEach } from 'vitest';
import { useUiStore } from './uiStore';

describe('uiStore', () => {
  beforeEach(() => useUiStore.getState().reset());

  it('toggles heatmap mode through off → load → shortfall → off', () => {
    const s = useUiStore.getState();
    expect(s.heatmapMode).toBe('off');
    s.cycleHeatmap();
    expect(useUiStore.getState().heatmapMode).toBe('load');
    s.cycleHeatmap();
    expect(useUiStore.getState().heatmapMode).toBe('shortfall');
    s.cycleHeatmap();
    expect(useUiStore.getState().heatmapMode).toBe('off');
  });

  it('selects a cell and sets highlighted cells from a warning click', () => {
    const s = useUiStore.getState();
    s.selectCell({ staffId: 'T013', day: 16 });
    expect(useUiStore.getState().selectedCell).toEqual({ staffId: 'T013', day: 16 });
    s.highlight([
      { staffId: 'T013', day: 16 },
      { staffId: 'T013', day: 15 },
    ]);
    expect(useUiStore.getState().highlighted.size).toBe(2);
  });
});
