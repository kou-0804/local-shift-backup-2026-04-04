import { RosterPage } from './components/RosterPage';

export function App() {
  // path: /rosters/<rid>  (no router dependency in P2d; read from the URL)
  const rid = window.location.pathname.split('/rosters/')[1]?.replace(/\/.*$/, '') ?? '';
  if (!rid) return <p>勤務表IDがURLにありません: /rosters/&lt;id&gt; を開いてください。</p>;
  return <RosterPage rosterId={rid} />;
}
