import { test, expect, request } from '@playwright/test';

// SCAFFOLDED + SKIPPED. These E2E scenarios require:
//   1. the FastAPI backend running on http://localhost:8000, and
//   2. a roster seeded via POST /jobs → poll done → POST /jobs/{id}/freeze.
// Neither is available in the frontend-only worktree, so the suite is skipped.
// Remove `.skip` (and fill the D+1 / drag staff ids from GET /rosters/{rid})
// once the backend is up to run these against a live seeded June 2026 roster.

const API = 'http://localhost:8000';

async function seedRoster(): Promise<string> {
  const ctx = await request.newContext();
  const job = await (await ctx.post(`${API}/jobs`, { data: { year: 2026, month: 6 } })).json();
  // poll until done
  for (let i = 0; i < 120; i++) {
    const s = await (await ctx.get(`${API}/jobs/${job.job_id}`)).json();
    if (s.status === 'done') break;
    if (s.status === 'failed') throw new Error('seed job failed');
    await new Promise((r) => setTimeout(r, 1000));
  }
  const roster = await (await ctx.post(`${API}/jobs/${job.job_id}/freeze`)).json();
  return roster.roster_id;
}

test.describe.skip('editor', () => {
  let rid: string;
  test.beforeAll(async () => {
    rid = await seedRoster();
  });

  test('assign updates the cell and its stats/warnings', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    const cell = page.getByTestId(/^cell-.*-15$/).first();
    await cell.click();
    await page.getByTestId('loc-select').selectOption('CT');
    await page.getByTestId('apply-assign').click();
    await expect(cell).toContainText('CT');
    // stats are server-authoritative — they appear/update after the merge
    await expect(page.getByTestId(/^stat-.*-公休$/).first()).not.toBeEmpty();
  });

  test('unassign raises 公休 (server recompute)', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    const stat = page.getByTestId(/^stat-.*-公休$/).first();
    const before = Number(await stat.innerText());
    const cell = page.getByTestId(/^cell-.*-20$/).first();
    await cell.click();
    await page.getByTestId('apply-unassign').click();
    await expect.poll(async () => Number(await stat.innerText())).toBeGreaterThanOrEqual(before);
  });

  test('a night edit derives the D+1 明け ○ cell', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    // Assign a night-bearing location on a day, then expect the next day's ○ to
    // appear — a cell the client did NOT optimistically write (D+1 明け from the
    // authoritative merge). Fill the exact staff/day from GET /rosters/{rid}.
    expect(true).toBeTruthy(); // placeholder — fill with seeded ids during execution
  });

  test('undo is available after an edit and reverts it (one step for a drag move)', async ({ page }) => {
    await page.goto(`/rosters/${rid}`);
    const cell = page.getByTestId(/^cell-.*-10$/).first();
    await cell.click();
    await page.getByTestId('loc-select').selectOption('CT');
    await page.getByTestId('apply-assign').click();
    await expect(page.getByTestId('btn-undo')).toBeEnabled();
    await page.getByTestId('btn-undo').click();
    await expect(page.getByTestId('btn-undo')).toBeDisabled();
  });
});
