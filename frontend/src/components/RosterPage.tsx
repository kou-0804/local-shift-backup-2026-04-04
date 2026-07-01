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
import { useQueryClient } from '@tanstack/react-query';
import { EditToolbar } from './EditToolbar';
import { ConflictDialog } from './ConflictDialog';
import { postConfirm, postResolve } from '../api/editsApi';
import { ServerValidationError, type ConflictError } from '../api/http';
import { rosterKey } from '../query/queryClient';
import type { EditOp } from '../domain/editOps';

export function RosterPage({ rosterId }: { rosterId: string }) {
  const { data: state, isLoading, error } = useRoster(rosterId);
  const [conflict, setConflict] = useState<ConflictError | null>(null);
  const { edit, undo, redo } = useEditMutation(rosterId, (err) => setConflict(err));
  const selectCell = useUiStore((s) => s.selectCell);
  const selected = useUiStore((s) => s.selectedCell);
  const qc = useQueryClient();
  const [resolving, setResolving] = useState(false);
  const [resolveMsg, setResolveMsg] = useState<{ kind: 'error' | 'notice'; text: string } | null>(null);

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
  // 配置して固定: assign, then lock, serialised so the lock uses the version the
  // assign bumped to (mutationFn reads version fresh from cache each call → no 409).
  const onAssignAndLock = (staffId: string, date: string, location: string) => {
    selectCell(null);
    void (async () => {
      try {
        await edit({ op: 'assign', staff_id: staffId, date, location });
        await edit({ op: 'toggle_lock', staff_id: staffId, date, locked: true, location });
      } catch {
        /* version conflicts are surfaced via useEditMutation's onConflict → ConflictDialog */
      }
    })();
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

  // 再生成(ロック保持): re-run the solver with locked cells held, then refetch the
  // roster. Runs the CP-SAT solver synchronously so this awaits for minutes.
  const formatResolveError = (e: unknown): string => {
    if (e instanceof ServerValidationError) {
      const d = e.detail as unknown as { errors?: unknown[] };
      const n = Array.isArray(d?.errors) ? d.errors.length : 0;
      return `ロックの組み合わせが成立しないため再生成できません${n ? `（${n}件の競合）` : ''}。ロックを一部外して再度お試しください。`;
    }
    return (e as Error)?.message || '再生成に失敗しました。';
  };
  const onResolve = async () => {
    if (resolving) return;
    setResolveMsg(null);
    setResolving(true);
    try {
      const res = await postResolve(rosterId);
      await qc.invalidateQueries({ queryKey: rosterKey(rosterId) });
      if (Array.isArray(res.unlockable) && res.unlockable.length > 0) {
        setResolveMsg({
          kind: 'notice',
          text: `再生成しました。一部のロックは保持できず解除されました（${res.unlockable.length}件）。`,
        });
      }
    } catch (e) {
      setResolveMsg({ kind: 'error', text: formatResolveError(e) });
    } finally {
      setResolving(false);
    }
  };

  const selectedRow = selected && state.rows.find((r) => r.staffId === selected.staffId);
  const selectedCellObj = selectedRow && selected ? selectedRow.cells.get(selected.day) : undefined;

  return (
    <div className="roster-page">
      <EditToolbar
        rosterId={rosterId}
        undoAvailable={state.undoAvailable}
        redoAvailable={state.redoAvailable}
        resolveEnabled={!resolving}
        onUndo={() => void undo()}
        onRedo={() => void redo()}
        onResolve={() => void onResolve()}
        onConfirm={() => void postConfirm(rosterId, state.version)}
      />
      {resolveMsg && (
        <p
          className={`resolve-banner ${resolveMsg.kind}`}
          role={resolveMsg.kind === 'error' ? 'alert' : 'status'}
        >
          {resolveMsg.text}
        </p>
      )}
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
          onAssignAndLock={onAssignAndLock}
          onClose={() => selectCell(null)}
        />
      )}
      {conflict && (
        <ConflictDialog version={conflict.serverVersion} onRebase={onRebase} onCancel={() => setConflict(null)} />
      )}
      {resolving && (
        <div className="resolve-overlay" role="status" aria-live="polite">
          <div className="resolve-overlay-box">
            <span className="resolve-spinner" aria-hidden /> 再生成中です。数分かかります。この画面のままお待ちください。
          </div>
        </div>
      )}
    </div>
  );
}
