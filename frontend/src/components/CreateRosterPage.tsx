import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createJob, getJob, freezeJob, getRequestsStatus } from '../api/jobsApi';
import { listMasterSets, safetyCheck } from '../masters/api/mastersApi';
import { useAuth } from '../auth/useAuth';
import { can } from '../auth/roles';
import './create.css';

type Phase = 'idle' | 'starting' | 'running' | 'freezing' | 'done' | 'error';

const POLL_MS = 2000;
const MAX_POLL_FAILS = 4; // tolerate ~8s of transient status-poll errors before giving up

function nextMonth(): { year: number; month: number } {
  const d = new Date();
  let year = d.getFullYear();
  let month = d.getMonth() + 2; // getMonth() is 0-indexed; +2 = next month, 1-indexed
  if (month > 12) {
    month = 1;
    year += 1;
  }
  return { year, month };
}

const msg = (e: unknown) => (e as Error)?.message || '不明なエラー';

/**
 * 勤務表 自動作成. One screen for the create workflow that previously only existed
 * as raw API calls: pick a month → see whether that month's 予定申請 CSV is imported
 * and whether the masters pass the safety gate → press 自動作成 → the solver runs
 * (POST /jobs), we poll to completion, freeze it (POST /jobs/{id}/freeze), and open
 * the resulting roster (/?rid=<id>).
 */
export function CreateRosterPage({
  onComplete,
}: {
  onComplete?: (rosterId: number) => void;
}) {
  const { role } = useAuth();

  const init = nextMonth();
  const [year, setYear] = useState(init.year);
  const [month, setMonth] = useState(init.month);
  const [phase, setPhase] = useState<Phase>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [reachedDone, setReachedDone] = useState(false); // solve finished; only freeze remains

  const mounted = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pollFails = useRef(0);
  useEffect(() => {
    return () => {
      mounted.current = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const openRoster = onComplete ?? ((rid: number) => window.location.assign(`/?rid=${rid}`));

  const setsQ = useQuery({ queryKey: ['create', 'master-sets'], queryFn: listMasterSets });
  // Mirror the backend's resolve_default_master_set_id: prefer the set named 現行,
  // else the lowest id — so the safety gate validates the set generation actually uses.
  const defaultSetId = useMemo(() => {
    const sets = setsQ.data;
    if (!sets || sets.length === 0) return undefined;
    const genkou = sets.find((s) => s.name === '現行');
    if (genkou) return genkou.master_set_id;
    return [...sets].sort((a, b) => a.master_set_id - b.master_set_id)[0].master_set_id;
  }, [setsQ.data]);

  const safetyQ = useQuery({
    queryKey: ['create', 'safety', defaultSetId],
    queryFn: () => safetyCheck(defaultSetId as number),
    enabled: defaultSetId !== undefined,
  });

  const reqQ = useQuery({
    queryKey: ['create', 'requests-status', year, month],
    queryFn: () => getRequestsStatus(year, month),
  });

  // --- derived status (kept separate from render so button-disable and the badge agree) ---
  const reqState: 'loading' | 'error' | 'imported' | 'none' = reqQ.isError
    ? 'error'
    : reqQ.isLoading
      ? 'loading'
      : reqQ.data?.imported
        ? 'imported'
        : 'none';

  const safetyState: 'na' | 'loading' | 'ok' | 'ng' | 'error' =
    defaultSetId === undefined
      ? 'na'
      : safetyQ.isError
        ? 'error'
        : safetyQ.isLoading
          ? 'loading'
          : safetyQ.data?.ok
            ? 'ok'
            : 'ng';

  const busy = phase === 'starting' || phase === 'running' || phase === 'freezing';
  // Block while the safety gate is still resolving (closes the click-before-check race)
  // and on a confirmed NG. A safety-check *error* does not hard-block (backend re-checks
  // authoritatively and fails the job), but we warn.
  const canGenerate = !busy && safetyState !== 'loading' && safetyState !== 'ng';

  function schedule(id: string) {
    timer.current = setTimeout(() => void poll(id), POLL_MS);
  }

  async function doFreeze(id: string) {
    setPhase('freezing');
    try {
      const { roster_id } = await freezeJob(id);
      if (!mounted.current) return;
      setPhase('done');
      openRoster(roster_id);
    } catch (e) {
      if (!mounted.current) return;
      setErrorMsg(msg(e));
      setPhase('error');
    }
  }

  async function poll(id: string) {
    try {
      const job = await getJob(id);
      if (!mounted.current) return;
      pollFails.current = 0;
      if (job.status === 'done') {
        setReachedDone(true);
        void doFreeze(id);
        return;
      }
      if (job.status === 'failed') {
        setErrorMsg(job.error || '生成に失敗しました。');
        setPhase('error');
        return;
      }
      schedule(id); // queued / running
    } catch (e) {
      if (!mounted.current) return;
      pollFails.current += 1;
      if (pollFails.current >= MAX_POLL_FAILS) {
        setErrorMsg(`進捗の取得に繰り返し失敗しました：${msg(e)}`);
        setPhase('error');
        return;
      }
      schedule(id); // transient blip — keep polling; the solve is still running
    }
  }

  async function onGenerate() {
    setErrorMsg(null);
    setReachedDone(false);
    pollFails.current = 0;
    setPhase('starting');
    try {
      const job = await createJob(year, month);
      if (!mounted.current) return;
      setJobId(job.id);
      setPhase('running');
      void poll(job.id); // first poll immediately; poll() re-queues itself with a delay
    } catch (e) {
      if (!mounted.current) return;
      setErrorMsg(msg(e));
      setPhase('error');
    }
  }

  function retryFreeze() {
    if (jobId) void doFreeze(jobId);
  }

  if (!role || !can(role, 'generate')) {
    return (
      <div className="create-page">
        <h1 className="create-title">勤務表 自動作成</h1>
        <p className="create-lead">この機能を使用する権限がありません。管理者にお問い合わせください。</p>
      </div>
    );
  }

  const nowY = new Date().getFullYear();
  const years = [nowY - 1, nowY, nowY + 1];

  return (
    <div className="create-page">
      <h1 className="create-title">勤務表 自動作成</h1>
      <p className="create-lead">
        月を選び、下の「自動作成を開始」を押すと、マスタと予定申請をもとに勤務表を自動生成します。
        完成すると自動でその勤務表が開きます（生成には数分かかります）。
      </p>

      <section className="create-card">
        <label className="create-field">
          <span className="create-label">対象月</span>
          <span className="create-month">
            <select
              aria-label="年"
              value={year}
              disabled={busy}
              onChange={(e) => setYear(Number(e.target.value))}
            >
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}年
                </option>
              ))}
            </select>
            <select
              aria-label="月"
              value={month}
              disabled={busy}
              onChange={(e) => setMonth(Number(e.target.value))}
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>
                  {m}月
                </option>
              ))}
            </select>
          </span>
        </label>
      </section>

      <section className="create-card">
        <h2 className="create-h2">この月の状態</h2>
        <div className="create-status-group" aria-live="polite">
          <div className="create-status" data-testid="requests-status">
            <span className="create-status-key">予定申請CSV</span>
            {reqState === 'loading' ? (
              <span className="create-badge neutral">確認中…</span>
            ) : reqState === 'error' ? (
              <span className="create-badge neutral">
                状態を取得できませんでした{' '}
                <button type="button" className="create-linkbtn" onClick={() => void reqQ.refetch()}>
                  再確認
                </button>
              </span>
            ) : reqState === 'imported' ? (
              <span className="create-badge ok">
                ✓ 取り込み済み（{reqQ.data?.row_count}件
                {reqQ.data?.imported_at ? ` ・ ${reqQ.data.imported_at.slice(0, 10)}` : ''}）
              </span>
            ) : (
              <span className="create-badge warn">
                未取り込み <a href="/?view=masters&m=requests">（予定申請タブで取り込む）</a>
              </span>
            )}
          </div>
          <div className="create-status">
            <span className="create-status-key">マスタ安全チェック</span>
            {safetyState === 'na' ? (
              <span className="create-badge neutral">既定データで作成</span>
            ) : safetyState === 'loading' ? (
              <span className="create-badge neutral">確認中…</span>
            ) : safetyState === 'error' ? (
              <span className="create-badge neutral">
                確認できませんでした{' '}
                <button type="button" className="create-linkbtn" onClick={() => void safetyQ.refetch()}>
                  再確認
                </button>
              </span>
            ) : safetyState === 'ok' ? (
              <span className="create-badge ok">✓ OK</span>
            ) : (
              <span className="create-badge danger">
                ⚠ 要確認: {safetyQ.data?.missing?.join(', ') || '不明'}
              </span>
            )}
          </div>
          {reqState === 'none' && (
            <p className="create-hint">
              予定申請が未取り込みでも作成はできますが、希望休などが反映されません。
            </p>
          )}
          {safetyState === 'error' && (
            <p className="create-hint">
              安全チェックを確認できませんでした。作成は可能ですが、マスタに問題があると生成に失敗します。
            </p>
          )}
        </div>
      </section>

      <button
        type="button"
        className="create-btn"
        onClick={() => void onGenerate()}
        disabled={!canGenerate}
      >
        {busy ? '作成中…' : '自動作成を開始'}
      </button>
      {safetyState === 'ng' && (
        <p className="create-hint danger">
          マスタに問題があるため作成できません。マスタ管理で修正してください。
        </p>
      )}

      {busy && (
        <section className="create-progress" role="status" aria-live="polite">
          {phase === 'starting' && <p>生成を開始しています…</p>}
          {phase === 'running' && (
            <p>
              <span className="create-spinner" aria-hidden /> 自動生成中です。数分かかります。この画面のままお待ちください。
            </p>
          )}
          {phase === 'freezing' && <p>確定処理中です…</p>}
        </section>
      )}

      {phase === 'error' && (
        <div className="create-progress">
          <p className="create-error" role="alert">
            {reachedDone ? '確定処理に失敗しました' : '作成に失敗しました'}：{errorMsg}
          </p>
          {reachedDone && jobId ? (
            <>
              <p className="create-hint">生成自体は成功しています。再生成せずに確定だけやり直せます。</p>
              <button type="button" className="create-btn" onClick={() => retryFreeze()}>
                確定をやり直す
              </button>
            </>
          ) : (
            <p className="create-hint">「自動作成を開始」からやり直してください。</p>
          )}
        </div>
      )}
    </div>
  );
}
