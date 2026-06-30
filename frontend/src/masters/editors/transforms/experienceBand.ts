// 経験年数の入力バンド。スケジューラが参照する閾値は 3/6/7 のみ（すべて≤10）で、
// 8年以上は全員同一扱い。よって 0–10 は実数、それ以上は2バケットで束ねても
// スケジュール結果は変わらない（shift_scheduler/src/schedulers を参照）。
// 既存の保存値は「バンドを変えない限り」保持する（＝Excel/Power Apps のバイト同一性）。

export interface ExpOption {
  value: string;
  label: string;
}

const B10_15 = 'B10_15';
const B15_PLUS = 'B15_plus';

/** バケットの代表保存値（8以上なら閾値的に同一なので任意。可読性のため 12 / 20）。 */
export const B10_15_REP = 12;
export const B15_PLUS_REP = 20;

export const EXPERIENCE_OPTIONS: ExpOption[] = [
  ...Array.from({ length: 11 }, (_, n) => ({ value: String(n), label: `${n}年` })),
  { value: B10_15, label: '10〜15年' },
  { value: B15_PLUS, label: '15年以上' },
];

/** 経験年数(整数) → 選択肢 value。0–10は実数、11–15は "B10_15"、16+ は "B15_plus"。 */
export function expToOptionValue(exp: number): string {
  const n = Number.isFinite(exp) ? Math.trunc(exp) : 0;
  if (n <= 10) return String(Math.max(0, n));
  if (n <= 15) return B10_15;
  return B15_PLUS;
}

/** 選択肢 value → 保存する整数。バケットは代表値、実数はその数。
 *  ※ <select> の onChange は値が変わった時だけ発火するため、同バンドの再選択で
 *    既存値が代表値に書き換わることはない（既存値は保持される）。 */
export function optionValueToExp(value: string): number {
  if (value === B10_15) return B10_15_REP;
  if (value === B15_PLUS) return B15_PLUS_REP;
  const n = Number(value);
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
}
