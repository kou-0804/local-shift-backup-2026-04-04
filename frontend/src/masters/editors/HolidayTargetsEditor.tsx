import { useState } from 'react';
import { useHolidayTargets } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { isYearMonth } from '../validation/validators';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import type { HolidayTarget } from '../types';

const MIN_COUNT = 7;
const MAX_COUNT = 11;

/** The 12 fiscal-year months (Apr..Mar) for the fiscal year containing `d`. */
export function fiscalMonths(d = new Date()): string[] {
  const y = d.getMonth() + 1 >= 4 ? d.getFullYear() : d.getFullYear() - 1;
  const out: string[] = [];
  for (let i = 0; i < 12; i++) {
    const month = ((3 + i) % 12) + 1; // 4..12, then 1..3
    const year = i < 9 ? y : y + 1;
    out.push(`${year}/${String(month).padStart(2, '0')}`);
  }
  return out;
}

/** 公休数 — 2-col key/value table. Rejects single-digit months (the #1 silent footgun:
 *  Python does an exact `df['年月']==f'{year}/{month:02d}'` match). Pre-seeds the fiscal
 *  year so users only fill numbers. */
export function HolidayTargetsEditor({ setId }: { setId: number }) {
  const { data } = useHolidayTargets(setId);
  const mut = useMasterMutation('holiday_targets');
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [newYm, setNewYm] = useState<string | null>(null);
  const [newCount, setNewCount] = useState('');
  const [newError, setNewError] = useState<string | null>(null);

  const loaded = data ?? [];
  const loadedMap = new Map(loaded.map((t) => [t.year_month, t.holiday_count]));
  const months = Array.from(new Set([...fiscalMonths(), ...loaded.map((t) => t.year_month)])).sort();
  const countOf = (ym: string): number | '' =>
    counts[ym] ?? loadedMap.get(ym) ?? '';

  const outOfBounds = months.filter((ym) => {
    const c = countOf(ym);
    return typeof c === 'number' && (c < MIN_COUNT || c > MAX_COUNT);
  });

  const saveRow = (ym: string) => {
    const c = countOf(ym);
    if (c === '') return;
    void mut.run(setId, (sid) => api.upsertHolidayTarget(sid, { year_month: ym, holiday_count: c }));
  };

  const deleteRow = (ym: string) => {
    void mut.run(setId, (sid) => api.deleteHolidayTarget(sid, ym));
  };

  const saveNew = () => {
    if (newYm == null) return;
    if (!isYearMonth(newYm)) {
      setNewError('年月はゼロ埋めYYYY/MM形式で入力してください（例 2026/04）');
      return;
    }
    if (loadedMap.has(newYm) || months.includes(newYm)) {
      setNewError(`年月 ${newYm} は既に存在します`);
      return;
    }
    const target: HolidayTarget = { year_month: newYm, holiday_count: Number(newCount || 0) };
    setNewError(null);
    void mut.run(setId, (sid) => api.upsertHolidayTarget(sid, target)).then(() => {
      setNewYm(null);
      setNewCount('');
    });
  };

  return (
    <div className="holiday-editor">
      <h2>公休数</h2>
      <ValidationErrorList serverError={mut.serverError} clientErrors={newError ? [newError] : []} />
      {outOfBounds.length > 0 && (
        <p role="note">
          公休数の目安は {MIN_COUNT}〜{MAX_COUNT} です（{outOfBounds.join(', ')} は範囲外）。
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>年月</th>
            <th>公休数</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {months.map((ym) => (
            <tr key={ym}>
              <td>
                <input readOnly value={ym} aria-label={`年月 ${ym}`} />
              </td>
              <td>
                <input
                  type="number"
                  data-testid={`ht-count-${ym}`}
                  value={countOf(ym)}
                  onChange={(e) =>
                    setCounts((c) => ({ ...c, [ym]: Number(e.target.value) }))
                  }
                />
              </td>
              <td>
                <button type="button" data-testid={`ht-save-${ym}`} onClick={() => saveRow(ym)}>
                  保存
                </button>
                <button type="button" data-testid={`ht-del-${ym}`} onClick={() => deleteRow(ym)}>
                  削除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {newYm != null ? (
        <div className="ht-new-row">
          <input
            data-testid="ht-ym-new"
            placeholder="YYYY/MM"
            value={newYm}
            onChange={(e) => setNewYm(e.target.value)}
          />
          <input
            type="number"
            data-testid="ht-count-new"
            placeholder="公休数"
            value={newCount}
            onChange={(e) => setNewCount(e.target.value)}
          />
          <button type="button" data-testid="ht-save-new" onClick={saveNew}>
            追加を保存
          </button>
          <button type="button" onClick={() => setNewYm(null)}>
            取消
          </button>
        </div>
      ) : (
        <button type="button" data-testid="ht-add" onClick={() => setNewYm('')}>
          年月を追加
        </button>
      )}
    </div>
  );
}
