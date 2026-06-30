import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { NightSkillEditor } from './NightSkillEditor';
import * as api from '../api/mastersApi';

// 夜勤スキルは2状態(夜勤可='TRUE' / 夜勤不可='FALSE')。
// 空欄('')は画面でスキルマスタのランク(B以上=可)から派生して表示し、保存で確定する。
const NIGHT_ROWS = [
  { tech_id: 'T010', sname: '石川　和弥', night_mr: '', night_cath: 'FALSE', night_angio: '' },
];
const SKILL_ROWS = [
  { tech_id: 'T010', name: '石川　和弥', cells: { 病院MR: 'B', ア: '-', 心: 'A' } },
];

function mockApi() {
  vi.spyOn(api, 'getNightOverrides').mockResolvedValue(NIGHT_ROWS as never);
  vi.spyOn(api, 'getSkillMatrix').mockResolvedValue(SKILL_ROWS as never);
}

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NightSkillEditor setId={2} />
    </QueryClientProvider>,
  );
}

describe('NightSkillEditor', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders binary 夜勤可/夜勤不可 selects and resolves blanks from the skill master', async () => {
    mockApi();
    renderEditor();
    const mr = (await screen.findByTestId('ns-mr-T010')) as HTMLSelectElement;
    // 病院MR=B → 空欄が「夜勤可」に解決
    expect(mr.value).toBe('TRUE');
    // 明示 FALSE はそのまま
    expect((screen.getByTestId('ns-cath-T010') as HTMLSelectElement).value).toBe('FALSE');
    // ア='-' → 空欄が「夜勤不可」に解決
    expect((screen.getByTestId('ns-angio-T010') as HTMLSelectElement).value).toBe('FALSE');
    expect([...mr.options].map((o) => o.value)).toEqual(['TRUE', 'FALSE']);
    expect([...mr.options].map((o) => o.textContent)).toEqual(['夜勤可', '夜勤不可']);
  });

  it('saves explicit TRUE/FALSE for every field (no blanks) — bakes the resolved values', async () => {
    mockApi();
    const put = vi.spyOn(api, 'putNightOverrides').mockResolvedValue({} as never);
    renderEditor();
    await userEvent.selectOptions(await screen.findByTestId('ns-mr-T010'), 'FALSE');
    await userEvent.click(screen.getByTestId('ns-save-T010'));
    const payload = put.mock.calls[0][1] as Array<{
      night_mr: string;
      night_cath: string;
      night_angio: string;
    }>;
    expect(payload[0].night_mr).toBe('FALSE'); // edited 可→不可
    expect(payload[0].night_cath).toBe('FALSE'); // explicit, unchanged
    expect(payload[0].night_angio).toBe('FALSE'); // resolved blank, now baked
    // 空欄は一切残らない（独立管理の確定）
    expect(Object.values(payload[0])).not.toContain('');
  });
});
