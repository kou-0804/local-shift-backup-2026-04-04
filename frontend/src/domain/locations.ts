// Default pick-list; P3 replaces this with a server-fed location master.
// Work codes (stats columns minus 公休/代休/夜勤) + the special tokens 休/○.
export function locationOptions(statsColumns: string[]): string[] {
  const work = statsColumns.filter((c) => c !== '公休' && c !== '代休' && c !== '夜勤');
  return [...work, '休', '○'];
}

export const REQUEST_SYMBOLS = ['★', '☆', '◆', '出', '17休', '17業', '夜希'];
