import { useMastersStore } from '../store/mastersStore';
import type { MasterKind } from '../types';

/** The 9 master tabs: 8 editable masters + the 予定申請 import. */
export const MASTER_TABS: { kind: MasterKind; label: string }[] = [
  { kind: 'staff', label: '技師マスタ' },
  { kind: 'skill', label: 'スキルマスタ' },
  { kind: 'location_set', label: '勤務場所マスタ' },
  { kind: 'special_rules', label: '特殊配置ルール' },
  { kind: 'training', label: '業務拡大' },
  { kind: 'night_quota', label: '夜勤回数' },
  { kind: 'night_overrides', label: '夜勤スキル一覧' },
  { kind: 'holiday_targets', label: '公休数' },
  { kind: 'requests', label: '予定申請' },
];

export const MASTER_LABEL: Record<MasterKind, string> = MASTER_TABS.reduce(
  (acc, t) => ({ ...acc, [t.kind]: t.label }),
  {} as Record<MasterKind, string>,
);

function setQueryParam(key: string, value: string): void {
  const url = new URL(window.location.href);
  url.searchParams.set(key, value);
  window.history.replaceState(null, '', url.toString());
}

export function MasterNav() {
  const selectedMaster = useMastersStore((s) => s.selectedMaster);
  const selectMaster = useMastersStore((s) => s.selectMaster);

  return (
    <div role="tablist" aria-label="マスター選択" className="master-nav">
      {MASTER_TABS.map((t) => (
        <button
          key={t.kind}
          role="tab"
          type="button"
          aria-selected={selectedMaster === t.kind}
          data-master={t.kind}
          onClick={() => {
            selectMaster(t.kind);
            setQueryParam('m', t.kind);
          }}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
