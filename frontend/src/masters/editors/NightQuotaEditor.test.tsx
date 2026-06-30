import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NightQuotaEditor } from './NightQuotaEditor';
import * as api from '../api/mastersApi';

// Authoritative GET /night_quota: bare entries array {name, count, tech_id?}.
const ENTRIES = [
  { tech_id: 'T003', name: '矢野　昌男', count: 2 },
  { tech_id: 'T004', name: '田中　一', count: 1 },
];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NightQuotaEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('NightQuotaEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('shows one numeric field per active staff for the picked month', async () => {
    vi.spyOn(api, 'getNightQuota').mockResolvedValue(ENTRIES as never);
    renderEditor();
    await waitFor(() => expect(screen.getByTestId('nq-count-T003')).toHaveValue(2));
  });

  it('blocks save when the running total drifts from the required count', async () => {
    vi.spyOn(api, 'getNightQuota').mockResolvedValue(ENTRIES as never);
    const save = vi.spyOn(api, 'putNightQuota');
    renderEditor();
    const f = await screen.findByTestId('nq-count-T003');
    await userEvent.clear(f);
    await userEvent.type(f, '5'); // sum 6 != required 3
    await userEvent.click(screen.getByTestId('nq-save'));
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(/合計/);
  });
});
