import type { OnCallRow } from '../domain/model';

export function OnCallRows({ rows, days }: { rows: OnCallRow[]; days: number[] }) {
  return (
    <>
      {rows.map((r) => (
        <tr key={r.label} className="oncall-row">
          <td className="sticky-name" colSpan={2}>
            {r.label}
          </td>
          {days.map((d) => (
            <td key={d} className="day-cell">
              {r.cells.get(d) ?? ''}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
