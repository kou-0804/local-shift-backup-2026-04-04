import { useUiStore } from '../store/uiStore';

const LABEL = {
  off: 'ヒートマップ: OFF',
  load: 'ヒートマップ: 負荷',
  shortfall: 'ヒートマップ: 不足',
} as const;

export function HeatmapToggle() {
  const mode = useUiStore((s) => s.heatmapMode);
  const cycle = useUiStore((s) => s.cycleHeatmap);
  return (
    <button data-testid="heatmap-toggle" onClick={cycle}>
      {LABEL[mode]}
    </button>
  );
}
