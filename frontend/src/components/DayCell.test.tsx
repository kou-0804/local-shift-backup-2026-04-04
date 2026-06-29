import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { DayCell } from './DayCell';
import type { Cell } from '../domain/model';

const cell: Cell = { day: 3, text: '病CT夜', kind: 'night', fill: '#FFFF00', locked: true };

// DayCell renders a <td>; wrap in a valid table to avoid DOM nesting warnings.
function renderCell(node: ReactNode) {
  return render(
    <table>
      <tbody>
        <tr>{node}</tr>
      </tbody>
    </table>,
  );
}

describe('DayCell', () => {
  it('renders text, applies fill, shows a lock badge when locked', () => {
    renderCell(<DayCell staffId="T013" cell={cell} onClick={() => {}} />);
    expect(screen.getByText('病CT夜')).toBeInTheDocument();
    const el = screen.getByTestId('cell-T013-3');
    expect(el).toHaveStyle({ backgroundColor: '#FFFF00' });
    expect(screen.getByTestId('lock-T013-3')).toBeInTheDocument();
  });

  it('calls onClick with the cell ref', async () => {
    const onClick = vi.fn();
    renderCell(<DayCell staffId="T013" cell={cell} onClick={onClick} />);
    await userEvent.click(screen.getByTestId('cell-T013-3'));
    expect(onClick).toHaveBeenCalledWith({ staffId: 'T013', day: 3 });
  });
});
