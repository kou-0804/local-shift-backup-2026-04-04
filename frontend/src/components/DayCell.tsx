import React from 'react';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import type { Cell } from '../domain/model';
import type { CellRef } from '../store/uiStore';

interface Props {
  staffId: string;
  cell: Cell | undefined;
  onClick: (ref: CellRef) => void;
  highlighted?: boolean;
  heatColor?: string | null;
}

export function DayCell({ staffId, cell, onClick, highlighted, heatColor }: Props) {
  const day = cell?.day ?? 0;
  const id = `${staffId}:${day}`;
  const { attributes, listeners, setNodeRef: dragRef } = useDraggable({ id });
  const { setNodeRef: dropRef, isOver } = useDroppable({ id });

  const bg = heatColor ?? cell?.fill ?? undefined;
  const style: React.CSSProperties = {
    backgroundColor: bg,
    outline: highlighted ? '2px solid #d32f2f' : isOver ? '2px dashed #1976d2' : undefined,
    opacity: cell?.pending ? 0.5 : 1,
  };

  return (
    <td
      ref={(n) => {
        dragRef(n);
        dropRef(n);
      }}
      {...listeners}
      {...attributes}
      data-testid={`cell-${staffId}-${day}`}
      className="day-cell"
      style={style}
      onClick={() => onClick({ staffId, day })}
    >
      {cell?.locked && (
        <span data-testid={`lock-${staffId}-${day}`} className="lock-badge">
          🔒
        </span>
      )}
      {cell?.text ?? ''}
    </td>
  );
}
