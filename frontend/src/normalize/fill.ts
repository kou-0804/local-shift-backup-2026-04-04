// Server grid sends "FFFF00" (no #); edit deltas send "#FFFFFF". Normalize both.
export const normalizeFill = (fill: string | null | undefined): string | null => {
  if (!fill) return null;
  return fill.startsWith('#') ? fill : `#${fill}`;
};

// Port of shift_scheduler fill_for() for thin optimistic feedback ONLY.
// Authoritative fill always comes from the server edit response.
export const localFillFor = (text: string): string | null => {
  if (text.includes('夜')) return '#FFFF00';
  if (text === '○') return '#FFC0CB';
  if (text === '★' || text === '☆' || text === '◆') return '#FFCDD2';
  if (text === '休') return '#D3D3D3';
  return null;
};
