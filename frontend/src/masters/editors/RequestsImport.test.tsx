import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RequestsImport } from './RequestsImport';
import * as api from '../api/mastersApi';

function renderImport() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RequestsImport setId={2} />
    </QueryClientProvider>,
  );
}

describe('RequestsImport', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('uploads, previews, and reports unresolved RSName before commit', async () => {
    vi.spyOn(api, 'previewRequests').mockResolvedValue({
      row_count: 2,
      rows: [
        { date: '2026-07-01', symbol: '☆', raw_rsname: '03 矢野　昌男', tech_id_resolved: 'T003', resolve_status: 'resolved' },
      ],
      unresolved: ['99 幽霊'],
    } as never);
    renderImport();
    const file = new File(['x'], '予定申請.csv', { type: 'text/csv' });
    await userEvent.upload(screen.getByTestId('req-file'), file);
    await waitFor(() => expect(screen.getByText(/99 幽霊/)).toBeInTheDocument());
    expect(screen.getByText(/未解決/)).toBeInTheDocument();
  });

  it('commits to the picked year/month after preview', async () => {
    vi.spyOn(api, 'previewRequests').mockResolvedValue({ row_count: 1, rows: [], unresolved: [] } as never);
    const commit = vi.spyOn(api, 'commitRequests').mockResolvedValue({ import_id: 5 } as never);
    renderImport();
    await userEvent.upload(screen.getByTestId('req-file'), new File(['x'], '予定申請.csv'));
    await userEvent.click(await screen.findByTestId('req-commit'));
    expect(commit).toHaveBeenCalled();
  });
});
