import { useEffect, useState } from 'react';
import { useNightOverrides } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import { triToWire, wireToTri } from './transforms/nightSkill';
import type { NightOverrideRow, Tri } from '../types';

const TRIS: Tri[] = ['TRUE', 'FALSE', 'inherit'];
const FIELDS: { key: 'night_mr' | 'night_cath' | 'night_angio'; testid: string; label: string }[] = [
  { key: 'night_mr', testid: 'mr', label: 'MR' },
  { key: 'night_cath', testid: 'cath', label: '心カテ' },
  { key: 'night_angio', testid: 'angio', label: 'アンギオ' },
];

/** 夜勤スキル一覧 — per-staff tri-state grid (TRUE / FALSE / inherit-from-skill-master)
 *  for MR, 心カテ, アンギオ. 'blank = inherit' is explicit. No HB override here
 *  (HB night-eligibility comes only from スキルマスタ). */
export function NightSkillEditor({ setId }: { setId: number }) {
  const { data } = useNightOverrides(setId);
  const mut = useMasterMutation('night_overrides');
  const [draft, setDraft] = useState<Record<string, Tri>>({});
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ready && data) {
      const map: Record<string, Tri> = {};
      data.forEach((r) => {
        FIELDS.forEach((f) => {
          map[`${r.tech_id}:${f.key}`] = wireToTri(r[f.key]);
        });
      });
      setDraft(map);
      setReady(true);
    }
  }, [ready, data]);

  const rows = data ?? [];
  const triOf = (techId: string, key: string): Tri => draft[`${techId}:${key}`] ?? 'inherit';

  const toWireRow = (r: NightOverrideRow): NightOverrideRow => ({
    ...r,
    night_mr: triToWire(triOf(r.tech_id, 'night_mr')),
    night_cath: triToWire(triOf(r.tech_id, 'night_cath')),
    night_angio: triToWire(triOf(r.tech_id, 'night_angio')),
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
      <p className="note">空欄（inherit）はスキルマスタの値を継承します。HBの夜勤適性に上書きはありません。</p>
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
          {rows.map((r) => (
            <tr key={r.tech_id}>
              <td>{r.sname}</td>
              {FIELDS.map((f) => (
                <td key={f.key}>
                  <select
                    data-testid={`ns-${f.testid}-${r.tech_id}`}
                    value={triOf(r.tech_id, f.key)}
                    onChange={(e) =>
                      setDraft((d) => ({ ...d, [`${r.tech_id}:${f.key}`]: e.target.value as Tri }))
                    }
                  >
                    {TRIS.map((t) => (
                      <option key={t} value={t}>
                        {t === 'inherit' ? '継承' : t}
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
