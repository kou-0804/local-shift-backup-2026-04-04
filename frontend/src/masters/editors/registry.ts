import type { ComponentType } from 'react';
import type { MasterKind } from '../types';
import { StaffEditor } from './StaffEditor';
import { HolidayTargetsEditor } from './HolidayTargetsEditor';
import { SkillMatrixEditor } from './SkillMatrixEditor';
import { LocationPowerBalanceEditor } from './LocationPowerBalanceEditor';

export type EditorComponent = ComponentType<{ setId: number }>;

/** Editors registered per master kind. MastersPage reads this; an unregistered kind
 *  renders a placeholder. Each P3b editor task appends its entry below. */
export const EDITOR_REGISTRY: Partial<Record<MasterKind, EditorComponent>> = {
  staff: StaffEditor,
  holiday_targets: HolidayTargetsEditor,
  skill: SkillMatrixEditor,
  location_set: LocationPowerBalanceEditor,
};
