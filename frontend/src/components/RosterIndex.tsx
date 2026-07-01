import { useRosterList } from '../query/useRosterList';
import type { WireRosterSummary } from '../domain/wire';
import './rosterIndex.css';

const monthLabel = (y: number, m: number) => `${y}年${m}月`;

// created_at is stored in UTC (backend _now() = datetime.now(timezone.utc)). The
// hospital runs on JST, so format in Asia/Tokyo — slicing the raw ISO string would
// show the UTC calendar day, a day behind for rosters created 00:00–09:00 JST.
const JST_DATE = new Intl.DateTimeFormat('ja-JP', {
  timeZone: 'Asia/Tokyo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});
function createdDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso.slice(0, 10) : JST_DATE.format(d);
}

function badge(status: WireRosterSummary['status']) {
  return status === 'confirmed'
    ? { text: '確定', cls: 'roster-status confirmed' }
    : { text: '作成中', cls: 'roster-status draft' };
}

/**
 * Roster picker shown by App when the URL carries no ?rid=. Without this the
 * roster app dead-ends on "勤務表IDがURLにありません"; this lists the available
 * rosters (newest month first, server-ordered) and links each to /?rid=<id>.
 */
export function RosterIndex() {
  const { data, isLoading, error } = useRosterList();

  if (isLoading) return <p className="roster-index-msg">読み込み中…</p>;
  if (error)
    return (
      <p className="roster-index-msg" role="alert">
        勤務表一覧の取得に失敗しました。
      </p>
    );

  const rosters = data ?? [];

  return (
    <div className="roster-index">
      <h1>勤務表一覧</h1>
      {rosters.length === 0 ? (
        <p className="roster-index-msg">
          まだ勤務表がありません。管理者が勤務表を作成すると、ここに表示されます。
        </p>
      ) : (
        <>
          <p className="roster-index-hint">開く勤務表を選択してください。</p>
          <ul className="roster-list">
            {rosters.map((r) => {
              const b = badge(r.status);
              return (
                <li key={r.id}>
                  <a className="roster-link" href={`/?rid=${r.id}`}>
                    <span className="roster-month">{monthLabel(r.year, r.month)}</span>
                    <span className={b.cls}>{b.text}</span>
                    <span className="roster-date">作成: {createdDate(r.created_at)}</span>
                  </a>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
