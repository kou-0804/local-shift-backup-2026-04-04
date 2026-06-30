import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LoginGate } from './LoginGate';
import { AuthError } from '../api/http';
import * as authApi from './authApi';
import type { SessionUser } from './authApi';

vi.mock('./authApi');

const ADMIN: SessionUser = { uid: 1, login_id: 'admin', role: 'admin', name: '管理者' };
const VIEWER: SessionUser = { uid: 3, login_id: 'vw', role: 'viewer', name: '閲覧' };

function renderGate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LoginGate>
        <div>PROTECTED CONTENT</div>
      </LoginGate>
    </QueryClientProvider>,
  );
}

describe('LoginGate', () => {
  beforeEach(() => vi.resetAllMocks());

  it('shows the login form when unauthenticated', async () => {
    vi.mocked(authApi.me).mockRejectedValue(new AuthError());
    renderGate();
    await waitFor(() => expect(screen.getByRole('form', { name: 'login' })).toBeInTheDocument());
    expect(screen.queryByText('PROTECTED CONTENT')).not.toBeInTheDocument();
  });

  it('logs in and then renders children', async () => {
    vi.mocked(authApi.me).mockRejectedValue(new AuthError());
    vi.mocked(authApi.login).mockResolvedValue(ADMIN);
    renderGate();
    await screen.findByRole('form', { name: 'login' });

    await userEvent.type(screen.getByLabelText('ID'), 'admin');
    await userEvent.type(screen.getByLabelText('パスワード'), 'adminpw123');
    await userEvent.click(screen.getByRole('button', { name: 'ログイン' }));

    expect(authApi.login).toHaveBeenCalledWith('admin', 'adminpw123');
    await screen.findByText('PROTECTED CONTENT');
  });

  it('surfaces a bad-login error message (never swallowed)', async () => {
    vi.mocked(authApi.me).mockRejectedValue(new AuthError());
    vi.mocked(authApi.login).mockRejectedValue(new AuthError('bad creds'));
    renderGate();
    await screen.findByRole('form', { name: 'login' });

    await userEvent.type(screen.getByLabelText('ID'), 'admin');
    await userEvent.type(screen.getByLabelText('パスワード'), 'nope');
    await userEvent.click(screen.getByRole('button', { name: 'ログイン' }));

    await screen.findByRole('alert');
    expect(screen.queryByText('PROTECTED CONTENT')).not.toBeInTheDocument();
  });

  it('shows the masters link for admin and hides it for viewer', async () => {
    vi.mocked(authApi.me).mockResolvedValue(ADMIN);
    const { unmount } = renderGate();
    await screen.findByText('PROTECTED CONTENT');
    expect(screen.getByRole('link', { name: 'マスタ管理' })).toBeInTheDocument();
    unmount();

    vi.mocked(authApi.me).mockResolvedValue(VIEWER);
    renderGate();
    await screen.findByText('PROTECTED CONTENT');
    expect(screen.queryByRole('link', { name: 'マスタ管理' })).not.toBeInTheDocument();
  });
});
