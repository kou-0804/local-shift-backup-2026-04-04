import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getJson, postJson, AuthError, ApiError } from './http';

describe('http 401 -> AuthError', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('getJson maps 401 to AuthError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('{"detail":"x"}', { status: 401, headers: { 'content-type': 'application/json' } }),
    ));
    await expect(getJson('/auth/me')).rejects.toBeInstanceOf(AuthError);
  });

  it('postJson maps 401 to AuthError (also an ApiError)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response('{"detail":"x"}', { status: 401, headers: { 'content-type': 'application/json' } }),
    ));
    const err = await postJson('/jobs', {}).catch((e) => e);
    expect(err).toBeInstanceOf(AuthError);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(401);
  });

  it('sends same-origin credentials so the session cookie flows', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('{"role":"admin"}', { status: 200, headers: { 'content-type': 'application/json' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    await getJson('/auth/me');
    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe('same-origin');
  });
});
