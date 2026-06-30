import { useEffect, useState } from 'react';
import { useNightQuota } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import { sumCounts } from './transforms/nightQuota';
import type { NightQuotaEntry } from '../types';

const currentMonth = (): string => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

const keyOf = (e: NightQuotaEntry): string => e.tech_id ?? e.name;

/** 夜勤回数 — pick a target month (the column-header month is authoritative), then one
 *  numeric field per active technologist. Validates 合計 == 必要当直者数; the required
 *  figure seeds from the loaded month's sum and is editable. */
export function NightQuotaEditor({ setId }: { setId: number }) {
  const [ym, setYm] = useState<string>(currentMonth());
  const { data } = useNightQuota(setId, ym);
  const mut = useMasterMutation('night_quota');
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [required, setRequired] = useState<number>(0);

  useEffect(() => {
    if (data) {
      const map: Record<string, number> = {};
      data.forEach((e) => {
        map[keyOf(e)] = e.count;
      });
      setCounts(map);
      setRequired(sumCounts(data));
    }
  }, [data]);

  const entries = data ?? [];
  const countOf = (e: NightQuotaEntry): number => counts[keyOf(e)] ?? e.count;
  const runningTotal = entries.reduce((acc, e) => acc + countOf(e), 0);
  const totalOk = runningTotal === required;

  const save = () => {
    if (!totalOk) return;
    const payload: NightQuotaEntry[] = entries.map((e) => ({ ...e, count: countOf(e) }));
    void mut.run(setId, (sid) => api.putNightQuota(sid, ym, payload));
  };

  return (
    <div className="night-quota-editor">
      <h2>夜勤回数</h2>
      <ValidationErrorList serverError={mut.serverError} />
      <AdvisoryWarnings warnings={mut.warnings} onDismiss={mut.reset} />
      <label>
        対象月:{' '}
        <input type="month" data-testid="nq-month" value={ym} onChange={(e) => setYm(e.target.value)} />
      </label>
      <label>
        必要当直者数:{' '}
        <input
          type="number"
          data-testid="nq-required"
          value={required}
          onChange={(e) => setRequired(Number(e.target.value))}
        />
      </label>
      <p data-testid="nq-running">合計: {runningTotal}</p>
      {!totalOk && (
        <p role="alert">
          合計（{runningTotal}）が必要当直者数（{required}）と一致しません。保存できません。
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>氏名</th>
            <th>夜勤回数</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={keyOf(e)}>
              <td>{e.name}</td>
              <td>
                <input
                  type="number"
                  data-testid={`nq-count-${keyOf(e)}`}
                  value={countOf(e)}
                  onChange={(ev) =>
                    setCounts((c) => ({ ...c, [keyOf(e)]: Number(ev.target.value) }))
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" data-testid="nq-save" onClick={save} disabled={!totalOk || mut.isPending}>
        保存
      </button>
    </div>
  );
}
