import { useQuery } from '@tanstack/react-query';
import { listRosters } from '../api/rosterApi';
import { rosterListKey } from './queryClient';
import type { WireRosterSummary } from '../domain/wire';

/** Roster index for the picker shown when no ?rid= is selected. */
export function useRosterList() {
  return useQuery<WireRosterSummary[]>({
    queryKey: rosterListKey,
    queryFn: listRosters,
  });
}
