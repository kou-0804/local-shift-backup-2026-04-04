import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
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

export function ScheduleGrid({ state, onCellClick, onDragEnd }: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const days = Array.from({ length: state.daysInMonth }, (_, i) => i + 1);
  const { heatmapMode, highlighted } = useUiStore();

  const rowVirt = useVirtualizer({
    count: state.rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 28,
    overscan: 12,
  });

  return (
    <DndContext onDragEnd={onDragEnd}>
      <div ref={parentRef} className="grid-scroll">
        <table className="schedule-grid">
          <thead>
            <tr>
              <th className="sticky-name" colSpan={2}>
                技師名
              </th>
              {days.map((d) => {
                const wk = weekendKind(state.weekdays[d] ?? '');
                const holiday = state.holidays.has(d);
                const cls = holiday || wk === 'sun' ? 'col-sun' : wk === 'sat' ? 'col-sat' : '';
                return (
                  <th key={d} className={`day-head ${cls}`}>
                    {d}
                  </th>
                );
              })}
              {state.statsColumns.map((c) => (
                <th key={c} className="stat-head">
                  {c}
                </th>
              ))}
            </tr>
            <tr>
              <th className="sticky-name" colSpan={2}>
                曜日
              </th>
              {days.map((d) => (
                <th key={d} className="day-head">
                  {state.weekdays[d] ?? ''}
                </th>
              ))}
              {state.statsColumns.map((c) => (
                <th key={c} className="stat-head" />
              ))}
            </tr>
          </thead>
          <tbody style={{ height: rowVirt.getTotalSize(), position: 'relative' }}>
            {rowVirt.getVirtualItems().map((vi) => {
              const row = state.rows[vi.index];
              return (
                <tr key={row.staffId} style={{ transform: `translateY(${vi.start}px)` }}>
                  <td className="sticky-name name-cell">{row.staffNum}</td>
                  <td className="sticky-name name-cell">{row.name}</td>
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
              );
            })}
            <OnCallRows rows={state.oncallRows} days={days} />
          </tbody>
        </table>
      </div>
    </DndContext>
  );
}
