import { useState } from 'react';
import type { EditOp } from '../domain/editOps';
import { locationOptions, REQUEST_SYMBOLS } from '../domain/locations';

interface Props {
  staffId: string;
  day: number;
  date: string; // ISO
  locked: boolean;
  statsColumns: string[];
  currentLocation?: string; // current assignment text, for toggle_lock location
  onEmit: (op: EditOp) => void;
  onClose: () => void;
}

export function EditPopover({ staffId, date, locked, statsColumns, currentLocation, onEmit, onClose }: Props) {
  const [loc, setLoc] = useState('');
  const [sym, setSym] = useState('');
  const fire = (op: EditOp) => {
    onEmit(op);
    onClose();
  };

  return (
    <div className="edit-popover" role="dialog">
      <label>
        場所
        <select data-testid="loc-select" value={loc} onChange={(e) => setLoc(e.target.value)}>
          <option value="">—</option>
          {locationOptions(statsColumns).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      </label>
      <button
        data-testid="apply-assign"
        disabled={!loc}
        onClick={() => fire({ op: 'assign', staff_id: staffId, date, location: loc })}
      >
        配置
      </button>
      <button data-testid="apply-unassign" onClick={() => fire({ op: 'unassign', staff_id: staffId, date })}>
        解除
      </button>

      <label>
        申請
        <select data-testid="sym-select" value={sym} onChange={(e) => setSym(e.target.value)}>
          <option value="">—</option>
          {REQUEST_SYMBOLS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <button
        data-testid="apply-symbol"
        onClick={() => fire({ op: 'set_symbol', staff_id: staffId, date, symbol: sym || null })}
      >
        申請設定
      </button>

      <button
        data-testid="toggle-lock"
        onClick={() =>
          fire({
            op: 'toggle_lock',
            staff_id: staffId,
            date,
            locked: !locked,
            ...(currentLocation ? { location: currentLocation } : {}),
          })
        }
      >
        {locked ? 'ロック解除' : 'ロック'}
      </button>
      <button data-testid="popover-close" onClick={onClose}>
        閉じる
      </button>
    </div>
  );
}
