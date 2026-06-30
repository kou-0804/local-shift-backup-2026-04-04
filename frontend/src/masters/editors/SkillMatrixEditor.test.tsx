import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SkillMatrixEditor } from './SkillMatrixEditor';
import * as api from '../api/mastersApi';

// Authoritative GET /skill shape: bare array of {tech_id, name, cells}.
const ROWS = [{ tech_id: 'T001', name: '小川　龍史', cells: { 病院MR: 'A', CT: 'B' } }];

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SkillMatrixEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('SkillMatrixEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders cells as {A,B,C,D,-} selects (no free text)', async () => {
    vi.spyOn(api, 'getSkillMatrix').mockResolvedValue(ROWS as never);
    renderEditor();
    const sel = (await screen.findByTestId('skill-T001-病院MR')) as HTMLSelectElement;
    expect([...sel.options].map((o) => o.value)).toEqual(['A', 'B', 'C', 'D', '-']);
  });

  it('warns about night-eligibility loss when 病院MR drops below B', async () => {
    vi.spyOn(api, 'getSkillMatrix').mockResolvedValue(ROWS as never);
    vi.spyOn(api, 'updateSkillCell').mockResolvedValue({
      tech_id: 'T001',
      updated: true,
      warnings: [],
    });
    renderEditor();
    const sel = await screen.findByTestId('skill-T001-病院MR');
    await userEvent.selectOptions(sel, 'C');
    await waitFor(() => expect(screen.getByText(/夜勤/)).toBeInTheDocument());
  });
});
