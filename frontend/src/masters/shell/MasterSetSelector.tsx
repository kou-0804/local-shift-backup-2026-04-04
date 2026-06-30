import { useMasterSets } from '../query/useMasterData';
import { cloneSet } from '../api/mastersApi';
import { useMastersStore } from '../store/mastersStore';
import type { MasterSet } from '../types';

/** A seeded set (no parent) is read-only in the UI; the first edit clones it. */
const isPristine = (s: MasterSet) => s.parent_set_id == null;

function setQueryParam(key: string, value: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set(key, value);
  window.history.replaceState(null, '', url.toString());
}

export function MasterSetSelector() {
  const { data: sets } = useMasterSets();
  const selectedSetId = useMastersStore((s) => s.selectedSetId);
  const pristine = useMastersStore((s) => s.pristine);
  const selectSet = useMastersStore((s) => s.selectSet);
  const onCloned = useMastersStore((s) => s.onCloned);

  if (!sets) return <p>マスターセットを読み込み中…</p>;

  const onChange = (id: number) => {
    const set = sets.find((s) => s.master_set_id === id);
    if (!set) return;
    selectSet(set.master_set_id, isPristine(set));
    setQueryParam('set', String(set.master_set_id));
  };

  const onClone = async () => {
    if (selectedSetId == null) return;
    const res = await cloneSet(selectedSetId);
    onCloned(res);
    setQueryParam('set', String(res.master_set_id));
  };

  return (
    <div className="master-set-selector">
      <label>
        マスターセット:{' '}
        <select
          aria-label="マスターセット"
          value={selectedSetId ?? ''}
          onChange={(e) => onChange(Number(e.target.value))}
        >
          {sets.map((s) => (
            <option key={s.master_set_id} value={s.master_set_id}>
              {s.name}
              {isPristine(s) ? '（現行）' : ''}
            </option>
          ))}
        </select>
      </label>
      {pristine && <span className="badge-readonly">読み取り専用</span>}
      <button type="button" onClick={onClone} disabled={selectedSetId == null}>
        編集用に複製
      </button>
    </div>
  );
}
