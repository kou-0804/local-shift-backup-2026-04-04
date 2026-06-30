import { describe, it, expect } from 'vitest';
import { triToWire, wireToTri } from './nightSkill';

describe('nightSkill tri-state', () => {
  it('maps inherit to the blank wire value', () => {
    expect(triToWire('inherit')).toBe('');
    expect(triToWire('TRUE')).toBe('TRUE');
    expect(triToWire('FALSE')).toBe('FALSE');
  });
  it('maps a blank/unknown wire value back to inherit', () => {
    expect(wireToTri('')).toBe('inherit');
    expect(wireToTri(null)).toBe('inherit');
    expect(wireToTri('TRUE')).toBe('TRUE');
    expect(wireToTri('FALSE')).toBe('FALSE');
  });
});
