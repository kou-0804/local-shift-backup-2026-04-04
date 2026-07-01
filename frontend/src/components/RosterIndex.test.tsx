import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RosterIndex } from './RosterIndex';
import * as rosterApi from '../api/rosterApi';
import type { WireRosterSummary } from '../domain/wire';

const renderIndex = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RosterIndex />
    </QueryClientProvider>,
  );
};

const ROSTERS: WireRosterSummary[] = [
  { id: 2, year: 2026, month: 6, status: 'draft', created_at: '2026-06-30T06:36:50+00:00', confirmed_at: null },
  { id: 1, year: 2026, month: 6, status: 'confirmed', created_at: '2026-06-29T14:49:48+00:00', confirmed_at: '2026-06-29T15:00:00+00:00' },
];

describe('RosterIndex', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('lists rosters with month, status, and a /?rid= link each', async () => {
    vi.spyOn(rosterApi, 'listRosters').mockResolvedValue(ROSTERS);
    renderIndex();

    await waitFor(() => expect(screen.getAllByText('2026年6月')).toHaveLength(2));
    expect(screen.getByText('作成中')).toBeInTheDocument();
    expect(screen.getByText('確定')).toBeInTheDocument();

    const links = screen.getAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/?rid=2', '/?rid=1']);
  });

  it('shows the creation date in JST, not UTC (no off-by-one near midnight)', async () => {
    // UTC 2026-06-30T17:00 == JST 2026-07-01 02:00 → must read as 07/01, not 06/30.
    vi.spyOn(rosterApi, 'listRosters').mockResolvedValue([
      { id: 9, year: 2026, month: 7, status: 'draft', created_at: '2026-06-30T17:00:00+00:00', confirmed_at: null },
    ]);
    renderIndex();
    await waitFor(() => expect(screen.getByText(/作成:/)).toBeInTheDocument());
    expect(screen.getByText(/作成:/)).toHaveTextContent('2026/07/01');
  });

  it('shows an empty-state message when there are no rosters', async () => {
    vi.spyOn(rosterApi, 'listRosters').mockResolvedValue([]);
    renderIndex();
    await waitFor(() => expect(screen.getByText(/まだ勤務表がありません/)).toBeInTheDocument());
    expect(screen.queryAllByRole('link')).toHaveLength(0);
  });

  it('surfaces a fetch error instead of dead-ending', async () => {
    vi.spyOn(rosterApi, 'listRosters').mockRejectedValue(new Error('boom'));
    renderIndex();
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('勤務表一覧の取得に失敗しました'),
    );
  });
});
