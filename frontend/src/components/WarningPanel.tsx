import type { RosterState } from '../domain/model';
import { useUiStore } from '../store/uiStore';
import {
  cellsForCoverage,
  cellsForSkill,
  cellsForConsecutive,
  cellsForHolidayDeficit,
} from '../normalize/warningCells';

export function WarningPanel({ state }: { state: RosterState }) {
  const highlight = useUiStore((s) => s.highlight);
  const { coverage, holiday_deficit, consecutive, skill, night_hb_gaps } = state.warnings;

  return (
    <aside className="warning-panel">
      <section>
        <h3>勤務不足の場所 ({coverage.length})</h3>
        {coverage.map((w, i) => (
          <button key={i} data-testid={`warn-coverage-${i}`} onClick={() => highlight(cellsForCoverage(w, state))}>
            {w.date} {w.location}: {w.assigned}/{w.required} (不足{w.short})
          </button>
        ))}
      </section>
      <section>
        <h3>公休不足の人 ({holiday_deficit.length})</h3>
        {holiday_deficit.map((w, i) => (
          <button key={i} data-testid={`warn-holiday-${i}`} onClick={() => highlight(cellsForHolidayDeficit(w, state))}>
            {w.staff_id}: 公休{w.off}/{w.target} (あと{w.short})
          </button>
        ))}
      </section>
      <section>
        <h3>連続勤務 ({consecutive.length})</h3>
        {consecutive.map((w, i) => (
          <button key={i} data-testid={`warn-consecutive-${i}`} onClick={() => highlight(cellsForConsecutive(w))}>
            {w.staff_id}: {w.start} から {w.len}連勤
          </button>
        ))}
      </section>
      <section>
        <h3>スキル/PB/夜勤違反 ({skill.length})</h3>
        {skill.map((w, i) => (
          <button key={i} data-testid={`warn-skill-${i}`} onClick={() => highlight(cellsForSkill(w))}>
            {w.date} {w.location} {w.staff_id}: {w.rule} need {w.need} have {w.have}
          </button>
        ))}
      </section>
      <section>
        <h3>夜勤HB不足 ({night_hb_gaps.length})</h3>
      </section>
    </aside>
  );
}
