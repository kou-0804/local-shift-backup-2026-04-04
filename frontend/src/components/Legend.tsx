// Always-visible colour legend for the schedule grid. The fill colours mirror
// grid_derivation.cell_fill (FFFF00 夜 / FFC0CB ○ / FFCDD2 ★☆◆ / D3D3D3 休) and
// the weekend/holiday column tints in grid.css, so the grid is self-explanatory.

interface LegendItem {
  swatch: string;
  label: string;
  outline?: boolean; // pale tints need a hairline so the swatch is visible on white
}

const ITEMS: LegendItem[] = [
  { swatch: '#FFFF00', label: '夜勤' },
  { swatch: '#FFC0CB', label: '明け（○）' },
  { swatch: '#FFCDD2', label: '希望・特別休（★☆◆）' },
  { swatch: '#D3D3D3', label: '公休（休）' },
  { swatch: '#eef4fb', label: '土曜', outline: true },
  { swatch: '#fcedef', label: '日・祝', outline: true },
];

export function Legend() {
  return (
    <div className="legend" aria-label="凡例">
      <span className="legend-title">凡例</span>
      {ITEMS.map((it) => (
        <span className="legend-item" key={it.label}>
          <span
            className="legend-swatch"
            style={it.outline ? { background: it.swatch, boxShadow: 'inset 0 0 0 1px #c4ccd8' } : { background: it.swatch }}
          />
          {it.label}
        </span>
      ))}
      <span className="legend-item">
        <span className="legend-swatch legend-warn" />
        警告該当（クリックで強調）
      </span>
      <span className="legend-item">🔒 ロック中</span>
    </div>
  );
}
