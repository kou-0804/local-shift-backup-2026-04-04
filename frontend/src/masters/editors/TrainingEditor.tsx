import { useEffect, useState } from 'react';
import { useTraining, useStaff } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { assertTrainingResolves, ClientValidationError } from '../validation/validators';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import type { StaffRow, TrainingWire } from '../types';

function selectedValues(select: HTMLSelectElement): string[] {
  return Array.from(select.selectedOptions).map((o) => o.value);
}

/** 業務拡大 — instructors/trainees as ID-backed multi-select pickers (store stable
 *  tech_ids, never fuzzy free text). The 'ランクA保持者' toggle replaces the instructor
 *  picker and emits the sentinel (instructor_ids:[] + rank_a_only:true). */
export function TrainingEditor({ setId }: { setId: number }) {
  const { data } = useTraining(setId);
  const staffQ = useStaff(setId);
  const mut = useMasterMutation('training');
  const [draft, setDraft] = useState<TrainingWire[]>([]);
  const [ready, setReady] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready && data) {
      setDraft(data);
      setReady(true);
    }
  }, [ready, data]);

  const staff: StaffRow[] = staffQ.data ?? [];
  const knownIds = new Set(staff.map((s) => s.tech_id));
  const nameOf = (id: string) => staff.find((s) => s.tech_id === id)?.name ?? id;

  const edit = (idx: number, patch: Partial<TrainingWire>) =>
    setDraft((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const toggleRankA = (idx: number) => {
    const r = draft[idx];
    if (!r.rank_a_only) edit(idx, { rank_a_only: true, instructor_ids: [] });
    else edit(idx, { rank_a_only: false });
  };

  const save = (idx: number) => {
    setClientError(null);
    const r = draft[idx];
    try {
      assertTrainingResolves([...r.instructor_ids, ...r.trainee_ids], knownIds);
    } catch (err) {
      if (err instanceof ClientValidationError) {
        setClientError(err.message);
        return;
      }
      throw err;
    }
    void mut.run(setId, (sid) => api.putTraining(sid, draft));
  };

  return (
    <div className="training-editor">
      <h2>業務拡大</h2>
      <ValidationErrorList serverError={mut.serverError} clientErrors={clientError ? [clientError] : []} />
      <AdvisoryWarnings warnings={mut.warnings} onDismiss={mut.reset} />
      {draft.map((rule, idx) => (
        <fieldset key={rule.modality} className="training-rule">
          <legend>{rule.modality}</legend>
          <label>
            <input
              type="checkbox"
              data-testid={`train-rankA-${rule.modality}`}
              checked={rule.rank_a_only}
              onChange={() => toggleRankA(idx)}
            />
            ランクA保持者（指導者を個別指定しない）
          </label>
          <div className="instructors">
            指導者:
            {rule.rank_a_only ? (
              <span> ランクA保持者</span>
            ) : (
              <>
                <span className="chips">{rule.instructor_ids.map((id) => (
                  <span key={id} className="chip">
                    {nameOf(id)}
                  </span>
                ))}</span>
                <select
                  multiple
                  aria-label={`${rule.modality} 指導者`}
                  value={rule.instructor_ids}
                  onChange={(e) => edit(idx, { instructor_ids: selectedValues(e.target) })}
                >
                  {staff.map((s) => (
                    <option key={s.tech_id} value={s.tech_id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
          <div className="trainees">
            対象者:
            <span className="chips">{rule.trainee_ids.map((id) => (
              <span key={id} className="chip">
                {nameOf(id)}
              </span>
            ))}</span>
            <select
              multiple
              aria-label={`${rule.modality} 対象者`}
              value={rule.trainee_ids}
              onChange={(e) => edit(idx, { trainee_ids: selectedValues(e.target) })}
            >
              {staff.map((s) => (
                <option key={s.tech_id} value={s.tech_id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <label>
            表示名:{' '}
            <input value={rule.display_name} onChange={(e) => edit(idx, { display_name: e.target.value })} />
          </label>
          <button type="button" data-testid={`train-save-${rule.modality}`} onClick={() => save(idx)}>
            保存
          </button>
        </fieldset>
      ))}
    </div>
  );
}
