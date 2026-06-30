import type { RosterState } from '../domain/model';
import type { CellRef } from '../store/uiStore';
import { useUiStore } from '../store/uiStore';
import {
  cellsForCoverage,
  cellsForSkill,
  cellsForConsecutive,
  cellsForHolidayDeficit,
} from '../normalize/warningCells';

// After highlighting a warning's cells, bring the first one into view inside the
// grid's scroll container. querySelector returns null when the grid isn't mounted
// (e.g. unit tests render the panel alone), so this is a safe no-op there.
function scrollToFirst(cells: CellRef[]): void {
  const first = cells[0];
  if (!first) return;
  const el = document.querySelector(`[data-testid="cell-${first.staffId}-${first.day}"]`);
  el?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
}

function Count({ n }: { n: number }) {
  return <span className={`warn-count${n ? ' has' : ''}`}>{n}</span>;
}

export function WarningPanel({ state }: { state: RosterState }) {
  const highlight = useUiStore((s) => s.highlight);
  const { coverage, holiday_deficit, consecutive, skill, night_hb_gaps } = state.warnings;

  // Show the technician's name (人が読む) instead of the bare T0xx id; fall back
  // to the id if the row isn't present.
  const nameOf = (id: string): string => state.rows.find((r) => r.staffId === id)?.name ?? id;
  const focus = (cells: CellRef[]): void => {
    highlight(cells);
    scrollToFirst(cells);
  };

  return (
    <aside className="warning-panel">
      <section>
        <h3>勤務不足の場所 <Count n={coverage.length} /></h3>
        <div className="warn-list">
          {coverage.length === 0 && <span className="warn-empty">なし</span>}
          {coverage.map((w, i) => (
            <button
              key={i}
              className="warn-chip"
              data-testid={`warn-coverage-${i}`}
              onClick={() => focus(cellsForCoverage(w, state))}
            >
              {w.date} {w.location}：{w.assigned}/{w.required}（不足{w.short}）
            </button>
          ))}
        </div>
      </section>

      <section>
        <h3>公休不足の人 <Count n={holiday_deficit.length} /></h3>
        <div className="warn-list">
          {holiday_deficit.length === 0 && <span className="warn-empty">なし</span>}
          {holiday_deficit.map((w, i) => (
            <button
              key={i}
              className="warn-chip"
              data-testid={`warn-holiday-${i}`}
              onClick={() => focus(cellsForHolidayDeficit(w, state))}
            >
              {nameOf(w.staff_id)}：公休 {w.off}/{w.target}（あと{w.short}）
            </button>
          ))}
        </div>
      </section>

      <section>
        <h3>連続勤務 <Count n={consecutive.length} /></h3>
        <div className="warn-list">
          {consecutive.length === 0 && <span className="warn-empty">なし</span>}
          {consecutive.map((w, i) => (
            <button
              key={i}
              className="warn-chip"
              data-testid={`warn-consecutive-${i}`}
              onClick={() => focus(cellsForConsecutive(w))}
            >
              {nameOf(w.staff_id)}：{w.start} から {w.len}連勤
            </button>
          ))}
        </div>
      </section>

      <section>
        <h3>スキル/PB/夜勤違反 <Count n={skill.length} /></h3>
        <div className="warn-list">
          {skill.length === 0 && <span className="warn-empty">なし</span>}
          {skill.map((w, i) => (
            <button
              key={i}
              className="warn-chip"
              data-testid={`warn-skill-${i}`}
              onClick={() => focus(cellsForSkill(w))}
            >
              {w.date} {w.location} {nameOf(w.staff_id)}：{w.rule}（need {w.need}／have {w.have}）
            </button>
          ))}
        </div>
      </section>

      <section>
        <h3>夜勤HB不足 <Count n={night_hb_gaps.length} /></h3>
        <div className="warn-list">
          {night_hb_gaps.length === 0 && <span className="warn-empty">なし</span>}
        </div>
      </section>
    </aside>
  );
}
