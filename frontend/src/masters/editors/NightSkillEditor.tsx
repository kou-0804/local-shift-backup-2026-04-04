import { useEffect, useState } from 'react';
import { useNightOverrides, useSkillMatrix } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import { triToWire } from './transforms/nightSkill';
import type { NightOverrideRow, Rank, Tri } from '../types';

/** 夜勤可否は「夜勤可 / 夜勤不可」の2状態で明示管理する（日中スキルとは独立）。
 *  画面では未設定(空欄)を スキルマスタのランクから派生した値で表示し、保存(PUT)時に
 *  全員ぶんの TRUE/FALSE が確定値として書き込まれる（＝以後は手動管理・独立）。
 *
 *  派生規則は shift_scheduler/src/loaders/data_loader.py:38-44 と一致:
 *    night_mr    = max(rank('病院MR'), rank('CLMR')) >= B
 *    night_angio = rank('ア') >= B
 *    night_cath  = rank('心') >= B
 *  ※ 保存(PUT)の生値・materialize 経路は不変＝Excel/Power Apps 往復のバイト同一性を保つ。
 *  ※ 行の同一性は配列インデックスで持つ（tech_id 空/重複の行でも状態が衝突しない）。 */
const NIGHT_OPTS: { value: 'TRUE' | 'FALSE'; label: string }[] = [
  { value: 'TRUE', label: '夜勤可' },
  { value: 'FALSE', label: '夜勤不可' },
];
const FIELDS: { key: 'night_mr' | 'night_cath' | 'night_angio'; testid: string; label: string }[] = [
  { key: 'night_mr', testid: 'mr', label: 'MR' },
  { key: 'night_cath', testid: 'cath', label: '心カテ' },
  { key: 'night_angio', testid: 'angio', label: 'アンギオ' },
];

const rankB = (cells: Record<string, Rank> | undefined, loc: string): boolean =>
  cells?.[loc] === 'A' || cells?.[loc] === 'B';

/** 空欄セルの夜勤可否をスキルマスタから派生（B以上＝可）。 */
function deriveNight(cells: Record<string, Rank> | undefined, key: string): 'TRUE' | 'FALSE' {
  if (key === 'night_mr') return rankB(cells, '病院MR') || rankB(cells, 'CLMR') ? 'TRUE' : 'FALSE';
  if (key === 'night_angio') return rankB(cells, 'ア') ? 'TRUE' : 'FALSE';
  return rankB(cells, '心') ? 'TRUE' : 'FALSE'; // night_cath
}

export function NightSkillEditor({ setId }: { setId: number }) {
  const { data } = useNightOverrides(setId);
  const { data: skill } = useSkillMatrix(setId);
  const mut = useMasterMutation('night_overrides');
  const [draft, setDraft] = useState<Record<string, Tri>>({});
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ready && data && skill) {
      const cellsByTech: Record<string, Record<string, Rank>> = {};
      skill.forEach((s) => {
        cellsByTech[s.tech_id] = s.cells;
      });
      const map: Record<string, Tri> = {};
      data.forEach((r, i) => {
        FIELDS.forEach((f) => {
          const raw = r[f.key];
          // 明示値(TRUE/FALSE)はそのまま、空欄はスキルマスタから派生して2状態に解決。
          map[`${i}:${f.key}`] =
            raw === 'TRUE' || raw === 'FALSE' ? raw : deriveNight(cellsByTech[r.tech_id], f.key);
        });
      });
      setDraft(map);
      setReady(true);
    }
  }, [ready, data, skill]);

  const rows = data ?? [];
  const triOf = (i: number, key: string): Tri => draft[`${i}:${key}`] ?? 'FALSE';

  const toWireRow = (r: NightOverrideRow, i: number): NightOverrideRow => ({
    ...r,
    night_mr: triToWire(triOf(i, 'night_mr')),
    night_cath: triToWire(triOf(i, 'night_cath')),
    night_angio: triToWire(triOf(i, 'night_angio')),
  });

  const save = () => {
    const payload = rows.map(toWireRow);
    void mut.run(setId, (sid) => api.putNightOverrides(sid, payload));
  };

  return (
    <div className="night-skill-editor">
      <h2>夜勤スキル一覧</h2>
      <ValidationErrorList serverError={mut.serverError} />
      <AdvisoryWarnings warnings={mut.warnings} onDismiss={mut.reset} />
      <p className="note">
        各夜勤業務（MR / 心カテ / アンギオ）を「夜勤可 / 夜勤不可」で管理します。
        日中勤務ができても夜勤がNGなどのケースも、ここで個別に設定できます。
        保存すると確定します（HB の夜勤適性はここでは扱いません）。
      </p>
      <table>
        <thead>
          <tr>
            <th>氏名</th>
            {FIELDS.map((f) => (
              <th key={f.key}>{f.label}</th>
            ))}
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.sname}</td>
              {FIELDS.map((f) => (
                <td key={f.key} data-night={triOf(i, f.key)}>
                  <select
                    data-testid={`ns-${f.testid}-${r.tech_id}`}
                    value={triOf(i, f.key)}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, [`${i}:${f.key}`]: e.target.value as Tri }))
                    }
                  >
                    {NIGHT_OPTS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </td>
              ))}
              <td>
                <button type="button" data-testid={`ns-save-${r.tech_id}`} onClick={save}>
                  保存
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
