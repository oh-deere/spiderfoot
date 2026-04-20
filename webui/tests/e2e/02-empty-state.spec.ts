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

test.describe('Empty state', () => {
  // Must run AFTER 01-scan-list.spec.ts — see playwright.config.ts
  // (workers: 1 + fullyParallel: false ensure alphabetical ordering holds).
  test.beforeAll(() => {
    const result = spawnSync('python3', [SEED_SCRIPT, DB_PATH, '--clear'], {
      stdio: 'inherit',
    });
    if (result.status !== 0) {
      throw new Error(`seed_db.py --clear failed (exit ${result.status})`);
    }
  });

  test('shows empty-state message when there are no scans', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/No scans yet/)).toBeVisible();
  });
});
