import { useQuery } from '@tanstack/react-query';
import { getRoster } from '../api/rosterApi';
import { normalizeGrid } from '../normalize/normalizeGrid';
import { rosterKey } from './queryClient';
import type { RosterState } from '../domain/model';

export function useRoster(rid: string) {
  return useQuery<RosterState>({
    queryKey: rosterKey(rid),
    queryFn: async () => normalizeGrid(rid, await getRoster(rid)),
  });
}
