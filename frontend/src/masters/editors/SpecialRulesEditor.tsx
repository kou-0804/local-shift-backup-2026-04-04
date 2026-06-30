import { useEffect, useState } from 'react';
import { useSpecialRules } from '../query/useMasterData';
import { useMasterMutation } from '../query/useMasterMutation';
import * as api from '../api/mastersApi';
import { ClientValidationError } from '../validation/validators';
import { ValidationErrorList } from '../shell/ValidationErrorList';
import { AdvisoryWarnings } from '../shell/AdvisoryWarnings';
import {
  classifyRankCond,
  tokenFromWeek,
  tokenFromWeekdays,
  weekdaysFromToken,
  weekFromToken,
} from './transforms/specialRules';
import type { SpecialRuleWire } from '../types';

const WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日'];
const WEEKS: (number | 'every')[] = ['every', 1, 2, 3, 4, 5];
const RANK_CONDS = ['-', 'A', 'B', 'C', 'D', 'D同士禁止', 'CD上限', 'CD単独禁止'];

/** 特殊配置ルール — structured per-rule form (not raw text). 対象曜日 models 水金 as
 *  Wed+Fri; 対象週 is 1-5 or every; string rank conditions (D同士禁止/CD上限/CD単独禁止)
 *  parse to NONE and are NOT enforced — a prominent warning surfaces that. */
export function SpecialRulesEditor({ setId }: { setId: number }) {
  const { data } = useSpecialRules(setId);
  const mut = useMasterMutation('special_rules');
  const [draft, setDraft] = useState<SpecialRuleWire[]>([]);
  const [ready, setReady] = useState(false);
  const [clientError, setClientError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready && data) {
      setDraft(data);
      setReady(true);
    }
  }, [ready, data]);

  const edit = (idx: number, patch: Partial<SpecialRuleWire>) =>
    setDraft((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const toggleWeekday = (idx: number, day: string) => {
    setClientError(null);
    const cur = weekdaysFromToken(draft[idx].weekday);
    const next = cur.includes(day) ? cur.filter((d) => d !== day) : [...cur, day];
    try {
      edit(idx, { weekday: tokenFromWeekdays(next) });
    } catch (err) {
      if (err instanceof ClientValidationError) setClientError(err.message);
      else throw err;
    }
  };

  const save = (idx: number) => {
    setClientError(null);
    void mut.run(setId, (sid) => api.putSpecialRules(sid, draft.map((r, i) => (i === idx ? draft[idx] : r))));
  };

  return (
    <div className="special-rules-editor">
      <h2>特殊配置ルール</h2>
      <ValidationErrorList serverError={mut.serverError} clientErrors={clientError ? [clientError] : []} />
      <AdvisoryWarnings warnings={mut.warnings} onDismiss={mut.reset} />
      {draft.map((rule, idx) => {
        const weekdays = weekdaysFromToken(rule.weekday);
        const condKind = classifyRankCond(rule.rank_cond);
        return (
          <fieldset key={rule.rule_id} className="special-rule">
            <legend>{rule.rule_id}</legend>
            <label>
              場所コード:{' '}
              <input value={rule.loc_code} onChange={(e) => edit(idx, { loc_code: e.target.value })} />
            </label>
            <div className="weekdays">
              対象曜日:
              {WEEKDAYS.map((day) => (
                <label key={day}>
                  <input
                    type="checkbox"
                    data-testid={`sr-wd-${day}`}
                    checked={weekdays.includes(day)}
                    onChange={() => toggleWeekday(idx, day)}
                  />
                  {day}
                </label>
              ))}
            </div>
            <label>
              対象週:{' '}
              <select
                value={String(weekFromToken(rule.week))}
                onChange={(e) =>
                  edit(idx, {
                    week: tokenFromWeek(e.target.value === 'every' ? 'every' : Number(e.target.value)),
                  })
                }
              >
                {WEEKS.map((w) => (
                  <option key={String(w)} value={String(w)}>
                    {w === 'every' ? '毎週' : `第${w}`}
                  </option>
                ))}
              </select>
            </label>
            <label>
              必要人数:{' '}
              <input
                type="number"
                value={rule.required_count}
                onChange={(e) => edit(idx, { required_count: Number(e.target.value) })}
              />
            </label>
            <label>
              ランク条件:{' '}
              <select value={rule.rank_cond} onChange={(e) => edit(idx, { rank_cond: e.target.value })}>
                {RANK_CONDS.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            {condKind === 'rank_floor' && (
              <label>
                ランク人数:{' '}
                <input
                  type="number"
                  value={rule.rank_count}
                  onChange={(e) => edit(idx, { rank_count: Number(e.target.value) })}
                />
              </label>
            )}
            {condKind === 'unenforced' && (
              <p role="note" className="unenforced">
                この条件はスケジューラで未適用です（{rule.rank_cond} は NONE として無視されます）。
              </p>
            )}
            <button type="button" data-testid={`sr-save-${rule.rule_id}`} onClick={() => save(idx)}>
              保存
            </button>
          </fieldset>
        );
      })}
    </div>
  );
}
