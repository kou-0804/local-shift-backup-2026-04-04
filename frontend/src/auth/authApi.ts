import { getJson, postJson } from '../api/http';
import type { Role } from './roles';

export interface SessionUser {
  uid: number;
  login_id: string;
  role: Role;
  name: string;
}

/** Log in with local credentials. The backend sets an httpOnly `session` cookie;
 *  the returned body is the public user record. Throws AuthError on bad creds. */
export function login(loginId: string, password: string): Promise<SessionUser> {
  return postJson<SessionUser>('/auth/login', { login_id: loginId, password });
}

export async function logout(): Promise<void> {
  await postJson('/auth/logout', {});
}

/** Current session. Throws AuthError (401) when not logged in. */
export function me(): Promise<SessionUser> {
  return getJson<SessionUser>('/auth/me');
}
