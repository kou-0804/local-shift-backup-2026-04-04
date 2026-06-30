import { assertPbLocationRef, ClientValidationError } from '../../validation/validators';
import type { LocationSet, PowerBalanceRow } from '../../types';

/** Group additive power-balance rows by 場所コード (a location may have several rank rows). */
export function groupPbByCode(rows: PowerBalanceRow[]): Map<string, PowerBalanceRow[]> {
  const map = new Map<string, PowerBalanceRow[]>();
  for (const r of rows) {
    const list = map.get(r.loc_code) ?? [];
    list.push(r);
    map.set(r.loc_code, list);
  }
  return map;
}

/** Throws ClientValidationError on a duplicate section-A loc_code or any section-B
 *  loc_code that has no section-A location. */
export function validateLocationSet({ locations, power_balance }: LocationSet): void {
  const seen = new Set<string>();
  for (const loc of locations) {
    if (seen.has(loc.loc_code)) {
      throw new ClientValidationError('場所コード', `場所コード「${loc.loc_code}」が重複しています`);
    }
    seen.add(loc.loc_code);
  }
  for (const row of power_balance) {
    assertPbLocationRef(row.loc_code, seen);
  }
}

/** Power-balance rows whose location is inactive (有効=×) — now dead references. */
export function deadPbRows(set: LocationSet): PowerBalanceRow[] {
  const inactive = new Set(set.locations.filter((l) => l.active === '×').map((l) => l.loc_code));
  return set.power_balance.filter((r) => inactive.has(r.loc_code));
}
