import { useUiStore } from '../store/uiStore';

// off → 偏り(公平性) → 不足(人員不足) → off。「負荷」は全員ほぼ同日数で差が出ず
// 意味が薄かったため、平均からの偏りを見る「偏り」に置き換えた。
const LABEL = {
  off: 'ヒートマップ: OFF',
  load: 'ヒートマップ: 偏り',
  shortfall: 'ヒートマップ: 不足',
} as const;

export function HeatmapToggle() {
  const mode = useUiStore((s) => s.heatmapMode);
  const cycle = useUiStore((s) => s.cycleHeatmap);
  return (
    <span className="heatmap-control">
      <button data-testid="heatmap-toggle" onClick={cycle}>
        {LABEL[mode]}
      </button>
      {mode === 'load' && (
        <span className="heatmap-legend" aria-hidden>
          <span className="hm-item">
            <span className="hm-sw" style={{ background: '#3b82f6' }} />少ない
          </span>
          <span className="hm-item">
            <span className="hm-sw" style={{ background: '#f1f5f9' }} />平均
          </span>
          <span className="hm-item">
            <span className="hm-sw" style={{ background: '#ef4444' }} />多い
          </span>
        </span>
      )}
      {mode === 'shortfall' && (
        <span className="heatmap-legend" aria-hidden>
          <span className="hm-item">
            <span className="hm-sw" style={{ background: '#ff7043' }} />人員不足
          </span>
        </span>
      )}
    </span>
  );
}
