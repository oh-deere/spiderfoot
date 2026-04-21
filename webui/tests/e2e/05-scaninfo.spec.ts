import { test, expect } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import * as path from 'path';
import { fileURLToPath } from 'node:url';

// ESM-safe __dirname (webui/package.json sets "type": "module").
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const FIXTURE_DIR = path.resolve(__dirname, 'fixtures');
const SEED_SCRIPT = path.resolve(FIXTURE_DIR, 'seed_db.py');
const DB_PATH = path.resolve(FIXTURE_DIR, 'spiderfoot-e2e', 'spiderfoot.db');

async function openFinishedScanInfo(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/');
  const anchor = page.getByRole('link', { name: 'monthly-recon' });
  await expect(anchor).toBeVisible();
  const href = await anchor.getAttribute('href');
  expect(href).toMatch(/\/scaninfo\?id=.+/);
  await anchor.click();
  await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 10_000 });
}

test.describe('Scan info page (M4a: Status + Info + Log)', () => {
  // 02-empty-state wipes the fixture DB, 03-new-scan adds one fresh row
  // named "playwright-newscan-smoke". Reseed the deterministic scans so
  // the "monthly-recon" FINISHED scan exists again. --reseed keeps the
  // SQLite file intact (sf.py has it open) while replacing its rows.
  test.beforeAll(() => {
    const result = spawnSync('python3', [SEED_SCRIPT, DB_PATH, '--reseed'], {
      stdio: 'inherit',
    });
    if (result.status !== 0) {
      throw new Error(`seed_db.py --reseed failed (exit ${result.status})`);
    }
  });

  test('Status tab renders scan summary after navigating from scan list', async ({ page }) => {
    await openFinishedScanInfo(page);
    await expect(page.getByRole('heading', { level: 2, name: 'monthly-recon' })).toBeVisible();
    await expect(page.getByText('FINISHED')).toBeVisible();

    // Status is the default active tab. "Total events" stat should be present.
    await expect(page.getByText('Total events')).toBeVisible();
  });

  test('Info tab renders the scan meta + global/module settings accordions', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Info' }).click();
    await expect(page.getByRole('cell', { name: 'Target', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /Global settings/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /Module settings/ })).toBeVisible();
  });

  test('Log tab shows the Download Logs button with correct href', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Log' }).click();
    const download = page.getByRole('link', { name: /Download logs/ });
    await expect(download).toBeVisible();
    const href = await download.getAttribute('href');
    expect(href).toMatch(/\/scanexportlogs\?id=.+/);
  });
});
