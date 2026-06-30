import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NightSkillEditor } from './NightSkillEditor';
import * as api from '../api/mastersApi';

// Authoritative wire: tri-state is TRUE / FALSE / '' (blank = inherit).
const ROWS = [
  { tech_id: 'T010', sname: '石川　和弥', night_mr: 'TRUE', night_cath: 'FALSE', night_angio: '' },
];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NightSkillEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('NightSkillEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders three tri-state selects with inherit distinct from FALSE', async () => {
    vi.spyOn(api, 'getNightOverrides').mockResolvedValue(ROWS as never);
    renderEditor();
    const mr = (await screen.findByTestId('ns-mr-T010')) as HTMLSelectElement;
    expect(mr.value).toBe('TRUE');
    expect((screen.getByTestId('ns-angio-T010') as HTMLSelectElement).value).toBe('inherit');
    expect([...mr.options].map((o) => o.value)).toEqual(['TRUE', 'FALSE', 'inherit']);
  });

  it('sends inherit as a blank override on save', async () => {
    vi.spyOn(api, 'getNightOverrides').mockResolvedValue(ROWS as never);
    const put = vi.spyOn(api, 'putNightOverrides').mockResolvedValue({} as never);
    renderEditor();
    await userEvent.selectOptions(await screen.findByTestId('ns-mr-T010'), 'inherit');
    await userEvent.click(screen.getByTestId('ns-save-T010'));
    const payload = put.mock.calls[0][1] as Array<{ night_mr: string }>;
    expect(payload[0].night_mr).toBe('');
  });
});
