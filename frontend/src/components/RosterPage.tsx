import { useState } from 'react';
import type { DragEndEvent } from '@dnd-kit/core';
import { useRoster } from '../query/useRoster';
import { useEditMutation } from '../query/useEditMutation';
import { useUiStore, type CellRef } from '../store/uiStore';
import { moveFromDragEnd } from '../normalize/dragEnd';
import { toIsoDate } from '../normalize/dates';
import { ScheduleGrid } from './ScheduleGrid';
import { EditPopover } from './EditPopover';
import { WarningPanel } from './WarningPanel';
import { Legend } from './Legend';
import './roster.css';
import { EditToolbar } from './EditToolbar';
import { ConflictDialog } from './ConflictDialog';
import { postConfirm } from '../api/editsApi';
import type { ConflictError } from '../api/http';
import type { EditOp } from '../domain/editOps';

export function RosterPage({ rosterId }: { rosterId: string }) {
  const { data: state, isLoading, error } = useRoster(rosterId);
  const [conflict, setConflict] = useState<ConflictError | null>(null);
  const { edit, undo, redo } = useEditMutation(rosterId, (err) => setConflict(err));
  const selectCell = useUiStore((s) => s.selectCell);
  const selected = useUiStore((s) => s.selectedCell);

  if (isLoading) return <p>読み込み中…</p>;
  if (error || !state) return <p>勤務表の取得に失敗しました。</p>;

  // resolve a dragged cell's assignment so the move payload carries its location
  const resolveLocation = (staffId: string, day: number): string =>
    state.rows.find((r) => r.staffId === staffId)?.cells.get(day)?.text ?? '';

  const onCellClick = (ref: CellRef) => selectCell(ref);
  const onEmit = (op: EditOp) => {
    void edit(op);
    selectCell(null);
  };
  const onDragEnd = (e: DragEndEvent) => {
    const op = moveFromDragEnd(e, state.year, state.month, resolveLocation);
    if (op) void edit(op);
  };
  const onRebase = () => {
    // Simplest correct rebase: reload so the next edit uses the server's bumped version.
    setConflict(null);
    window.location.reload();
  };

  const selectedRow = selected && state.rows.find((r) => r.staffId === selected.staffId);
  const selectedCellObj = selectedRow && selected ? selectedRow.cells.get(selected.day) : undefined;

  return (
    <div className="roster-page">
      <EditToolbar
        rosterId={rosterId}
        undoAvailable={state.undoAvailable}
        redoAvailable={state.redoAvailable}
        resolveEnabled={false}
        onUndo={() => void undo()}
        onRedo={() => void redo()}
        onResolve={() => {
          /* P2b: enable + call postResolve, then refetch */
        }}
        onConfirm={() => void postConfirm(rosterId, state.version)}
      />
      <Legend />
      <div className="roster-body">
        <ScheduleGrid state={state} onCellClick={onCellClick} onDragEnd={onDragEnd} />
        <WarningPanel state={state} />
      </div>
      {selected && (
        <EditPopover
          staffId={selected.staffId}
          day={selected.day}
          date={toIsoDate(state.year, state.month, selected.day)}
          locked={selectedCellObj?.locked ?? false}
          statsColumns={state.statsColumns}
          currentLocation={selectedCellObj?.text}
          onEmit={onEmit}
          onClose={() => selectCell(null)}
        />
      )}
      {conflict && (
        <ConflictDialog version={conflict.serverVersion} onRebase={onRebase} onCancel={() => setConflict(null)} />
      )}
    </div>
  );
}
