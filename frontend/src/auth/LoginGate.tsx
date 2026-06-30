import { useState, type FormEvent, type ReactNode } from 'react';
import { useAuth } from './useAuth';
import { can } from './roles';

/**
 * Wraps the whole app. Until a session exists it renders a login form; once
 * authenticated it renders a session bar (user + role + logout) and the app.
 * The masters-management entry point is hidden for roles lacking `editMasters`
 * (backend stays authoritative — this only hides the control).
 */
export function LoginGate({ children }: { children: ReactNode }) {
  const { user, role, isLoading, login, logout } = useAuth();
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isLoading) {
    return <div role="status">読み込み中…</div>;
  }

  if (!user || !role) {
    const onSubmit = async (e: FormEvent) => {
      e.preventDefault();
      setError(null);
      setSubmitting(true);
      try {
        await login(loginId, password);
      } catch {
        setError('ログインに失敗しました。IDまたはパスワードを確認してください。');
      } finally {
        setSubmitting(false);
      }
    };
    return (
      <form aria-label="login" onSubmit={onSubmit} style={{ maxWidth: 320, margin: '4rem auto' }}>
        <h1>勤務表システム ログイン</h1>
        <label style={{ display: 'block', marginBottom: 8 }}>
          ID
          <input
            name="login_id"
            aria-label="ID"
            value={loginId}
            onChange={(e) => setLoginId(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label style={{ display: 'block', marginBottom: 8 }}>
          パスワード
          <input
            name="password"
            aria-label="パスワード"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        <button type="submit" disabled={submitting}>
          ログイン
        </button>
        {error && (
          <p role="alert" style={{ color: 'crimson' }}>
            {error}
          </p>
        )}
      </form>
    );
  }

  return (
    <div>
      <header
        className="auth-bar"
        style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '6px 12px', borderBottom: '1px solid #ddd' }}
      >
        <a href="/">勤務表</a>
        {can(role, 'editMasters') && <a href="/?view=masters">マスタ管理</a>}
        <span style={{ marginLeft: 'auto' }}>
          {user.name || user.login_id}（{role}）
        </span>
        <button type="button" onClick={() => void logout()}>
          ログアウト
        </button>
      </header>
      {children}
    </div>
  );
}
