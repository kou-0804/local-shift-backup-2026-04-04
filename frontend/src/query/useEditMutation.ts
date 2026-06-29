import { useMutation, useQueryClient } from '@tanstack/react-query';
import { rosterKey } from './queryClient';
import { postEdit, postUndo, postRedo } from '../api/editsApi';
import { applyOptimistic, mergeEditResponse } from '../normalize/mergeEdit';
import { ConflictError } from '../api/http';
import type { RosterState } from '../domain/model';
import type { EditOp } from '../domain/editOps';
import type { WireEditResponse } from '../domain/wire';

type Action = { kind: 'edit'; op: EditOp } | { kind: 'undo' } | { kind: 'redo' };

export function useEditMutation(rid: string, onConflict?: (err: ConflictError) => void) {
  const qc = useQueryClient();
  const key = rosterKey(rid);

  const m = useMutation<WireEditResponse, unknown, Action, { prev?: RosterState }>({
    onMutate: async (action) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<RosterState>(key);
      if (prev && action.kind === 'edit') {
        qc.setQueryData<RosterState>(key, applyOptimistic(prev, action.op)); // edited cell only
      }
      return { prev };
    },
    mutationFn: async (action) => {
      const state = qc.getQueryData<RosterState>(key);
      const version = state?.version ?? 0;
      if (action.kind === 'edit') return postEdit(rid, action.op, version);
      if (action.kind === 'undo') return postUndo(rid, version);
      return postRedo(rid, version);
    },
    onSuccess: (resp) => {
      const cur = qc.getQueryData<RosterState>(key);
      if (cur) qc.setQueryData<RosterState>(key, mergeEditResponse(cur, resp)); // authoritative
    },
    onError: (err, _action, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev); // roll back optimistic first
      if (err instanceof ConflictError) {
        if (err.serverGrid) onConflict?.(err); // stale version → rebase from server grid
        else void qc.invalidateQueries({ queryKey: key }); // nothing-to-undo/redo → refetch
      }
    },
  });

  return {
    edit: (op: EditOp) => m.mutateAsync({ kind: 'edit', op }),
    undo: () => m.mutateAsync({ kind: 'undo' }),
    redo: () => m.mutateAsync({ kind: 'redo' }),
    isPending: m.isPending,
  };
}
