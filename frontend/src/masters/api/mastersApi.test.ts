import { describe, it, expect, vi, afterEach } from 'vitest';
import * as api from './mastersApi';
import { ServerValidationError } from '../../api/http';

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    }),
  );
}
afterEach(() => vi.restoreAllMocks());

describe('mastersApi', () => {
  it('lists master sets (master_set_id shape)', async () => {
    const f = mockFetch(200, [
      { master_set_id: 1, name: '現行', created_at: 'x', parent_set_id: null },
    ]);
    const sets = await api.listMasterSets();
    expect(f.mock.calls[0][0]).toBe('/master-sets');
    expect(sets[0].master_set_id).toBe(1);
  });

  it('lists staff for a set', async () => {
    const f = mockFetch(200, [{ tech_id: 'T001', name: '小川　龍史' }]);
    const rows = await api.listStaff(2);
    expect(f.mock.calls[0][0]).toBe('/masters/2/staff');
    expect(rows[0].tech_id).toBe('T001');
  });

  it('clones a set via POST /masters/{id}/clone returning {master_set_id}', async () => {
    const f = mockFetch(200, { master_set_id: 3 });
    const s = await api.cloneSet(1);
    expect(f.mock.calls[0][0]).toBe('/masters/1/clone');
    expect(f.mock.calls[0][1]?.method).toBe('POST');
    expect(s.master_set_id).toBe(3);
  });

  it('PUTs only the changed skill cell', async () => {
    const f = mockFetch(200, { tech_id: 'T001', updated: true, warnings: [] });
    await api.updateSkillCell(2, 'T001', { 病院MR: 'C' });
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/masters/2/skill/T001');
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(init!.body as string)).toEqual({ 病院MR: 'C' });
  });

  it('PUTs the whole special_rules array (bare array body)', async () => {
    const f = mockFetch(200, []);
    await api.putSpecialRules(2, [{ rule_id: 'SR-06' } as never]);
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/masters/2/special_rules');
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(init!.body as string)).toEqual([{ rule_id: 'SR-06' }]);
  });

  it('PUTs night_quota with the hyphen year_month query', async () => {
    const f = mockFetch(200, []);
    await api.putNightQuota(2, '2026/07', [{ name: '矢野　昌男', count: 2 }]);
    expect(f.mock.calls[0][0]).toBe('/masters/2/night_quota?year_month=2026-07');
    expect(f.mock.calls[0][1]?.method).toBe('PUT');
  });

  it('upserts a holiday target via POST and parses a 422 into ServerValidationError', async () => {
    mockFetch(422, { detail: { field: '年月', message: 'ゼロ埋めYYYY/MM' } });
    await expect(
      api.upsertHolidayTarget(2, { year_month: '2026/4', holiday_count: 9 }),
    ).rejects.toBeInstanceOf(ServerValidationError);
  });

  it('deletes a holiday target by the hyphen path key', async () => {
    const f = mockFetch(200, { ok: true });
    await api.deleteHolidayTarget(2, '2027/03');
    expect(f.mock.calls[0][0]).toBe('/masters/2/holiday_targets/2027-03');
    expect(f.mock.calls[0][1]?.method).toBe('DELETE');
  });

  it('safetyCheck returns ok + missing', async () => {
    mockFetch(200, { ok: false, missing: ['T072'], load_bearing_ids: ['T001'] });
    const r = await api.safetyCheck(2);
    expect(r.missing).toContain('T072');
  });

  it('previewRequests posts raw bytes (not FormData) with the master_set_id query', async () => {
    const f = mockFetch(200, { row_count: 1, rows: [], unresolved: ['99 幽霊'], legend: {} });
    const pv = await api.previewRequests(2, 'date,sym\n');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/masters/requests/preview?master_set_id=2');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe('date,sym\n');
    expect(init?.body).not.toBeInstanceOf(FormData);
    expect(pv.unresolved).toEqual(['99 幽霊']);
  });

  it('commitRequests posts raw bytes to /requests/{y}/{m} with imported_by + source_filename', async () => {
    const f = mockFetch(200, { import_id: 5 });
    const r = await api.commitRequests(2, 2026, 7, 'x', 'kohei', '予定申請_202607.csv');
    const url = f.mock.calls[0][0] as string;
    expect(url).toContain('/masters/requests/2026/7?master_set_id=2');
    expect(url).toContain('imported_by=kohei');
    expect(url).toContain('source_filename=');
    expect(r.import_id).toBe(5);
  });
});
