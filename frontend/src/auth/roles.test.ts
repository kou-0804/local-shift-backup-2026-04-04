import { describe, it, expect } from 'vitest';
import { can, type Capability } from './roles';

describe('can', () => {
  it('admin can do everything', () => {
    const caps: Capability[] = [
      'generate', 'editRoster', 'editMasters', 'confirm', 'manageUsers', 'viewArchive',
    ];
    for (const cap of caps) expect(can('admin', cap)).toBe(true);
  });

  it('editor edits rosters but cannot confirm or manage users', () => {
    expect(can('editor', 'editRoster')).toBe(true);
    expect(can('editor', 'viewArchive')).toBe(true);
    expect(can('editor', 'confirm')).toBe(false);
    expect(can('editor', 'manageUsers')).toBe(false);
    expect(can('editor', 'editMasters')).toBe(false);
    expect(can('editor', 'generate')).toBe(false);
  });

  it('viewer can only view archive', () => {
    expect(can('viewer', 'viewArchive')).toBe(true);
    expect(can('viewer', 'editRoster')).toBe(false);
    expect(can('viewer', 'generate')).toBe(false);
    expect(can('viewer', 'confirm')).toBe(false);
    expect(can('viewer', 'manageUsers')).toBe(false);
  });
});
