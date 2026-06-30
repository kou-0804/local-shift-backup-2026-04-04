import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LocationPowerBalanceEditor } from './LocationPowerBalanceEditor';
import * as api from '../api/mastersApi';

const LOCS = [
  { loc_code: '病院MR', loc_name: 'MRI', category: 'MR', mon: 1, tue: 1, wed: 1, thu: 1, fri: 1, sat: 0, sun: 0, gender_constraint: 'なし', display_order: 1, active: '○' },
];
const PB = [{ loc_code: '病院MR', min_rank: 'A', min_count: 1, cd_cap: null, d_solo_ban: '' }];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LocationPowerBalanceEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('LocationPowerBalanceEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders both sub-editors from the location + power_balance reads', async () => {
    vi.spyOn(api, 'getLocation').mockResolvedValue(LOCS as never);
    vi.spyOn(api, 'getPowerBalance').mockResolvedValue(PB as never);
    renderEditor();
    await waitFor(() => expect(screen.getByTestId('loc-grid')).toBeInTheDocument());
    expect(screen.getByTestId('pb-grid')).toBeInTheDocument();
  });

  it('saves both tables in ONE PUT /location_set', async () => {
    vi.spyOn(api, 'getLocation').mockResolvedValue(LOCS as never);
    vi.spyOn(api, 'getPowerBalance').mockResolvedValue(PB as never);
    const put = vi.spyOn(api, 'putLocationSet').mockResolvedValue({} as never);
    renderEditor();
    await screen.findByTestId('loc-grid');
    await userEvent.click(screen.getByTestId('locset-save'));
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0][1]).toMatchObject({
      locations: expect.any(Array),
      power_balance: expect.any(Array),
    });
  });

  it('warns when toggling 有効 to ×', async () => {
    vi.spyOn(api, 'getLocation').mockResolvedValue(LOCS as never);
    vi.spyOn(api, 'getPowerBalance').mockResolvedValue(PB as never);
    renderEditor();
    await userEvent.click(await screen.findByTestId('loc-active-病院MR'));
    expect(screen.getByText(/スケジュール対象から外れます/)).toBeInTheDocument();
  });
});
