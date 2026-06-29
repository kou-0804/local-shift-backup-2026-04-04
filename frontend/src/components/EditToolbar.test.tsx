import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditToolbar } from './EditToolbar';

const base = {
  rosterId: 'R1',
  undoAvailable: true,
  redoAvailable: false,
  onUndo: vi.fn(),
  onRedo: vi.fn(),
  onConfirm: vi.fn(),
  onResolve: vi.fn(),
  resolveEnabled: false,
};

describe('EditToolbar', () => {
  it('binds undo/redo disabled state to the flags', () => {
    render(<EditToolbar {...base} />);
    expect(screen.getByTestId('btn-undo')).toBeEnabled();
    expect(screen.getByTestId('btn-redo')).toBeDisabled();
  });
  it('disables Re-solve when not enabled (P2b dark-launch)', () => {
    render(<EditToolbar {...base} />);
    expect(screen.getByTestId('btn-resolve')).toBeDisabled();
  });
  it('exposes the Excel download as a link to GET /excel', () => {
    render(<EditToolbar {...base} />);
    expect(screen.getByTestId('btn-excel')).toHaveAttribute('href', '/rosters/R1/excel');
  });
  it('fires undo', async () => {
    render(<EditToolbar {...base} />);
    await userEvent.click(screen.getByTestId('btn-undo'));
    expect(base.onUndo).toHaveBeenCalled();
  });
});
