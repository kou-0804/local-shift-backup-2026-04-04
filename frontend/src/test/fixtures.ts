import type { WireRosterResponse, WireEditResponse } from '../domain/wire';

export const gridFixture: WireRosterResponse = {
  version: 4,
  status: 'editing',
  year: 2026,
  month: 6,
  grid: {
    year: 2026,
    month: 6,
    days_in_month: 30, // June 2026
    weekdays: { '1': '月', '2': '火', '3': '水', '4': '木' },
    stats_columns: ['夜勤', 'CT', '公休', '代休'],
    holidays: [],
    rows: [
      {
        staff_id: 'T013',
        staff_num: 13,
        name: '佐藤(海)',
        cells: { '1': 'CT', '2': '○', '3': '病CT夜', '4': '' },
        cell_meta: {
          '1': { kind: 'work', fill: null, locked: false },
          '2': { kind: 'akemei', fill: 'FFC0CB', locked: false },
          '3': { kind: 'night', fill: 'FFFF00', locked: true },
          '4': { kind: 'empty', fill: null, locked: false },
        },
        has_work: true,
        stats: { 夜勤: 2, CT: 7, 公休: 9, 代休: 0 },
      },
      {
        staff_id: 'T020',
        staff_num: 20,
        name: '田中',
        cells: { '1': '休', '2': '', '3': '', '4': '' },
        cell_meta: { '1': { kind: 'off', fill: 'D3D3D3', locked: false } },
        has_work: false,
        stats: null,
      },
    ],
    oncall_rows: [{ label: '第1拘束', cells: { '1': '佐藤海', '2': '' } }],
  },
  warnings: {
    coverage: [],
    holiday_deficit: [],
    consecutive: [],
    skill: [],
    night_hb_gaps: [],
    off_counts: {},
    daikyu_counts: {},
  },
};

export const nightEditResponseFixture: WireEditResponse = {
  edit_id: 7,
  seq: 3,
  version: 5,
  // a night assignment on day 15 derives a D+1 明け '○' on day 16 — client cannot predict this
  changed_cells: [
    { staff_id: 'T013', date: '2026-06-15', text: '病CT夜', category: 'night', locked: false, fill: '#FFFF00', warnings: [] },
    { staff_id: 'T013', date: '2026-06-16', text: '○', category: 'akemei', locked: false, fill: '#FFC0CB', warnings: [] },
  ],
  stats: { T013: { 夜勤: 3, CT: 7, 公休: 9, 代休: 0 } },
  warnings: {
    coverage: [{ date: '2026-06-15', location: 'ク', required: 3, assigned: 2, short: 1 }],
    holiday_deficit: [],
    consecutive: [],
    skill: [],
    night_hb_gaps: [],
  },
  undo_available: true,
  redo_available: false,
};
