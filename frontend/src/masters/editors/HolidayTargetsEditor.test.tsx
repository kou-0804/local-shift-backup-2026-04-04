import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HolidayTargetsEditor } from './HolidayTargetsEditor';
import * as api from '../api/mastersApi';

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <HolidayTargetsEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('HolidayTargetsEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders the 2-col table', async () => {
    vi.spyOn(api, 'getHolidayTargets').mockResolvedValue([{ year_month: '2026/04', holiday_count: 9 }]);
    renderEditor();
    await waitFor(() => expect(screen.getByDisplayValue('2026/04')).toBeInTheDocument());
  });

  it('rejects an un-padded month before calling the API', async () => {
    vi.spyOn(api, 'getHolidayTargets').mockResolvedValue([]);
    const upsert = vi.spyOn(api, 'upsertHolidayTarget');
    renderEditor();
    await screen.findByTestId('ht-add');
    await userEvent.click(screen.getByTestId('ht-add'));
    await userEvent.type(screen.getByTestId('ht-ym-new'), '2026/4');
    await userEvent.type(screen.getByTestId('ht-count-new'), '9');
    await userEvent.click(screen.getByTestId('ht-save-new'));
    expect(upsert).not.toHaveBeenCalled();
    expect(screen.getByText(/ゼロ埋め/)).toBeInTheDocument();
  });
});
