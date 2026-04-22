import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';
import { fileURLToPath } from 'node:url';

// ESM-safe __dirname (webui/package.json sets "type": "module").
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const REPO_ROOT = path.resolve(__dirname, '..');
const FIXTURE_DIR = path.resolve(__dirname, 'tests/e2e/fixtures');
const SEED_SCRIPT = path.resolve(FIXTURE_DIR, 'seed_db.py');
const COMPOSE_FILE = path.resolve(REPO_ROOT, 'docker-compose.yml');

// Dev Postgres container (see docker-compose.yml). Host port 55432 avoids
// clashing with a system Postgres some developers already run locally.
const DATABASE_URL = 'postgresql://spiderfoot:dev@localhost:55432/spiderfoot';

// Wait loop: pg_isready against the compose-managed container. 10 iterations
// * 1s = 10s upper bound. Once it returns 0 we break out of the loop.
const WAIT_FOR_PG =
  'for i in 1 2 3 4 5 6 7 8 9 10; do ' +
  `docker compose -f ${COMPOSE_FILE} exec -T postgres pg_isready -U spiderfoot -d spiderfoot 2>/dev/null && break; ` +
  'sleep 1; ' +
  'done';

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
    // 1. docker compose up -d postgres (idempotent — reuses an already-running container).
    // 2. pg_isready loop waits for the healthcheck to pass.
    // 3. seed_db.py --reseed writes the deterministic fixture into Postgres.
    // 4. sf.py picks up the same SPIDERFOOT_DATABASE_URL and serves the UI.
    command:
      `docker compose -f ${COMPOSE_FILE} up -d postgres && ` +
      `${WAIT_FOR_PG} && ` +
      `SPIDERFOOT_DATABASE_URL=${DATABASE_URL} python3 ${SEED_SCRIPT} --reseed && ` +
      `SPIDERFOOT_DATABASE_URL=${DATABASE_URL} python3 ${REPO_ROOT}/sf.py -l 127.0.0.1:5990`,
    url: 'http://127.0.0.1:5990/',
    // Always spin up a fresh server so the seed step runs each time; the
    // delete/empty-state tests mutate the DB, so reusing a server would
    // leave the fixture in an intermediate state.
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
