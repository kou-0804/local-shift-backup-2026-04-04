import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MastersPage } from './MastersPage';
import { useMastersStore } from './store/mastersStore';
import * as api from './api/mastersApi';

const SETS = [
  { master_set_id: 1, name: '現行', created_at: '2026-06-30T00:00:00', parent_set_id: null },
];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MastersPage />
    </QueryClientProvider>,
  );
}

describe('MastersPage shell', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useMastersStore.getState().reset();
  });

  it('lists sets and shows the 9 master tabs', async () => {
    vi.spyOn(api, 'listMasterSets').mockResolvedValue(SETS as never);
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: true, missing: [] });
    renderPage();
    await waitFor(() => expect(screen.getByRole('option', { name: /現行/ })).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: '技師マスタ' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '予定申請' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(9);
  });

  it('switches the active editor when a tab is clicked', async () => {
    vi.spyOn(api, 'listMasterSets').mockResolvedValue(SETS as never);
    vi.spyOn(api, 'safetyCheck').mockResolvedValue({ ok: true, missing: [] });
    renderPage();
    const staffTab = await screen.findByRole('tab', { name: '技師マスタ' });
    await waitFor(() => expect(staffTab).toHaveAttribute('aria-selected', 'true'));
    const holidayTab = screen.getByRole('tab', { name: '公休数' });
    await userEvent.click(holidayTab);
    expect(holidayTab).toHaveAttribute('aria-selected', 'true');
    expect(staffTab).toHaveAttribute('aria-selected', 'false');
  });
});
