import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { cloneSet } from '../api/mastersApi';
import { ServerValidationError } from '../../api/http';
import type { ServerValidationDetail } from '../../api/http';
import { useMastersStore } from '../store/mastersStore';
import { masterKey } from './masterKeys';
import type { AdvisoryWarning, MasterKind } from '../types';

export interface RunOpts<T> {
  /** Extract advisory warnings from the mutation response, if any. */
  warnings?: (r: T) => AdvisoryWarning[];
}

/**
 * Generic master write hook with clone-before-edit. `run(setId, fn)`:
 *  1. if the store-selected set is pristine and matches `setId`, clones it first and
 *     re-targets via onCloned (so the seeded set is never mutated);
 *  2. runs the mutation against the (possibly new) writable set id;
 *  3. on success invalidates the master query + stashes advisory warnings;
 *  4. on ServerValidationError stashes {field,message} for ValidationErrorList
 *     (does NOT throw to an error boundary). Other errors propagate.
 *
 * In isolated editor tests the store is untouched (selectedSetId=null), so no clone
 * fires and `fn` runs directly against the passed setId.
 */
export function useMasterMutation(master: MasterKind) {
  const qc = useQueryClient();
  const [isPending, setPending] = useState(false);
  const [warnings, setWarnings] = useState<AdvisoryWarning[]>([]);
  const [serverError, setServerError] = useState<ServerValidationDetail | null>(null);

  const ensureWritable = useCallback(async (setId: number): Promise<number> => {
    const st = useMastersStore.getState();
    if (st.pristine && st.selectedSetId === setId) {
      const res = await cloneSet(setId);
      st.onCloned(res);
      return res.master_set_id;
    }
    return setId;
  }, []);

  const run = useCallback(
    async <T>(
      setId: number,
      fn: (writableSetId: number) => Promise<T>,
      opts?: RunOpts<T>,
    ): Promise<T | undefined> => {
      setServerError(null);
      setPending(true);
      try {
        const writableSetId = await ensureWritable(setId);
        const result = await fn(writableSetId);
        setWarnings(opts?.warnings ? opts.warnings(result) : []);
        await qc.invalidateQueries({ queryKey: masterKey(writableSetId, master) });
        useMastersStore.getState().clearDirty();
        return result;
      } catch (err) {
        if (err instanceof ServerValidationError) {
          setServerError(err.detail);
          return undefined;
        }
        throw err;
      } finally {
        setPending(false);
      }
    },
    [ensureWritable, qc, master],
  );

  const reset = useCallback(() => {
    setWarnings([]);
    setServerError(null);
  }, []);

  return { run, isPending, warnings, serverError, reset };
}
