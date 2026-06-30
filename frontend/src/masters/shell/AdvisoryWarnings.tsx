import type { AdvisoryWarning } from '../types';

interface Props {
  warnings: AdvisoryWarning[];
  onDismiss?: () => void;
}

/** Renders non-blocking advisory warnings[] from a mutation response (or a local
 *  side-effect notice). Dismissible; never blocks the save. */
export function AdvisoryWarnings({ warnings, onDismiss }: Props) {
  if (warnings.length === 0) return null;
  return (
    <div role="status" className="advisory-warnings">
      <ul>
        {warnings.map((w, i) => (
          <li key={i}>{w.code ? `[${w.code}] ${w.message}` : w.message}</li>
        ))}
      </ul>
      {onDismiss && (
        <button type="button" onClick={onDismiss}>
          閉じる
        </button>
      )}
    </div>
  );
}
