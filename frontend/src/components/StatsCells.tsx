import type { Row } from '../domain/model';

export function StatsCells({ row, statsColumns }: { row: Row; statsColumns: string[] }) {
  return (
    <>
      {statsColumns.map((col) => (
        <td key={col} className="stat-cell" data-testid={`stat-${row.staffId}-${col}`}>
          {row.hasWork && row.stats ? (row.stats[col] ?? 0) : ''}
        </td>
      ))}
    </>
  );
}
