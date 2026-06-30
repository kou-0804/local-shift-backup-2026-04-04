import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StaffEditor } from './StaffEditor';
import * as api from '../api/mastersApi';

const ROW = {
  tech_id: 'T001',
  name: '小川　龍史',
  gender: '男',
  experience_years: 20,
  night_ok: '○',
  status: '在籍',
  note: '',
  oncall_ok: '○',
} as const;

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StaffEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('StaffEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders imported rows', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([ROW as never]);
    renderEditor();
    await waitFor(() => expect(screen.getByDisplayValue('T001')).toBeInTheDocument());
  });

  it('blocks save on a non-Tnnn id and shows an inline error', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([ROW as never]);
    const create = vi.spyOn(api, 'createStaff');
    renderEditor();
    await screen.findByDisplayValue('T001');
    await userEvent.click(screen.getByTestId('staff-add'));
    await userEvent.type(screen.getByTestId('staff-id-new'), 'X1');
    await userEvent.click(screen.getByTestId('staff-save-new'));
    expect(create).not.toHaveBeenCalled();
    expect(screen.getByText(/Tnnn/)).toBeInTheDocument();
  });

  it('warns that renaming 氏名 breaks cross-file joins', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([ROW as never]);
    renderEditor();
    // U+3000 full-width names are collapsed by the TL normalizer, so locate the input
    // by its stable testid rather than its display value.
    const nameInput = await screen.findByTestId('staff-name-T001');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, '小川　竜史');
    expect(screen.getByText(/結合キー/)).toBeInTheDocument();
  });

  it('surfaces that 退職 does not auto-exclude from scheduling', async () => {
    vi.spyOn(api, 'listStaff').mockResolvedValue([{ ...ROW, status: '退職' } as never]);
    renderEditor();
    await waitFor(() => expect(screen.getByText(/自動的に除外されません/)).toBeInTheDocument());
  });
});
