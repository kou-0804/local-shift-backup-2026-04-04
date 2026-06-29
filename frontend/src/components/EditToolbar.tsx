import { getExcelUrl } from '../api/rosterApi';
import { HeatmapToggle } from './HeatmapToggle';

interface Props {
  rosterId: string;
  undoAvailable: boolean;
  redoAvailable: boolean;
  resolveEnabled: boolean; // false until P2b lands
  onUndo: () => void;
  onRedo: () => void;
  onResolve: () => void;
  onConfirm: () => void;
}

export function EditToolbar(p: Props) {
  return (
    <div className="edit-toolbar">
      <button data-testid="btn-undo" disabled={!p.undoAvailable} onClick={p.onUndo}>
        元に戻す
      </button>
      <button data-testid="btn-redo" disabled={!p.redoAvailable} onClick={p.onRedo}>
        やり直す
      </button>
      <button
        data-testid="btn-resolve"
        disabled={!p.resolveEnabled}
        onClick={p.onResolve}
        title={p.resolveEnabled ? '' : 'P2b で有効化'}
      >
        再生成(ロック保持)
      </button>
      <a data-testid="btn-excel" href={getExcelUrl(p.rosterId)} download>
        Excel出力
      </a>
      <button data-testid="btn-confirm" onClick={p.onConfirm}>
        確定
      </button>
      <HeatmapToggle />
    </div>
  );
}
