import type { WireWarnings } from '../domain/wire';
import type { ClientWarnings } from '../domain/model';

/** Collapse the GET-flavored and edit-flavored wire warning shapes into one
 *  fully-defaulted client shape so components never branch on which arrived. */
export function normalizeWarnings(w?: WireWarnings): ClientWarnings {
  return {
    coverage: w?.coverage ?? [],
    holiday_deficit: w?.holiday_deficit ?? [],
    consecutive: w?.consecutive ?? [],
    skill: w?.skill ?? [],
    night_hb_gaps: w?.night_hb_gaps ?? [],
    off_counts: w?.off_counts ?? {},
    daikyu_counts: w?.daikyu_counts ?? {},
  };
}
