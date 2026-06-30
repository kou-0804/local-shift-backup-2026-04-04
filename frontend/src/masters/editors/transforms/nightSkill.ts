import type { Tri } from '../../types';

/** Tri-state → wire. inherit is the blank string '' (the backend only lets exact
 *  TRUE/FALSE take effect; anything else inherits from スキルマスタ). */
export function triToWire(tri: Tri): string {
  return tri === 'inherit' ? '' : tri;
}

/** Wire → tri-state. Only exact 'TRUE'/'FALSE' map through; '', null, or any unknown
 *  value is inherit. */
export function wireToTri(value: string | null | undefined): Tri {
  return value === 'TRUE' || value === 'FALSE' ? value : 'inherit';
}
