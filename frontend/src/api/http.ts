import type { WireConflictDetail, WireGrid } from '../domain/wire';

const BASE = import.meta.env.VITE_API_BASE ?? '';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
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

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.status === 409) throw new ConflictError(extractConflictDetail(await readJson(res)));
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${path}`);
  return res.json() as Promise<T>;
}

export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}
