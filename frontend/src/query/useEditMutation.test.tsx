import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { rosterKey } from './queryClient';
import { useEditMutation } from './useEditMutation';
import { normalizeGrid } from '../normalize/normalizeGrid';
import { gridFixture, nightEditResponseFixture } from '../test/fixtures';
import * as editsApi from '../api/editsApi';
import { ConflictError } from '../api/http';
import type { RosterState } from '../domain/model';
import type { WireConflictDetail } from '../domain/wire';

function wrap(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('useEditMutation', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('optimistically updates then merges the authoritative server response', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(rosterKey('R1'), normalizeGrid('R1', gridFixture));
    vi.spyOn(editsApi, 'postEdit').mockResolvedValue(nightEditResponseFixture);

    const { result } = renderHook(() => useEditMutation('R1'), { wrapper: wrap(qc) });
    await act(async () => {
      await result.current.edit({ op: 'assign', staff_id: 'T013', date: '2026-06-15', location: '病CT夜' });
    });

    await waitFor(() => {
      const s = qc.getQueryData<RosterState>(rosterKey('R1'))!;
      expect(s.version).toBe(5);
      expect(s.rows.find((r) => r.staffId === 'T013')!.cells.get(16)!.text).toBe('○'); // D+1 明け merged
    });
  });

  it('surfaces a 409 ConflictError with the server grid for rebase', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(rosterKey('R1'), normalizeGrid('R1', gridFixture));
    const detail = { version: 9, grid: { rows: [] }, warnings: {} } as unknown as WireConflictDetail;
    vi.spyOn(editsApi, 'postEdit').mockRejectedValue(new ConflictError(detail));
    const onConflict = vi.fn();

    const { result } = renderHook(() => useEditMutation('R1', onConflict), { wrapper: wrap(qc) });
    await act(async () => {
      await result.current.edit({ op: 'assign', staff_id: 'T013', date: '2026-06-15', location: 'CT' }).catch(() => {});
    });
    await waitFor(() => expect(onConflict).toHaveBeenCalled());
    const err = onConflict.mock.calls[0][0] as ConflictError;
    expect(err.serverVersion).toBe(9);
  });
});
