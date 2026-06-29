import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RosterPage } from './RosterPage';
import * as rosterApi from '../api/rosterApi';
import { gridFixture } from '../test/fixtures';

describe('RosterPage', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('loads the roster and renders the grid + a warning panel + toolbar', async () => {
    vi.spyOn(rosterApi, 'getRoster').mockResolvedValue(gridFixture);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <RosterPage rosterId="R1" />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText('佐藤(海)')).toBeInTheDocument());
    expect(screen.getByTestId('btn-undo')).toBeInTheDocument();
    expect(screen.getByText(/勤務不足/)).toBeInTheDocument();
  });
});
