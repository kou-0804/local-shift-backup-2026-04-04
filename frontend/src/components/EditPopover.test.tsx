import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditPopover } from './EditPopover';

const props = {
  staffId: 'T013',
  day: 16,
  date: '2026-06-16',
  locked: false,
  statsColumns: ['夜勤', 'CT', 'MG', '公休', '代休'],
};

describe('EditPopover', () => {
  it('emits an assign op (staff_id key) when a location is chosen', async () => {
    const onEmit = vi.fn();
    render(<EditPopover {...props} onEmit={onEmit} onClose={() => {}} />);
    await userEvent.selectOptions(screen.getByTestId('loc-select'), 'CT');
    await userEvent.click(screen.getByTestId('apply-assign'));
    expect(onEmit).toHaveBeenCalledWith({ op: 'assign', staff_id: 'T013', date: '2026-06-16', location: 'CT' });
  });

  it('emits unassign', async () => {
    const onEmit = vi.fn();
    render(<EditPopover {...props} onEmit={onEmit} onClose={() => {}} />);
    await userEvent.click(screen.getByTestId('apply-unassign'));
    expect(onEmit).toHaveBeenCalledWith({ op: 'unassign', staff_id: 'T013', date: '2026-06-16' });
  });

  it('emits toggle_lock with the flipped value', async () => {
    const onEmit = vi.fn();
    render(<EditPopover {...props} onEmit={onEmit} onClose={() => {}} />);
    await userEvent.click(screen.getByTestId('toggle-lock'));
    expect(onEmit).toHaveBeenCalledWith({ op: 'toggle_lock', staff_id: 'T013', date: '2026-06-16', locked: true });
  });

  it('配置して固定: assigns and locks in one step (needs a location)', async () => {
    const onAssignAndLock = vi.fn();
    render(
      <EditPopover {...props} onEmit={() => {}} onAssignAndLock={onAssignAndLock} onClose={() => {}} />,
    );
    // disabled until a location is chosen
    expect(screen.getByTestId('apply-assign-lock')).toBeDisabled();
    await userEvent.selectOptions(screen.getByTestId('loc-select'), 'CT');
    await userEvent.click(screen.getByTestId('apply-assign-lock'));
    expect(onAssignAndLock).toHaveBeenCalledWith('T013', '2026-06-16', 'CT');
  });
});
