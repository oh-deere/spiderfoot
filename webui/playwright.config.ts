import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';
import { fileURLToPath } from 'node:url';

// ESM-safe __dirname (webui/package.json sets "type": "module").
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const REPO_ROOT = path.resolve(__dirname, '..');
const FIXTURE_DIR = path.resolve(__dirname, 'tests/e2e/fixtures');
const SEED_SCRIPT = path.resolve(FIXTURE_DIR, 'seed_db.py');
const SPIDERFOOT_DATA = path.resolve(FIXTURE_DIR, 'spiderfoot-e2e');

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5990',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command:
      `rm -rf ${SPIDERFOOT_DATA} && ` +
      `mkdir -p ${SPIDERFOOT_DATA} && ` +
      `python3 ${SEED_SCRIPT} ${SPIDERFOOT_DATA}/spiderfoot.db && ` +
      `SPIDERFOOT_DATA=${SPIDERFOOT_DATA} ` +
      `python3 ${REPO_ROOT}/sf.py -l 127.0.0.1:5990`,
    url: 'http://127.0.0.1:5990/',
    // Always spin up a fresh server so the seed step runs each time; the
    // delete/empty-state tests mutate the DB, so reusing a server would
    // leave the fixture in an intermediate state.
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
