import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { safetyCheck } from '../api/mastersApi';
import { masterKey } from '../query/masterKeys';

interface Props {
  setId: number;
  /** Called whenever the gate result is known, so a parent (or the roster generate
   *  action) can disable 生成 when the master set is broken. */
  onResult?: (ok: boolean) => void;
}

/**
 * Blocking safety gate: spec §3.5 hardcodes load-bearing staff IDs. If any are missing
 * from 技師マスタ the backend's GET /safety-check returns {ok:false, missing}, and we
 * render a clear blocking alert that prevents generation.
 */
export function SafetyGateBanner({ setId, onResult }: Props) {
  const { data } = useQuery({
    queryKey: masterKey(setId, 'safety-check'),
    queryFn: () => safetyCheck(setId),
  });

  useEffect(() => {
    if (data) onResult?.(data.ok);
  }, [data, onResult]);

  if (!data || data.ok) return null;

  return (
    <div role="alert" className="safety-gate-banner">
      <strong>生成不可:</strong> コード固定の技師ID{' '}
      <code>{data.missing.join(', ')}</code> が技師マスタに存在しません（§3.5 参照）。
      該当IDを復元するまで勤務表を生成できません。
    </div>
  );
}
