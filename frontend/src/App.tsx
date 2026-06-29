import { RosterPage } from './components/RosterPage';

export function App() {
  // Select the roster via the `?rid=<id>` query param. We intentionally do NOT use
  // a `/rosters/<id>` path: in dev the Vite proxy forwards `/rosters` to the API,
  // and in prod FastAPI serves `/rosters` as JSON — either way that path would not
  // load the SPA. The query param keeps the SPA on `/` clear of the API namespace.
  const params = new URLSearchParams(window.location.search);
  const rid =
    params.get('rid') ??
    // back-compat: also accept /rosters/<id> if something links to it
    (window.location.pathname.split('/rosters/')[1]?.replace(/\/.*$/, '') || '');
  if (!rid) return <p>勤務表IDがURLにありません: <code>/?rid=&lt;id&gt;</code> を開いてください。</p>;
  return <RosterPage rosterId={rid} />;
}
