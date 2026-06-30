import { useEffect, useState } from 'react';
import { useLocation, usePowerBalance } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { ClientValidationError } from '../validation/validators';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import { deadPbRows, groupPbByCode, validateLocationSet } from './transforms/locationPb';
import type { LocationRow, PowerBalanceRow, Rank } from '../types';

const WEEKDAYS: (keyof LocationRow)[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
const RANKS: Rank[] = ['A', 'B', 'C', 'D', '-'];

/** 勤務場所マスタ — ONE physical file = TWO tables. Two sub-grids share one in-memory
 *  LocationSet and persist as a single atomic PUT /location_set. Section-B 場所コード is
 *  always a section-A code (orphans can't be typed); 有効=× warns about dead PB rows. */
export function LocationPowerBalanceEditor({ setId }: { setId: number }) {
  const locQ = useLocation(setId);
  const pbQ = usePowerBalance(setId);
  const mut = useMasterMutation('location_set');
  const [locs, setLocs] = useState<LocationRow[]>([]);
  const [pb, setPb] = useState<PowerBalanceRow[]>([]);
  const [ready, setReady] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready && locQ.data && pbQ.data) {
      setLocs(locQ.data);
      setPb(pbQ.data);
      setReady(true);
    }
  }, [ready, locQ.data, pbQ.data]);

  const setActive = (code: string, active: string) =>
    setLocs((rows) => rows.map((l) => (l.loc_code === code ? { ...l, active } : l)));

  const editPb = (idx: number, field: keyof PowerBalanceRow, value: string | number | null) =>
    setPb((rows) => rows.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));

  const addPbRow = (code: string) =>
    setPb((rows) => [...rows, { loc_code: code, min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' }]);

  const inactive = locs.filter((l) => l.active === '×');
  const dead = ready ? deadPbRows({ locations: locs, power_balance: pb }) : [];

  const save = () => {
    setClientError(null);
    try {
      validateLocationSet({ locations: locs, power_balance: pb });
    } catch (err) {
      if (err instanceof ClientValidationError) {
        setClientError(err.message);
        return;
      }
      throw err;
    }
    void mut.run(setId, (sid) => api.putLocationSet(sid, { locations: locs, power_balance: pb }));
  };

  const grouped = groupPbByCode(pb);

  return (
    <div className="locpb-editor">
      <h2>勤務場所マスタ</h2>
      <ValidationErrorList serverError={mut.serverError} clientErrors={clientError ? [clientError] : []} />
      <AdvisoryWarnings warnings={mut.warnings} onDismiss={mut.reset} />
      {inactive.length > 0 && (
        <p role="note">
          有効=× の場所はスケジュール対象から外れます（{inactive.map((l) => l.loc_code).join(', ')}）。
          {dead.length > 0 && ` 参照が無効になるパワーバランス行: ${dead.map((r) => r.loc_code).join(', ')}`}
        </p>
      )}

      <h3>勤務場所</h3>
      <table data-testid="loc-grid">
        <thead>
          <tr>
            <th>場所コード</th>
            <th>名称</th>
            <th>区分</th>
            {WEEKDAYS.map((w) => (
              <th key={w}>{w}</th>
            ))}
            <th>性別制約</th>
            <th>表示順</th>
            <th>有効</th>
          </tr>
        </thead>
        <tbody>
          {locs.map((l) => (
            <tr key={l.loc_code}>
              <td>{l.loc_code}</td>
              <td>{l.loc_name}</td>
              <td>{l.category}</td>
              {WEEKDAYS.map((w) => (
                <td key={w}>{String(l[w])}</td>
              ))}
              <td>{l.gender_constraint}</td>
              <td>{l.display_order}</td>
              <td>
                <button
                  type="button"
                  data-testid={`loc-active-${l.loc_code}`}
                  onClick={() => setActive(l.loc_code, l.active === '○' ? '×' : '○')}
                >
                  {l.active}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>パワーバランス</h3>
      <table data-testid="pb-grid">
        <tbody>
          {locs.map((l) => (
            <tr key={l.loc_code} data-pb-group={l.loc_code}>
              <th>{l.loc_code}</th>
              <td>
                {(grouped.get(l.loc_code) ?? []).map((row) => {
                  const idx = pb.indexOf(row);
                  return (
                    <span key={idx} className="pb-row">
                      <select
                        aria-label={`${l.loc_code} 最低ランク`}
                        value={row.min_rank}
                        onChange={(e) => editPb(idx, 'min_rank', e.target.value)}
                      >
                        {RANKS.map((r) => (
                          <option key={r}>{r}</option>
                        ))}
                      </select>
                      <input
                        type="number"
                        aria-label={`${l.loc_code} 最低人数`}
                        value={row.min_count}
                        onChange={(e) => editPb(idx, 'min_count', Number(e.target.value))}
                      />
                    </span>
                  );
                })}
                <button type="button" onClick={() => addPbRow(l.loc_code)}>
                  ランク行を追加
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <button type="button" data-testid="locset-save" onClick={save} disabled={mut.isPending}>
        まとめて保存
      </button>
    </div>
  );
}
