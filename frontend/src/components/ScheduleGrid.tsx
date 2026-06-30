import { DndContext, type DragEndEvent } from '@dnd-kit/core';
import type { RosterState } from '../domain/model';
import type { CellRef } from '../store/uiStore';
import { useUiStore, cellKey } from '../store/uiStore';
import { weekendKind } from '../normalize/dates';
import { heatColorForCell } from '../viz/heatmap';
import { DayCell } from './DayCell';
import { StatsCells } from './StatsCells';
import { OnCallRows } from './OnCallRows';
import './grid.css';

interface Props {
  state: RosterState;
  onCellClick: (ref: CellRef) => void;
  onDragEnd: (e: DragEndEvent) => void;
}

// Column widths — keep in sync with grid.css .col-* rules. They are summed
// into an explicit table width so `table-layout: fixed` actually engages
// (with width:auto the browser falls back to uneven content-based columns).
const COL_NUM = 34;
const COL_NAME = 104;
const COL_DAY = 58;
const COL_STAT = 42;

// Weekend/holiday class for a given day column.
function dayTint(state: RosterState, d: number): string {
  const wk = weekendKind(state.weekdays[d] ?? '');
  const holiday = state.holidays.has(d);
  return holiday || wk === 'sun' ? 'col-sun' : wk === 'sat' ? 'col-sat' : '';
}

// ~70 rows render fine without virtualization, and a plain fixed-layout
// table keeps every row a uniform height with the header perfectly aligned
// (virtualized transforms jittered when long codes wrapped to two lines).
export function ScheduleGrid({ state, onCellClick, onDragEnd }: Props) {
  const days = Array.from({ length: state.daysInMonth }, (_, i) => i + 1);
  const { heatmapMode, highlighted } = useUiStore();
  const tableWidth = COL_NUM + COL_NAME + days.length * COL_DAY + state.statsColumns.length * COL_STAT;

  return (
    <DndContext onDragEnd={onDragEnd}>
      <div className="grid-scroll">
        <table className="schedule-grid" style={{ width: tableWidth }}>
          <colgroup>
            <col className="col-num" />
            <col className="col-name" />
            {days.map((d) => (
              <col key={d} className={`col-day ${dayTint(state, d)}`} />
            ))}
            {state.statsColumns.map((c) => (
              <col key={c} className="col-stat" />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className="cell-namehead" colSpan={2}>
                技師名
              </th>
              {days.map((d) => (
                <th key={d} className={`day-head ${dayTint(state, d)}`}>
                  {d}
                </th>
              ))}
              {state.statsColumns.map((c) => (
                <th key={c} className="stat-head">
                  {c}
                </th>
              ))}
            </tr>
            <tr>
              <th className="cell-namehead row2" colSpan={2}>
                曜日
              </th>
              {days.map((d) => (
                <th key={d} className={`day-head row2 ${dayTint(state, d)}`}>
                  {state.weekdays[d] ?? ''}
                </th>
              ))}
              {state.statsColumns.map((c) => (
                <th key={c} className="stat-head row2" />
              ))}
            </tr>
          </thead>
          <tbody>
            {state.rows.map((row) => (
              <tr key={row.staffId}>
                <td className="cell-num">{row.staffNum}</td>
                <td className="cell-name">{row.name}</td>
                {days.map((d) => (
                  <DayCell
                    key={d}
                    staffId={row.staffId}
                    cell={row.cells.get(d)}
                    onClick={onCellClick}
                    highlighted={highlighted.has(cellKey({ staffId: row.staffId, day: d }))}
                    heatColor={heatColorForCell(heatmapMode, state, row, d)}
                  />
                ))}
                <StatsCells row={row} statsColumns={state.statsColumns} />
              </tr>
            ))}
            <OnCallRows rows={state.oncallRows} days={days} />
          </tbody>
        </table>
      </div>
    </DndContext>
  );
}
