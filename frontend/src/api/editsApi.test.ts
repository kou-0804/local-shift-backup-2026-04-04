import { describe, it, expect, vi, beforeEach } from 'vitest';
import { postEdit } from './editsApi';
import { ConflictError } from './http';
import type { WireEditResponse } from '../domain/wire';

const okResp: WireEditResponse = {
  edit_id: 1,
  seq: 1,
  version: 5,
  changed_cells: [],
  stats: {},
  warnings: { coverage: [], holiday_deficit: [], consecutive: [], skill: [], night_hb_gaps: [] },
  undo_available: true,
  redo_available: false,
};

describe('postEdit', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('POSTs op + expected_version (staff_id key) and returns the parsed response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(okResp), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const res = await postEdit('R1', { op: 'assign', staff_id: 'T013', date: '2026-06-16', location: 'CT' }, 4);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/rosters/R1/edits');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({
      op: 'assign',
      staff_id: 'T013',
      date: '2026-06-16',
      location: 'CT',
      expected_version: 4,
    });
    expect(res.version).toBe(5);
  });

  it('throws ConflictError carrying the server detail (version+grid) on 409', async () => {
    const detail = { version: 9, grid: { rows: [] }, warnings: {} };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail }), {
          status: 409,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    const err = await postEdit('R1', { op: 'assign', staff_id: 'T1', date: '2026-06-01', location: 'CT' }, 1).catch(
      (e) => e,
    );
    expect(err).toBeInstanceOf(ConflictError);
    expect((err as ConflictError).serverVersion).toBe(9);
    expect((err as ConflictError).serverGrid).toEqual({ rows: [] });
  });
});
