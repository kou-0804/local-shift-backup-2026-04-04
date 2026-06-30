import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TrainingEditor } from './TrainingEditor';
import * as api from '../api/mastersApi';

const TRAIN = [
  { modality: '病院MR', rank_a_only: false, instructor_ids: ['T005'], trainee_ids: ['T040'], display_name: '(MR)' },
];
const STAFF = [
  { tech_id: 'T005', name: '指導　太郎' },
  { tech_id: 'T040', name: '育成　花子' },
];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TrainingEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('TrainingEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders staff names from stable ids', async () => {
    vi.spyOn(api, 'getTraining').mockResolvedValue(TRAIN as never);
    vi.spyOn(api, 'listStaff').mockResolvedValue(STAFF as never);
    renderEditor();
    // Regex avoids the U+3000 full-width-space normalizer mismatch; name appears as both
    // a chip and a picker option, so assert at least one resolved name renders.
    await waitFor(() => expect(screen.getAllByText(/指導/).length).toBeGreaterThan(0));
  });

  it('rank-A toggle replaces the instructor picker and emits the sentinel', async () => {
    vi.spyOn(api, 'getTraining').mockResolvedValue(TRAIN as never);
    vi.spyOn(api, 'listStaff').mockResolvedValue(STAFF as never);
    const put = vi.spyOn(api, 'putTraining').mockResolvedValue({} as never);
    renderEditor();
    await userEvent.click(await screen.findByTestId('train-rankA-病院MR'));
    await userEvent.click(screen.getByTestId('train-save-病院MR'));
    expect(put).toHaveBeenCalledTimes(1);
    const payload = put.mock.calls[0][1] as Array<{ rank_a_only: boolean; instructor_ids: string[] }>;
    expect(payload[0]).toMatchObject({ rank_a_only: true, instructor_ids: [] });
  });

  it('saves authoritative instructor/trainee text rebuilt from ids (backend re-resolves)', async () => {
    vi.spyOn(api, 'getTraining').mockResolvedValue(TRAIN as never);
    vi.spyOn(api, 'listStaff').mockResolvedValue(STAFF as never);
    const put = vi.spyOn(api, 'putTraining').mockResolvedValue({} as never);
    renderEditor();
    await screen.findAllByText(/指導/); // staff loaded → nameOf resolves ids to names (chip + option)
    await userEvent.click(screen.getByTestId('train-save-病院MR'));
    const payload = put.mock.calls[0][1] as Array<{ instructor_text?: string; trainee_text?: string }>;
    expect(payload[0].instructor_text).toBe('指導　太郎');
    expect(payload[0].trainee_text).toBe('育成　花子');
  });
});
