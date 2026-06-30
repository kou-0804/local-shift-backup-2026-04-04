import type { WireConflictDetail, WireGrid } from '../domain/wire';

const BASE = import.meta.env.VITE_API_BASE ?? '';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Thrown on HTTP 401 (no/expired session). Extends ApiError so existing
 *  `instanceof ApiError` handlers still catch it, while useAuth/LoginGate can
 *  detect "not authenticated" specifically via `instanceof AuthError`. */
export class AuthError extends ApiError {
  constructor(message = 'authentication required') {
    super(401, message);
    this.name = 'AuthError';
  }
}

/** Thrown on HTTP 409. Carries the FastAPI `detail` payload so the client can
 *  rebase from the server's current grid (or surface a nothing-to-undo reason). */
export class ConflictError extends Error {
  constructor(public detail: WireConflictDetail) {
    super('version conflict (409)');
    this.name = 'ConflictError';
  }
  get serverVersion(): number {
    return this.detail.version;
  }
  get serverGrid(): WireGrid | null {
    return this.detail.grid ?? null;
  }
  get reason(): string | undefined {
    return this.detail.reason;
  }
}

async function readJson(res: Response): Promise<unknown> {
  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) return res.json();
  try {
    return JSON.parse(await res.text());
  } catch {
    return {};
  }
}

// FastAPI wraps HTTPException payloads under `detail`; tolerate a bare detail too.
function extractConflictDetail(parsed: unknown): WireConflictDetail {
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>;
    if (obj.detail && typeof obj.detail === 'object') return obj.detail as WireConflictDetail;
    return obj as unknown as WireConflictDetail;
  }
  return { version: 0 };
}

/** The custom backend ValidationError envelope: HTTP 422 `{ detail: { field?, message } }`. */
export interface ServerValidationDetail {
  field?: string;
  message: string;
}

/** Thrown on HTTP 422. Carries the backend `detail` so the UI can render the
 *  field + JP message inline (never swallowed). */
export class ServerValidationError extends Error {
  constructor(public detail: ServerValidationDetail) {
    super(detail.message);
    this.name = 'ServerValidationError';
  }
}

/** Shared non-2xx handler for the master API verbs: 422 → ServerValidationError,
 *  any other non-ok → ApiError. Reads (getJson) keep their own simpler path. */
async function check(res: Response, path: string): Promise<Response> {
  if (res.status === 401) throw new AuthError(`401 ${path}`);
  if (res.status === 422) {
    const body = (await readJson(res)) as { detail?: ServerValidationDetail };
    throw new ServerValidationError(body.detail ?? { message: `422 ${path}` });
  }
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res;
}

// credentials: 'same-origin' makes the httpOnly `session` cookie flow with every
// API call (same origin in dev via proxy and in prod via mount_spa).
export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    credentials: 'same-origin',
  });
  if (res.status === 409) throw new ConflictError(extractConflictDetail(await readJson(res)));
  return (await check(res, path)).json() as Promise<T>;
}

export async function putJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    credentials: 'same-origin',
  });
  return (await check(res, path)).json() as Promise<T>;
}

export async function delJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE', credentials: 'same-origin' });
  return (await check(res, path)).json() as Promise<T>;
}

/** POST raw bytes (e.g. the 予定申請 CSV) — the body is the file content itself,
 *  NOT multipart/form-data. The backend reads `request.body()` directly. */
export async function postRaw<T>(path: string, body: BodyInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'text/csv' },
    body,
    credentials: 'same-origin',
  });
  return (await check(res, path)).json() as Promise<T>;
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: 'same-origin' });
  if (res.status === 401) throw new AuthError(`401 ${path}`);
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}
