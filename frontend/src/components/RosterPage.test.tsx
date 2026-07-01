import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RosterPage } from './RosterPage';
import * as rosterApi from '../api/rosterApi';
import * as editsApi from '../api/editsApi';
import { ServerValidationError } from '../api/http';
import { gridFixture } from '../test/fixtures';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RosterPage rosterId="R1" />
    </QueryClientProvider>,
  );
}

describe('RosterPage', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('loads the roster and renders the grid + a warning panel + toolbar', async () => {
    vi.spyOn(rosterApi, 'getRoster').mockResolvedValue(gridFixture);
    renderPage();
    await waitFor(() => expect(screen.getByText('佐藤(海)')).toBeInTheDocument());
    expect(screen.getByTestId('btn-undo')).toBeInTheDocument();
    expect(screen.getByText(/勤務不足/)).toBeInTheDocument();
  });

  it('再生成(ロック保持): the button is enabled, calls postResolve, then refetches the roster', async () => {
    const getSpy = vi.spyOn(rosterApi, 'getRoster').mockResolvedValue(gridFixture);
    const resolveSpy = vi.spyOn(editsApi, 'postResolve').mockResolvedValue({
      version: 2,
      grid: gridFixture.grid,
      warnings: gridFixture.warnings,
      unlockable: [],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText('佐藤(海)')).toBeInTheDocument());
    expect(screen.getByTestId('btn-resolve')).toBeEnabled();
    const before = getSpy.mock.calls.length;

    await userEvent.click(screen.getByTestId('btn-resolve'));

    await waitFor(() => expect(resolveSpy).toHaveBeenCalledWith('R1'));
    await waitFor(() => expect(getSpy.mock.calls.length).toBeGreaterThan(before)); // roster refetched
  });

  it('再生成: shows an error banner (never dead-ends) when the lock set is impossible', async () => {
    vi.spyOn(rosterApi, 'getRoster').mockResolvedValue(gridFixture);
    vi.spyOn(editsApi, 'postResolve').mockRejectedValue(
      new ServerValidationError({ errors: [1, 2] } as unknown as { message: string }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText('佐藤(海)')).toBeInTheDocument());

    await userEvent.click(screen.getByTestId('btn-resolve'));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('再生成できません'));
  });

  it('clicking a cell opens the edit popover (click not swallowed by drag)', async () => {
    vi.spyOn(rosterApi, 'getRoster').mockResolvedValue(gridFixture);
    renderPage();
    await waitFor(() => expect(screen.getByText('佐藤(海)')).toBeInTheDocument());
    const cells = document.querySelectorAll('[data-testid^="cell-"]');
    expect(cells.length).toBeGreaterThan(0);
    await userEvent.click(cells[0] as HTMLElement);
    expect(screen.getByRole('dialog', { name: 'セル編集' })).toBeInTheDocument();
  });
});
