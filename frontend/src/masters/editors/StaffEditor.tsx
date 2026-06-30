import { useState } from 'react';
import { useStaff } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { isTechId } from '../validation/validators';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import type { StaffRow } from '../types';

const EMPTY_NEW: StaffRow = {
  tech_id: '',
  name: '',
  gender: '男',
  experience_years: 0,
  night_ok: '○',
  status: '在籍',
  note: '',
  oncall_ok: '○',
};

const GENDERS = ['男', '女'];
const OX = ['○', '×'];
const STATUSES = ['在籍', '退職'];

/** 技師マスタ — flat one-row-per-person grid. tech_id is unique + Tnnn; 氏名 is the
 *  cross-file join key (rename warning); 退職 does NOT auto-exclude (surfaced). */
export function StaffEditor({ setId }: { setId: number }) {
  const { data } = useStaff(setId);
  const mut = useMasterMutation('staff');
  const [draft, setDraft] = useState<Record<string, StaffRow>>({});
  const [newRow, setNewRow] = useState<StaffRow | null>(null);
  const [newError, setNewError] = useState<string | null>(null);

  const rows = data ?? [];
  const existingIds = new Set(rows.map((r) => r.tech_id));
  const current = (r: StaffRow): StaffRow => draft[r.tech_id] ?? r;
  const renamed = rows.filter((r) => current(r).name !== r.name);
  const hasRetired = rows.some((r) => current(r).status === '退職');

  const editField = (r: StaffRow, field: keyof StaffRow, value: string | number) =>
    setDraft((d) => ({ ...d, [r.tech_id]: { ...current(r), [field]: value } }));

  const saveExisting = (r: StaffRow) => {
    void mut.run(setId, (sid) => api.updateStaff(sid, r.tech_id, current(r)));
  };

  const saveNew = () => {
    if (!newRow) return;
    if (!isTechId(newRow.tech_id)) {
      setNewError('技師IDはTnnn形式で入力してください');
      return;
    }
    if (existingIds.has(newRow.tech_id)) {
      setNewError(`技師ID ${newRow.tech_id} は既に存在します`);
      return;
    }
    setNewError(null);
    void mut.run(setId, (sid) => api.createStaff(sid, newRow)).then(() => setNewRow(null));
  };

  return (
    <div className="staff-editor">
      <h2>技師マスタ</h2>
      {hasRetired && (
        <p role="note">
          「退職」はスケジュールから自動的に除外されません。対象から外すには配置設定の調整が必要です。
        </p>
      )}
      <ValidationErrorList serverError={mut.serverError} clientErrors={newError ? [newError] : []} />
      <AdvisoryWarnings warnings={mut.warnings} onDismiss={mut.reset} />
      <table>
        <thead>
          <tr>
            <th>技師ID</th>
            <th>氏名</th>
            <th>性別</th>
            <th>経験年数</th>
            <th>夜勤可否</th>
            <th>在籍状況</th>
            <th>備考</th>
            <th>拘束可否</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const c = current(r);
            return (
              <tr key={r.tech_id}>
                <td>
                  <input readOnly value={r.tech_id} aria-label={`技師ID ${r.tech_id}`} />
                </td>
                <td>
                  <input
                    data-testid={`staff-name-${r.tech_id}`}
                    value={c.name}
                    onChange={(e) => editField(r, 'name', e.target.value)}
                  />
                </td>
                <td>
                  <select value={c.gender} onChange={(e) => editField(r, 'gender', e.target.value)}>
                    {GENDERS.map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="number"
                    min={0}
                    value={c.experience_years}
                    onChange={(e) => editField(r, 'experience_years', Number(e.target.value))}
                  />
                </td>
                <td>
                  <select value={c.night_ok} onChange={(e) => editField(r, 'night_ok', e.target.value)}>
                    {OX.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select value={c.status} onChange={(e) => editField(r, 'status', e.target.value)}>
                    {STATUSES.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <input value={c.note} onChange={(e) => editField(r, 'note', e.target.value)} />
                </td>
                <td>
                  <select value={c.oncall_ok} onChange={(e) => editField(r, 'oncall_ok', e.target.value)}>
                    {OX.map((o) => (
                      <option key={o}>{o}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <button
                    type="button"
                    data-testid={`staff-save-${r.tech_id}`}
                    onClick={() => saveExisting(r)}
                    disabled={mut.isPending}
                  >
                    保存
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {renamed.length > 0 && (
        <p role="note">
          氏名はファイル間の結合キーです。変更すると他マスタとの結合が壊れる恐れがあります。
        </p>
      )}
      {newRow ? (
        <div className="staff-new-row">
          <input
            data-testid="staff-id-new"
            placeholder="技師ID (Tnnn)"
            value={newRow.tech_id}
            onChange={(e) => setNewRow({ ...newRow, tech_id: e.target.value })}
          />
          <input
            data-testid="staff-name-new"
            placeholder="氏名"
            value={newRow.name}
            onChange={(e) => setNewRow({ ...newRow, name: e.target.value })}
          />
          <button type="button" data-testid="staff-save-new" onClick={saveNew}>
            追加を保存
          </button>
          <button type="button" onClick={() => setNewRow(null)}>
            取消
          </button>
        </div>
      ) : (
        <button type="button" data-testid="staff-add" onClick={() => setNewRow({ ...EMPTY_NEW })}>
          技師を追加
        </button>
      )}
    </div>
  );
}
