import { useState } from 'react';
import { useSkillMatrix } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import { cellEditPayload, deriveColumns, nightEligibilityChange } from './transforms/skillMatrix';
import type { Rank } from '../types';

const RANKS: Rank[] = ['A', 'B', 'C', 'D', '-'];

/** スキルマスタ — constrained {A,B,C,D,-} matrix (rows=技師, cols=skill codes). Each cell
 *  is a dropdown (no free text — non-ABCD silently becomes NONE in Python). Surfaces the
 *  hidden night-eligibility side effect (病院MR/CLMR/ア/心/HB ≥B). */
export function SkillMatrixEditor({ setId }: { setId: number }) {
  const { data } = useSkillMatrix(setId);
  const mut = useMasterMutation('skill');
  const [overrides, setOverrides] = useState<Record<string, Rank>>({});
  const [nightNotice, setNightNotice] = useState<string | null>(null);

  const rows = data ?? [];
  const columns = deriveColumns(rows);
  const key = (techId: string, loc: string) => `${techId}:${loc}`;
  const rankAt = (techId: string, loc: string, original: Rank): Rank =>
    overrides[key(techId, loc)] ?? original;

  const onChange = (techId: string, loc: string, oldRank: Rank, newRank: Rank) => {
    setOverrides((o) => ({ ...o, [key(techId, loc)]: newRank }));
    const change = nightEligibilityChange(loc, oldRank, newRank);
    if (change === 'lost') {
      setNightNotice(`${loc} のランクが B 未満になり、夜勤適性から外れる可能性があります。`);
    } else if (change === 'gained') {
      setNightNotice(`${loc} のランクが B 以上になり、夜勤適性に加わる可能性があります。`);
    }
    void mut.run(setId, (sid) => api.updateSkillCell(sid, techId, cellEditPayload(loc, newRank)), {
      warnings: (r) => r.warnings.map((m) => ({ code: 'skill', message: m })),
    });
  };

  return (
    <div className="skill-editor">
      <h2>スキルマスタ</h2>
      <ValidationErrorList serverError={mut.serverError} />
      {nightNotice && <p role="note">{nightNotice}</p>}
      <AdvisoryWarnings warnings={mut.warnings} onDismiss={mut.reset} />
      {/* Excel風の枠固定: 縦スクロールで見出し行、横スクロールで技師ID/氏名列を常時表示。 */}
      <div className="skill-scroll">
      <table>
        <thead>
          <tr>
            <th>技師ID</th>
            <th>氏名</th>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.tech_id}>
              <td>{r.tech_id}</td>
              <td>{r.name}</td>
              {columns.map((loc) => {
                const original = (r.cells[loc] ?? '-') as Rank;
                const value = rankAt(r.tech_id, loc, original);
                return (
                  <td key={loc} data-rank={value}>
                    <select
                      data-testid={`skill-${r.tech_id}-${loc}`}
                      value={value}
                      onChange={(e) => onChange(r.tech_id, loc, value, e.target.value as Rank)}
                    >
                      {RANKS.map((rank) => (
                        <option key={rank} value={rank}>
                          {rank}
                        </option>
                      ))}
                    </select>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <p className="note">
        スキル列（＝スケジュール対象場所）の追加・削除は管理者専用機能として別途対応します。
      </p>
    </div>
  );
}
