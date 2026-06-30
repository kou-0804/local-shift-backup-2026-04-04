import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SpecialRulesEditor } from './SpecialRulesEditor';
import * as api from '../api/mastersApi';

const RULES = [
  {
    rule_id: 'SR-06',
    loc_code: '精',
    weekday: '水金',
    week: '-',
    required_count: 1,
    rank_cond: 'A',
    rank_count: 1,
    source_loc: null,
    source_rank: null,
    note: '',
  },
];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SpecialRulesEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('SpecialRulesEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('shows 水金 as Wed+Fri selected', async () => {
    vi.spyOn(api, 'getSpecialRules').mockResolvedValue(RULES as never);
    renderEditor();
    await waitFor(() => expect(screen.getByTestId('sr-wd-水')).toBeChecked());
    expect(screen.getByTestId('sr-wd-金')).toBeChecked();
  });

  it('warns that string rank conditions are not enforced', async () => {
    vi.spyOn(api, 'getSpecialRules').mockResolvedValue([{ ...RULES[0], rank_cond: 'D同士禁止' }] as never);
    renderEditor();
    await waitFor(() => expect(screen.getByText(/未適用|未実装/)).toBeInTheDocument());
  });

  it('serializes Wed+Fri back to the 水金 token on save', async () => {
    vi.spyOn(api, 'getSpecialRules').mockResolvedValue(RULES as never);
    const put = vi.spyOn(api, 'putSpecialRules').mockResolvedValue({} as never);
    renderEditor();
    await screen.findByTestId('sr-save-SR-06');
    await userEvent.click(screen.getByTestId('sr-save-SR-06'));
    expect(put).toHaveBeenCalledTimes(1);
    const payload = put.mock.calls[0][1] as Array<{ weekday: string }>;
    expect(payload[0]).toMatchObject({ weekday: '水金' });
  });
});
