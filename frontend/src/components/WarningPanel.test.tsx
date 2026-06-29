import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WarningPanel } from './WarningPanel';
import { normalizeGrid } from '../normalize/normalizeGrid';
import { gridFixture } from '../test/fixtures';
import { useUiStore } from '../store/uiStore';

const state = normalizeGrid('R1', {
  ...gridFixture,
  warnings: {
    coverage: [{ date: '2026-06-01', location: 'ク', required: 3, assigned: 2, short: 1 }],
    holiday_deficit: [{ staff_id: 'T020', off: 8, target: 9, short: 1 }],
    consecutive: [{ staff_id: 'T013', start: '2026-06-10', len: 7 }],
    skill: [],
  },
});

describe('WarningPanel', () => {
  beforeEach(() => useUiStore.getState().reset());

  it('groups warnings under coverage/holiday/consecutive/skill headers', () => {
    render(<WarningPanel state={state} />);
    expect(screen.getByText(/勤務不足/)).toBeInTheDocument();
    expect(screen.getByText(/公休不足/)).toBeInTheDocument();
    expect(screen.getByText(/連続勤務/)).toBeInTheDocument();
  });

  it('clicking a warning sets highlighted cells in the store', async () => {
    render(<WarningPanel state={state} />);
    await userEvent.click(screen.getByTestId('warn-consecutive-0'));
    expect(useUiStore.getState().highlighted.size).toBe(7);
  });
});
