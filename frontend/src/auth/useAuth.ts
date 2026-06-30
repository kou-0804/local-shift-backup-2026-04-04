import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AuthError } from '../api/http';
import { login as apiLogin, logout as apiLogout, me as apiMe, type SessionUser } from './authApi';
import type { Role } from './roles';

export const AUTH_KEY = ['auth', 'me'] as const;

export interface UseAuth {
  user: SessionUser | null;
  role: Role | null;
  isLoading: boolean;
  login: (loginId: string, password: string) => Promise<SessionUser>;
  logout: () => Promise<void>;
}

export function useAuth(): UseAuth {
  const qc = useQueryClient();
  const query = useQuery<SessionUser | null>({
    queryKey: AUTH_KEY,
    queryFn: async () => {
      try {
        return await apiMe();
      } catch (e) {
        if (e instanceof AuthError) return null; // not authenticated -> no user
        throw e; // surface real errors (never swallow)
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  const login = async (loginId: string, password: string) => {
    const u = await apiLogin(loginId, password);
    qc.setQueryData(AUTH_KEY, u);
    return u;
  };

  const logout = async () => {
    await apiLogout();
    qc.setQueryData(AUTH_KEY, null);
    qc.clear(); // drop any role-restricted cached data on sign-out
  };

  return {
    user: query.data ?? null,
    role: query.data?.role ?? null,
    isLoading: query.isLoading,
    login,
    logout,
  };
}
