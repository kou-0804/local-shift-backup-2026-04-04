import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CreateRosterPage } from './CreateRosterPage';
import * as jobsApi from '../api/jobsApi';
import * as mastersApi from '../masters/api/mastersApi';
import * as useAuthMod from '../auth/useAuth';

vi.mock('../api/jobsApi');
vi.mock('../masters/api/mastersApi');
vi.mock('../auth/useAuth');

function renderPage(onComplete = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CreateRosterPage onComplete={onComplete} />
    </QueryClientProvider>,
  );
  return onComplete;
}

const IMPORTED: jobsApi.RequestsStatus = {
  year: 2026, month: 8, imported: true, import_id: 3, row_count: 5,
  imported_at: '2026-07-01T09:00:00', source_filename: '予定申請.csv',
};

const genBtn = () => screen.getByRole('button', { name: '自動作成を開始' });

describe('CreateRosterPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useAuthMod.useAuth).mockReturnValue({
      user: { uid: 1, login_id: 'admin', role: 'admin', name: '管理者' },
      role: 'admin', isLoading: false, login: vi.fn(), logout: vi.fn(),
    });
    vi.mocked(mastersApi.listMasterSets).mockResolvedValue([
      { master_set_id: 1, name: '現行', created_at: '', parent_set_id: null },
    ]);
    vi.mocked(mastersApi.safetyCheck).mockResolvedValue({ ok: true, missing: [] });
    vi.mocked(jobsApi.getRequestsStatus).mockResolvedValue(IMPORTED);
  });

  it('generates: create → poll(done) → freeze → opens the new roster', async () => {
    vi.mocked(jobsApi.createJob).mockResolvedValue({ id: 'j1', status: 'queued' });
    vi.mocked(jobsApi.getJob).mockResolvedValue({ id: 'j1', status: 'done' });
    vi.mocked(jobsApi.freezeJob).mockResolvedValue({ roster_id: 7 });
    const onComplete = renderPage();

    await waitFor(() => expect(genBtn()).toBeEnabled()); // safety gate resolved OK
    await userEvent.click(genBtn());

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(7));
    expect(jobsApi.createJob).toHaveBeenCalled();
    expect(jobsApi.freezeJob).toHaveBeenCalledWith('j1');
  });

  it('shows 未取り込み with an import link when the month has no 予定申請', async () => {
    vi.mocked(jobsApi.getRequestsStatus).mockResolvedValue({ ...IMPORTED, imported: false, row_count: 0, import_id: null });
    renderPage();
    const link = await screen.findByRole('link', { name: /予定申請タブで取り込む/ });
    expect(link).toHaveAttribute('href', '/?view=masters&m=requests');
  });

  it('surfaces a failed generation (e.g. solver infeasible) without dead-ending', async () => {
    vi.mocked(jobsApi.createJob).mockResolvedValue({ id: 'j1', status: 'queued' });
    vi.mocked(jobsApi.getJob).mockResolvedValue({ id: 'j1', status: 'failed', error: 'No solution found for night shifts.' });
    renderPage();

    await waitFor(() => expect(genBtn()).toBeEnabled());
    await userEvent.click(genBtn());

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('No solution found'));
    expect(jobsApi.freezeJob).not.toHaveBeenCalled();
  });

  it('blocks generation when the masters safety check fails', async () => {
    vi.mocked(mastersApi.safetyCheck).mockResolvedValue({ ok: false, missing: ['T001'] });
    renderPage();
    await waitFor(() => expect(screen.getByText(/要確認: T001/)).toBeInTheDocument());
    expect(genBtn()).toBeDisabled();
  });

  it('does not disguise a requests-status fetch error as “未取り込み”', async () => {
    vi.mocked(jobsApi.getRequestsStatus).mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => expect(screen.getByText(/状態を取得できませんでした/)).toBeInTheDocument());
    expect(screen.queryByRole('link', { name: /予定申請タブで取り込む/ })).not.toBeInTheDocument();
  });

  it('denies the page to roles without generate capability', async () => {
    vi.mocked(useAuthMod.useAuth).mockReturnValue({
      user: { uid: 2, login_id: 'ed', role: 'editor', name: '編集' },
      role: 'editor', isLoading: false, login: vi.fn(), logout: vi.fn(),
    });
    renderPage();
    expect(screen.getByText(/権限がありません/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '自動作成を開始' })).not.toBeInTheDocument();
  });
});
