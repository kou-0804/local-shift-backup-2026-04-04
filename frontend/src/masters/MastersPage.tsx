import { useEffect, type ReactElement } from 'react';
import { useMasterSets } from './query/useMasterData';
import { useMastersStore } from './store/mastersStore';
import { MasterSetSelector } from './shell/MasterSetSelector';
import { MasterNav, MASTER_LABEL } from './shell/MasterNav';
import { SafetyGateBanner } from './shell/SafetyGateBanner';
import { EDITOR_REGISTRY } from './editors/registry';
import type { MasterKind } from './types';
import './masters.css';

const MASTER_KINDS: MasterKind[] = [
  'staff',
  'skill',
  'location_set',
  'special_rules',
  'training',
  'night_quota',
  'night_overrides',
  'holiday_targets',
  'requests',
];

function EditorRegion({ master, setId }: { master: MasterKind; setId: number }): ReactElement {
  const Editor = EDITOR_REGISTRY[master];
  if (Editor) return <Editor setId={setId} />;
  return <p data-testid="editor-placeholder">{MASTER_LABEL[master]}（準備中）</p>;
}

/** Shell for the master-management section (?view=masters): set selector +
 *  clone-before-edit, safety-gate banner, 9-tab nav, and one editor per master. */
export function MastersPage() {
  const { data: sets } = useMasterSets();
  const selectedSetId = useMastersStore((s) => s.selectedSetId);
  const selectedMaster = useMastersStore((s) => s.selectedMaster);
  const selectSet = useMastersStore((s) => s.selectSet);
  const selectMaster = useMastersStore((s) => s.selectMaster);

  // Seed the selected master from `?m=` once.
  useEffect(() => {
    const m = new URLSearchParams(window.location.search).get('m');
    if (m && (MASTER_KINDS as string[]).includes(m)) selectMaster(m as MasterKind);
  }, [selectMaster]);

  // Seed the selected set from `?set=` (or the first set) once the list loads.
  useEffect(() => {
    if (!sets || sets.length === 0 || selectedSetId != null) return;
    const wanted = Number(new URLSearchParams(window.location.search).get('set'));
    const chosen = sets.find((s) => s.master_set_id === wanted) ?? sets[0];
    selectSet(chosen.master_set_id, chosen.parent_set_id == null);
  }, [sets, selectedSetId, selectSet]);

  return (
    <div className="masters-page">
      <h1>マスター管理</h1>
      <MasterSetSelector />
      {selectedSetId != null && <SafetyGateBanner setId={selectedSetId} />}
      <MasterNav />
      <section className="master-editor" role="tabpanel">
        {selectedSetId != null ? (
          <EditorRegion master={selectedMaster} setId={selectedSetId} />
        ) : (
          <p>マスターセットを選択してください。</p>
        )}
      </section>
    </div>
  );
}
