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

test.describe('Clone scan (M5)', () => {
  // Earlier specs mutate the fixture DB (02-empty-state wipes it,
  // 03-new-scan adds one row). Reseed so "monthly-recon" is present.
  // --reseed keeps the SQLite file intact while replacing its rows.
  test.beforeAll(() => {
    const result = spawnSync('python3', [SEED_SCRIPT, DB_PATH, '--reseed'], {
      stdio: 'inherit',
    });
    if (result.status !== 0) {
      throw new Error(`seed_db.py --reseed failed (exit ${result.status})`);
    }
  });

  test('row menu Clone action lands in NewScanPage with prefilled name', async ({ page }) => {
    await page.goto('/');
    const rowName = 'monthly-recon';
    await expect(page.getByText(rowName)).toBeVisible();

    // Open row action menu + click Clone.
    await page
      .getByRole('button', { name: new RegExp(`Actions for ${rowName}`) })
      .click();
    await page.getByRole('menuitem', { name: 'Clone' }).click();

    // Landed on /newscan?clone=<guid>.
    await page.waitForURL(/\/newscan\?clone=.+/, { timeout: 10_000 });

    // Scan Name input is prefilled with "monthly-recon (clone)".
    const nameInput = page.getByLabel(/Scan Name/);
    await expect(nameInput).toHaveValue(`${rowName} (clone)`);
  });
});
