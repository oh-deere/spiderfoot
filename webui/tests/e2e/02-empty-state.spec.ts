import { test, expect } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import * as path from 'path';
import { fileURLToPath } from 'node:url';

// ESM-safe __dirname (webui/package.json sets "type": "module").
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const FIXTURE_DIR = path.resolve(__dirname, 'fixtures');
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const DATA_DIR = path.resolve(FIXTURE_DIR, 'spiderfoot-e2e');
const DB_PATH = path.resolve(DATA_DIR, 'spiderfoot.db');

test.describe('Empty state', () => {
  test.beforeAll(async () => {
    // Empty the fixture DB so the running sf.py serves /scanlist -> [].
    // The running backend shares the DB with us (SQLite; next /scanlist
    // poll reads the emptied table directly).
    const result = spawnSync('python3', [
      '-c',
      `import sys
sys.path.insert(0, "${REPO_ROOT}")
from spiderfoot import SpiderFootDb
db = SpiderFootDb({"__database": "${DB_PATH}"})
with db.dbhLock:
    db.dbh.execute("DELETE FROM tbl_scan_instance")
    db.conn.commit()
`,
    ], { stdio: 'inherit' });
    if (result.status !== 0) {
      throw new Error(`Failed to empty the fixture DB (exit ${result.status})`);
    }
  });

  test('shows empty-state message when there are no scans', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByText(/No scans yet/)).toBeVisible();
  });
});
