import { useState, type FormEvent, type ReactNode } from 'react';
import { useAuth } from './useAuth';
import { can } from './roles';
import './auth.css';

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
      <div className="login-wrap">
        <form aria-label="login" className="login-card" onSubmit={onSubmit}>
          <h1 className="login-title">勤務表システム</h1>
          <p className="login-sub">ログインしてください</p>
          <label className="login-field">
            <span className="login-field-label">ID</span>
            <input
              className="login-input"
              name="login_id"
              aria-label="ID"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label className="login-field">
            <span className="login-field-label">パスワード</span>
            <input
              className="login-input"
              name="password"
              aria-label="パスワード"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <button className="login-btn" type="submit" disabled={submitting}>
            ログイン
          </button>
          {error && (
            <p role="alert" className="login-error">
              {error}
            </p>
          )}
        </form>
      </div>
    );
  }

  return (
    <div>
      <header className="auth-bar">
        <a href="/">勤務表</a>
        {can(role, 'generate') && <a href="/?view=create">勤務表作成</a>}
        {can(role, 'editMasters') && <a href="/?view=masters">マスタ管理</a>}
        <span className="auth-spacer auth-user">
          {user.name || user.login_id}（{role}）
        </span>
        <button type="button" className="auth-logout" onClick={() => void logout()}>
          ログアウト
        </button>
      </header>
      {children}
    </div>
  );
}
