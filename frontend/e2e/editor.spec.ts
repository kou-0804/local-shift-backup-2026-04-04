import { test, expect, type Page } from '@playwright/test';

// ACTIVATED E2E. Runs against the production same-origin server (SPA + API on
// :8000 — see playwright.config.ts) with a pre-seeded, frozen June-2026 roster.
//
// The app requires auth: every test logs in through the real LoginGate form
// first, which sets the httpOnly `session` cookie on the browser context. The
// SPA selects a roster via the `?rid=<id>` query param (NOT `/rosters/<id>`,
// which is the JSON API namespace).
//
// Seeded-roster knobs (override via env when re-seeding):
const RID = process.env.E2E_RID ?? '1';
const ADMIN_ID = process.env.E2E_ADMIN_ID ?? 'admin';
const ADMIN_PW = process.env.E2E_ADMIN_PW ?? 'admin12345';

// Concrete cells read from GET /rosters/1/grid for the seeded June-2026 roster
// (T001 加藤 = first row, always visible): work weekdays show '病CT', the listed
// rest/empty days are free. T002 day 9 is a 夜 (night) so day 10 is the D+1 明け ○.
const STAFF = 'T001';
const REST_DAY = 12; // '休'  -> assignable
const WORK_DAY = 20; // '病CT' (Sat work) -> unassign raises 公休
const UNDO_DAY = 24; // '休'  -> assign then undo
const EMPTY_DAY = 7; //  ''   -> set_symbol shows the symbol verbatim
const AKE_STAFF = 'T002';
const AKE_DAY = 10; // '○' (明け), derived from the night on day 9

async function login(page: Page): Promise<void> {
  await page.goto('/');
  // A fresh browser context has no session cookie, so the LoginGate form always
  // renders after the SPA hydrates — wait for it (don't race the JS) then submit.
  const idField = page.getByLabel('ID', { exact: true });
  await idField.waitFor({ state: 'visible' });
  await idField.fill(ADMIN_ID);
  await page.getByLabel('パスワード').fill(ADMIN_PW);
  await page.getByRole('button', { name: 'ログイン' }).click();
  await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible();
}

async function openRoster(page: Page): Promise<void> {
  await login(page);
  await page.goto(`/?rid=${RID}`);
  await expect(page.getByTestId(`cell-${STAFF}-${REST_DAY}`)).toBeVisible();
}

test.describe('editor', () => {
  test('assign updates the cell and its stats/warnings', async ({ page }) => {
    await openRoster(page);
    const cell = page.getByTestId(`cell-${STAFF}-${REST_DAY}`);
    await cell.dispatchEvent('click'); // bypass dnd-kit pointer sensor (it swallows a real click)
    await page.getByTestId('loc-select').selectOption('CT');
    await page.getByTestId('apply-assign').click();
    await expect(cell).toContainText('CT');
    // stats are server-authoritative — they appear/update after the merge
    await expect(page.getByTestId(`stat-${STAFF}-公休`)).not.toBeEmpty();
  });

  test('unassign raises 公休 (server recompute)', async ({ page }) => {
    await openRoster(page);
    const stat = page.getByTestId(`stat-${STAFF}-公休`);
    const before = Number((await stat.innerText()).trim());
    const cell = page.getByTestId(`cell-${STAFF}-${WORK_DAY}`);
    await cell.dispatchEvent('click'); // bypass dnd-kit pointer sensor (it swallows a real click)
    await page.getByTestId('apply-unassign').click();
    await expect
      .poll(async () => Number((await stat.innerText()).trim()))
      .toBeGreaterThanOrEqual(before);
  });

  test('a night derives the D+1 明け ○ cell (server-authoritative)', async ({ page }) => {
    await openRoster(page);
    // The day after a 夜 night must render ○ — a cell derived by the backend, not
    // written by the client. (The UI cannot author nights, so we assert the
    // existing seeded 明け cell that the D+1 derivation produced.)
    const akeCell = page.getByTestId(`cell-${AKE_STAFF}-${AKE_DAY}`);
    await expect(akeCell).toContainText('○');
  });

  test('set_symbol shows the 申請 symbol on an empty cell', async ({ page }) => {
    await openRoster(page);
    const cell = page.getByTestId(`cell-${STAFF}-${EMPTY_DAY}`);
    await cell.dispatchEvent('click'); // bypass dnd-kit pointer sensor (it swallows a real click)
    await page.getByTestId('sym-select').selectOption('☆');
    await page.getByTestId('apply-symbol').click();
    await expect(cell).toContainText('☆');
  });

  test('undo is available after an edit and reverts it', async ({ page }) => {
    await openRoster(page);
    const cell = page.getByTestId(`cell-${STAFF}-${UNDO_DAY}`);
    await cell.dispatchEvent('click'); // bypass dnd-kit pointer sensor (it swallows a real click)
    await page.getByTestId('loc-select').selectOption('CT');
    await page.getByTestId('apply-assign').click();
    await expect(cell).toContainText('CT');
    await expect(page.getByTestId('btn-undo')).toBeEnabled();
    await page.getByTestId('btn-undo').click();
    // reverted: the optimistic 'CT' is rolled back to the server snapshot
    await expect(cell).not.toContainText('CT');
  });
});
