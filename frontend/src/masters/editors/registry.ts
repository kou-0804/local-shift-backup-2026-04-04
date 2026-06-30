import type { ComponentType } from 'react';
import type { MasterKind } from '../types';

export type EditorComponent = ComponentType<{ setId: number }>;

/** Editors registered per master kind. MastersPage reads this; an unregistered kind
 *  renders a placeholder. Each P3b editor task appends its entry below. */
export const EDITOR_REGISTRY: Partial<Record<MasterKind, EditorComponent>> = {};
