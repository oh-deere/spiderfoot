# Web UI SPA — Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended). Most tasks are sequential — each builds on the previous. Do NOT dispatch in parallel unless explicitly noted.

**Goal:** Migrate SpiderFoot's scan-list page (`/`) from Mako templates to a React + TypeScript SPA, establishing the full toolchain (Vite + Mantine + TanStack Query + Vitest + Playwright) in a new `webui/` subdirectory. Retire the old Mako `scanlist.tmpl` as part of the work.

**Architecture:** Same-repo `webui/` subdirectory. Vite dev server on `:5173` proxies API calls to CherryPy on `:5001` during dev. Production: `npm run build` outputs `webui/dist/`; Docker's new Node stage produces it; CherryPy serves `/` → `index.html` for SPA routes and static assets under `/static/webui/`. Mako handlers continue to serve unmigrated paths.

**Tech Stack:** Node 22 + Vite 6 + React 19 + TypeScript 5 + Mantine 8 + TanStack Query 5 + React Router 7 + Vitest 2 + Playwright 1.x. Python 3.12+ stdlib for the seed-DB script.

**Spec:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md`.

---

## File Structure

- **Create** `webui/package.json`, `webui/tsconfig.json`, `webui/vite.config.ts`, `webui/playwright.config.ts`, `webui/index.html`
- **Create** `webui/src/main.tsx`, `webui/src/App.tsx`, `webui/src/theme.ts`, `webui/src/router.tsx`, `webui/src/types.ts`
- **Create** `webui/src/api/client.ts`, `webui/src/api/scans.ts`, `webui/src/api/scans.test.ts`
- **Create** `webui/src/components/ScanStatusBadge.tsx`
- **Create** `webui/src/pages/ScanListPage.tsx`, `webui/src/pages/ScanListPage.test.tsx`
- **Create** `webui/tests/e2e/scan-list.spec.ts`, `webui/tests/e2e/empty-state.spec.ts`, `webui/tests/e2e/fixtures/seed_db.py`
- **Create** `webui/public/favicon.svg`
- **Create** `webui/.gitignore` (local to webui)
- **Modify** `.gitignore` at repo root — add `webui/node_modules/`, `webui/dist/`, `webui/test-results/`, `webui/playwright-report/`
- **Modify** `sfwebui.py` — add SPA routing + static mount, delete `index()` / `rootpage()` Mako handlers that render `scanlist.tmpl`
- **Delete** `spiderfoot/templates/scanlist.tmpl`
- **Modify** `Dockerfile` — add `ui-build` Node stage, copy `webui/dist/` into runtime image
- **Modify** `test/run` — add webui build + Vitest + Playwright steps
- **Modify** `CLAUDE.md` — add a "Web UI" section pointing at `webui/`

---

## Context for the implementer

- **Current baseline:** `./test/run` reports 1460 passed + 35 skipped. After this plan: same pytest count + new webui build/test steps run before pytest.
- **Current scan-list endpoint:** `GET /scanlist` on CherryPy returns a JSON array of positional tuples. Row shape: `[guid, name, target, created_unix, started_unix, ended_unix, status, event_count]` — 8 fields.
- **Delete endpoint:** `GET /scandelete?id=<guid>` (CherryPy routes it as GET despite the semantic being delete; keep as-is to match existing behavior).
- **Vite + React + TS in 2026:** use `npm create vite@latest webui -- --template react-ts` for the scaffold.
- **Mantine 8 imports:** `@mantine/core`, `@mantine/hooks`, `@mantine/notifications`, `@mantine/modals`. CSS must be imported in the app entry: `import '@mantine/core/styles.css'`.
- **TanStack Query 5 imports:** `@tanstack/react-query` exports `QueryClient`, `QueryClientProvider`, `useQuery`, `useMutation`.
- **React Router 7 imports:** `react-router-dom` — use `createBrowserRouter` + `RouterProvider`.
- **Running the Python side:** `python3 ./sf.py -l 127.0.0.1:5001`.
- **Running the dev SPA:** `cd webui && npm run dev` (opens `:5173`).
- **Running tests:** `./test/run` from repo root runs everything. Individual: `cd webui && npm test -- --run` (Vitest one-shot), `cd webui && npx playwright test` (E2E).
- **Flake8:** max-line 120, config in `setup.cfg`. Only the Python side; webui is TypeScript.
- **Auth:** the `sf.py` currently warns when no passwd file is present — for dev work that's fine. CherryPy uses a session cookie; the SPA inherits it via `fetch` with `credentials: 'same-origin'`.
- **CherryPy registers the root page via** `class SpiderFootWebUi` — the `@cherrypy.expose` on the method named `index` is what serves `/`. In the current code it renders `scanlist.tmpl` and redirects internally.

---

## Task 1: Scaffold `webui/` with Vite + React + TypeScript

**Files:**
- Create: `webui/package.json`, `webui/tsconfig.json`, `webui/tsconfig.node.json`, `webui/vite.config.ts`, `webui/index.html`
- Create: `webui/src/main.tsx`, `webui/src/App.tsx`, `webui/src/vite-env.d.ts`
- Create: `webui/public/favicon.svg`
- Create: `webui/.gitignore`
- Modify: repo root `.gitignore`

- [ ] **Step 1: Scaffold via `npm create vite`**

Run from repo root:
```bash
npm create vite@latest webui -- --template react-ts
```
Press `y` when asked to install `create-vite`. This produces `webui/` with a standard Vite + React + TypeScript skeleton.

- [ ] **Step 2: Replace the default scaffolded `webui/vite.config.ts`**

Overwrite with:
```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/webui/',  // production URL prefix for hashed assets
  server: {
    port: 5173,
    proxy: {
      // Every path except /static/webui/* proxies to CherryPy during dev.
      // Vite handles static assets; everything else (API, legacy pages) goes through.
      '^/(?!static/webui/|@vite|src|node_modules).*': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
```

- [ ] **Step 3: Set the `webui/index.html` title**

Edit `webui/index.html` to change `<title>Vite + React + TS</title>` to `<title>SpiderFoot</title>`. Remove the default favicon link if present; we'll add a proper one in a moment.

- [ ] **Step 4: Simplify `webui/src/App.tsx` and `webui/src/main.tsx`**

Replace `webui/src/App.tsx` with:
```tsx
export default function App() {
  return <div>SpiderFoot UI — scaffold boot</div>;
}
```

Replace `webui/src/main.tsx` with:
```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

Delete the scaffold's default CSS files (`webui/src/App.css`, `webui/src/index.css`) — we'll use Mantine's CSS in Task 2.

- [ ] **Step 5: Create `webui/public/favicon.svg`**

Create a minimal SVG (a simple spider icon is cute but any recognizable mark works). For the plan: a circle with "SF" inside.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <circle cx="16" cy="16" r="14" fill="#339af0"/>
  <text x="16" y="21" text-anchor="middle" font-family="sans-serif"
        font-size="14" font-weight="bold" fill="white">SF</text>
</svg>
```

- [ ] **Step 6: Add `webui/.gitignore`**

```
node_modules/
dist/
test-results/
playwright-report/
*.log
```

- [ ] **Step 7: Add webui entries to repo-root `.gitignore`**

Append at the bottom of the existing `.gitignore`:
```
# Web UI
webui/node_modules/
webui/dist/
webui/test-results/
webui/playwright-report/
```

- [ ] **Step 8: Install deps and verify the dev server starts**

```bash
cd webui && npm install
cd webui && npm run dev
```
Expected: Vite prints `Local: http://localhost:5173/`. Open it in a browser; see "SpiderFoot UI — scaffold boot". Kill with Ctrl-C.

- [ ] **Step 9: Verify production build works**

```bash
cd webui && npm run build
ls webui/dist/
```
Expected: `dist/` contains `index.html`, `assets/` subdirectory with hashed JS + CSS bundles, `favicon.svg`.

- [ ] **Step 10: Commit**

```bash
git add webui .gitignore
git commit -m "$(cat <<'EOF'
webui: scaffold Vite + React + TypeScript foundation

Boots a minimal Vite dev server at :5173 with API proxy pointing
at CherryPy on :5001. Production build emits hashed assets under
base=/static/webui/ so CherryPy can serve them from a single
static mount later.

Scaffold only — no Mantine, no routing, no API layer yet. Just
proves the toolchain works end-to-end (dev server + build).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add Mantine + TanStack Query + theme

**Files:**
- Modify: `webui/package.json` (via npm install)
- Create: `webui/src/theme.ts`
- Modify: `webui/src/main.tsx`
- Modify: `webui/src/App.tsx`

- [ ] **Step 1: Install Mantine + TanStack Query**

```bash
cd webui && npm install @mantine/core @mantine/hooks @mantine/notifications @mantine/modals @tanstack/react-query react-router-dom
```

- [ ] **Step 2: Create `webui/src/theme.ts`**

```typescript
import { createTheme, MantineColorsTuple } from '@mantine/core';

// Primary color sampled from auth.ohdeere.se brand. Adjust if the
// auth server's palette changes.
const ohdeereBlue: MantineColorsTuple = [
  '#e7f5ff',
  '#d0ebff',
  '#a5d8ff',
  '#74c0fc',
  '#4dabf7',
  '#339af0',
  '#228be6',
  '#1c7ed6',
  '#1971c2',
  '#1864ab',
];

export const theme = createTheme({
  primaryColor: 'ohdeere',
  colors: {
    ohdeere: ohdeereBlue,
  },
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  defaultRadius: 'md',
  cursorType: 'pointer',
});
```

- [ ] **Step 3: Replace `webui/src/main.tsx`**

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { ModalsProvider } from '@mantine/modals';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

import App from './App';
import { theme } from './theme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      refetchInterval: 5_000,
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <QueryClientProvider client={queryClient}>
        <ModalsProvider>
          <Notifications />
          <App />
        </ModalsProvider>
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 4: Replace `webui/src/App.tsx`**

```tsx
import { AppShell, Title } from '@mantine/core';

export default function App() {
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header p="md">
        <Title order={3}>SpiderFoot</Title>
      </AppShell.Header>
      <AppShell.Main>
        <Title order={4}>Mantine boots</Title>
      </AppShell.Main>
    </AppShell>
  );
}
```

- [ ] **Step 5: Verify dev + build still work**

```bash
cd webui && npm run dev
```
Open `localhost:5173` — expect a Mantine-styled page with a blue header showing "SpiderFoot" and a body saying "Mantine boots". Ctrl-C to stop.

```bash
cd webui && npm run build
```
Expected: build succeeds; `dist/assets/` contains the Mantine CSS bundle (~200KB).

- [ ] **Step 6: Commit**

```bash
git add webui/package.json webui/package-lock.json webui/src/theme.ts webui/src/main.tsx webui/src/App.tsx
git commit -m "$(cat <<'EOF'
webui: wire Mantine + TanStack Query + theme

Adds Mantine (core, hooks, notifications, modals), TanStack Query
v5, and React Router. Theme pulls a primary-color palette sampled
from auth.ohdeere.se branding — single source later if a shared
token package shows up.

QueryClient config set to 5s staleTime + 5s refetchInterval so
running-scan data stays fresh without WebSockets.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Typed API layer + Vitest unit tests

**Files:**
- Create: `webui/src/types.ts`, `webui/src/api/client.ts`, `webui/src/api/scans.ts`, `webui/src/api/scans.test.ts`
- Modify: `webui/package.json` (add vitest deps)

- [ ] **Step 1: Install Vitest + testing deps**

```bash
cd webui && npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom @vitest/ui
```

- [ ] **Step 2: Add Vitest config to `webui/vite.config.ts`**

Update the `defineConfig({...})` to include a `test` section. Replace the file with:

```typescript
/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/webui/',
  server: {
    port: 5173,
    proxy: {
      '^/(?!static/webui/|@vite|src|node_modules).*': {
        target: 'http://127.0.0.1:5001',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
});
```

- [ ] **Step 3: Add `webui/src/test-setup.ts`**

```typescript
import '@testing-library/jest-dom';
```

- [ ] **Step 4: Add a `test` script to `webui/package.json`**

Edit `webui/package.json`. Under `"scripts"`, add:
```json
"test": "vitest"
```
So the full scripts block looks like:
```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test": "vitest"
}
```

- [ ] **Step 5: Create `webui/src/types.ts`**

```typescript
export type ScanStatus =
  | 'CREATED'
  | 'STARTING'
  | 'STARTED'
  | 'RUNNING'
  | 'ABORT-REQUESTED'
  | 'ABORTED'
  | 'FINISHED'
  | 'ERROR-FAILED';

export type Scan = {
  guid: string;
  name: string;
  target: string;
  createdAt: number;
  startedAt: number;
  endedAt: number;
  status: ScanStatus;
  eventCount: number;
};
```

- [ ] **Step 6: Create `webui/src/api/client.ts`**

```typescript
export class ApiError extends Error {
  constructor(
    public status: number,
    public body: string,
  ) {
    super(`API error ${status}: ${body.slice(0, 200)}`);
    this.name = 'ApiError';
  }
}

export async function fetchJson<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new ApiError(response.status, body);
  }
  return (await response.json()) as T;
}
```

- [ ] **Step 7: Create `webui/src/api/scans.ts`**

```typescript
import { fetchJson } from './client';
import type { Scan, ScanStatus } from '../types';

export async function listScans(): Promise<Scan[]> {
  const rows = await fetchJson<unknown[][]>('/scanlist');
  return rows.map((r) => ({
    guid: r[0] as string,
    name: r[1] as string,
    target: r[2] as string,
    createdAt: r[3] as number,
    startedAt: r[4] as number,
    endedAt: r[5] as number,
    status: r[6] as ScanStatus,
    eventCount: r[7] as number,
  }));
}

export async function deleteScan(guid: string): Promise<void> {
  await fetchJson(`/scandelete?id=${encodeURIComponent(guid)}`, {
    method: 'GET',  // CherryPy's /scandelete handler accepts GET
  });
}
```

- [ ] **Step 8: Create `webui/src/api/scans.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { listScans, deleteScan } from './scans';
import { ApiError } from './client';

describe('listScans', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps positional-tuple response to typed Scan objects', async () => {
    (globalThis.fetch as any).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['abc', 'test-scan', 'example.com', 1700000000, 1700000001,
            1700000100, 'FINISHED', 42],
        ]),
        { status: 200 },
      ),
    );
    const scans = await listScans();
    expect(scans).toEqual([
      {
        guid: 'abc',
        name: 'test-scan',
        target: 'example.com',
        createdAt: 1700000000,
        startedAt: 1700000001,
        endedAt: 1700000100,
        status: 'FINISHED',
        eventCount: 42,
      },
    ]);
  });

  it('returns empty array for empty response', async () => {
    (globalThis.fetch as any).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    const scans = await listScans();
    expect(scans).toEqual([]);
  });

  it('throws ApiError on non-2xx', async () => {
    (globalThis.fetch as any).mockResolvedValue(
      new Response('nope', { status: 500 }),
    );
    await expect(listScans()).rejects.toBeInstanceOf(ApiError);
  });
});

describe('deleteScan', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('hits /scandelete with the encoded guid', async () => {
    (globalThis.fetch as any).mockResolvedValue(
      new Response('null', { status: 200 }),
    );
    await deleteScan('abc/123');
    const url = (globalThis.fetch as any).mock.calls[0][0];
    expect(url).toBe('/scandelete?id=abc%2F123');
  });
});
```

- [ ] **Step 9: Run Vitest and verify the tests pass**

```bash
cd webui && npm test -- --run
```
Expected: 4 tests pass.

- [ ] **Step 10: Commit**

```bash
git add webui/
git commit -m "$(cat <<'EOF'
webui: typed API layer + Vitest unit tests

Scan type matches SpiderFoot's JSON /scanlist positional-tuple
response; listScans() hides that shape from components so switching
the backend response format later is a one-file edit. deleteScan()
uses GET to match CherryPy's /scandelete handler. ApiError class
wraps non-2xx responses for consistent error surfacing through
TanStack Query.

Four Vitest cases: tuple → typed-Scan mapping, empty-list, API-
error path, deleteScan URL encoding.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: ScanListPage component + smoke test

**Files:**
- Create: `webui/src/components/ScanStatusBadge.tsx`
- Create: `webui/src/pages/ScanListPage.tsx`, `webui/src/pages/ScanListPage.test.tsx`
- Create: `webui/src/router.tsx`
- Modify: `webui/src/App.tsx`

- [ ] **Step 1: Create `webui/src/components/ScanStatusBadge.tsx`**

```tsx
import { Badge } from '@mantine/core';
import type { ScanStatus } from '../types';

const STATUS_COLORS: Record<ScanStatus, string> = {
  CREATED: 'gray',
  STARTING: 'blue',
  STARTED: 'blue',
  RUNNING: 'blue',
  'ABORT-REQUESTED': 'orange',
  ABORTED: 'orange',
  FINISHED: 'green',
  'ERROR-FAILED': 'red',
};

export function ScanStatusBadge({ status }: { status: ScanStatus }) {
  return <Badge color={STATUS_COLORS[status] ?? 'gray'}>{status}</Badge>;
}
```

- [ ] **Step 2: Create `webui/src/pages/ScanListPage.tsx`**

```tsx
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionIcon,
  Alert,
  Anchor,
  Button,
  Group,
  Loader,
  Menu,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { listScans, deleteScan } from '../api/scans';
import { ScanStatusBadge } from '../components/ScanStatusBadge';
import type { Scan, ScanStatus } from '../types';

type FilterKey = 'all' | 'running' | 'finished' | 'aborted' | 'failed';

const FILTER_GROUPS: Record<FilterKey, ScanStatus[] | null> = {
  all: null,
  running: ['CREATED', 'STARTING', 'STARTED', 'RUNNING'],
  finished: ['FINISHED'],
  aborted: ['ABORT-REQUESTED', 'ABORTED'],
  failed: ['ERROR-FAILED'],
};

function matches(scan: Scan, filter: FilterKey): boolean {
  const statuses = FILTER_GROUPS[filter];
  return statuses === null || statuses.includes(scan.status);
}

function formatTime(unix: number): string {
  if (!unix) return '—';
  const delta = Date.now() / 1000 - unix;
  if (delta < 60) return 'just now';
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

export function ScanListPage() {
  const [filter, setFilter] = useState<FilterKey>('all');
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['scans'],
    queryFn: listScans,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteScan,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scans'] }),
  });

  const openDeleteConfirm = (scan: Scan) =>
    modals.openConfirmModal({
      title: 'Delete scan',
      children: (
        <Text size="sm">
          Delete scan <strong>{scan.name}</strong> (target {scan.target})? This
          cannot be undone.
        </Text>
      ),
      labels: { confirm: 'Delete', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(scan.guid),
    });

  if (query.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }

  if (query.isError) {
    return (
      <Alert color="red" title="Failed to load scans" mt="md">
        {(query.error as Error).message}
        <Group mt="sm">
          <Button size="xs" onClick={() => query.refetch()}>
            Retry
          </Button>
        </Group>
      </Alert>
    );
  }

  const filtered = (query.data ?? []).filter((s) => matches(s, filter));

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Scans</Title>
        <Button component="a" href="/newscan">
          + New Scan
        </Button>
      </Group>

      <SegmentedControl
        data={[
          { label: 'All', value: 'all' },
          { label: 'Running', value: 'running' },
          { label: 'Finished', value: 'finished' },
          { label: 'Aborted', value: 'aborted' },
          { label: 'Failed', value: 'failed' },
        ]}
        value={filter}
        onChange={(v) => setFilter(v as FilterKey)}
      />

      {filtered.length === 0 ? (
        <Text c="dimmed" ta="center" mt="xl">
          No scans{filter === 'all' ? ' yet' : ' match this filter'}.
        </Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Status</Table.Th>
              <Table.Th>Name</Table.Th>
              <Table.Th>Target</Table.Th>
              <Table.Th>Events</Table.Th>
              <Table.Th>Started</Table.Th>
              <Table.Th aria-label="Actions" />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map((scan) => (
              <Table.Tr key={scan.guid} data-testid={`scan-row-${scan.guid}`}>
                <Table.Td>
                  <ScanStatusBadge status={scan.status} />
                </Table.Td>
                <Table.Td>
                  <Anchor href={`/scaninfo?id=${scan.guid}`}>
                    {scan.name}
                  </Anchor>
                </Table.Td>
                <Table.Td>{scan.target}</Table.Td>
                <Table.Td>{scan.eventCount}</Table.Td>
                <Table.Td>{formatTime(scan.startedAt)}</Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>
                  <Menu shadow="md" width={200}>
                    <Menu.Target>
                      <ActionIcon
                        variant="subtle"
                        aria-label={`Actions for ${scan.name}`}
                      >
                        ⋮
                      </ActionIcon>
                    </Menu.Target>
                    <Menu.Dropdown>
                      <Menu.Item
                        component="a"
                        href={`/scaninfo?id=${scan.guid}`}
                      >
                        View
                      </Menu.Item>
                      <Menu.Item
                        color="red"
                        onClick={() => openDeleteConfirm(scan)}
                      >
                        Delete
                      </Menu.Item>
                    </Menu.Dropdown>
                  </Menu>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
```

- [ ] **Step 3: Create `webui/src/router.tsx`**

```tsx
import { createBrowserRouter } from 'react-router-dom';
import { ScanListPage } from './pages/ScanListPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <ScanListPage />,
  },
]);
```

- [ ] **Step 4: Replace `webui/src/App.tsx`**

```tsx
import { AppShell, Title } from '@mantine/core';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';

export default function App() {
  return (
    <AppShell header={{ height: 56 }} padding="md">
      <AppShell.Header p="md">
        <Title order={3}>SpiderFoot</Title>
      </AppShell.Header>
      <AppShell.Main>
        <RouterProvider router={router} />
      </AppShell.Main>
    </AppShell>
  );
}
```

- [ ] **Step 5: Create `webui/src/pages/ScanListPage.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { ScanListPage } from './ScanListPage';

describe('ScanListPage', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function renderPage() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <ModalsProvider>
            <ScanListPage />
          </ModalsProvider>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  it('renders the scan list when query resolves', async () => {
    (globalThis.fetch as any).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['abc', 'test', 'example.com',
            1700000000, 1700000001, 1700000100, 'FINISHED', 42],
        ]),
        { status: 200 },
      ),
    );
    renderPage();
    expect(await screen.findByText('test')).toBeInTheDocument();
    expect(await screen.findByText('example.com')).toBeInTheDocument();
    expect(await screen.findByText('FINISHED')).toBeInTheDocument();
  });

  it('renders empty state when no scans', async () => {
    (globalThis.fetch as any).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    renderPage();
    expect(await screen.findByText(/No scans yet/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run Vitest and confirm tests pass**

```bash
cd webui && npm test -- --run
```
Expected: 6 passed (4 from Task 3 + 2 new).

- [ ] **Step 7: Verify the page renders in the dev server**

```bash
python3 ./sf.py -l 127.0.0.1:5001 &
cd webui && npm run dev
```
Open `localhost:5173`. Expected: scan-list page with existing scans (if any are in the local SQLite DB) or the empty state. Ctrl-C both.

- [ ] **Step 8: Commit**

```bash
git add webui/
git commit -m "$(cat <<'EOF'
webui: ScanListPage — React replacement for Mako scanlist.tmpl

First migrated page. Mantine Table with per-row status badge,
target, event count, relative "started" timestamp, and a ⋮ menu
for view / delete. Delete goes through a Mantine confirm modal.
SegmentedControl filter (all / running / finished / aborted /
failed) narrows visible rows.

Link to the scan-detail page is a plain <a href="/scaninfo?id=...">
until /scaninfo migrates in a future milestone; browser does a full
page load and Mako renders the legacy detail page.

TanStack Query polls /scanlist every 5s so running scans update
live without WebSockets.

Two render smoke tests added (happy path + empty state).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: CherryPy integration — serve SPA, delete Mako scanlist

**Files:**
- Modify: `sfwebui.py` — add SPA static mount + route, delete `index()` handler that renders `scanlist.tmpl`
- Delete: `spiderfoot/templates/scanlist.tmpl`

- [ ] **Step 1: Read `sfwebui.py` around the `index()` method to understand what to replace**

```bash
grep -nE "def index\(|scanlist\.tmpl" sfwebui.py | head -5
```

Locate the `index()` method (currently around line 550-600 based on earlier snapshot) and its Mako template rendering of `scanlist.tmpl`.

- [ ] **Step 2: Modify `sfwebui.py` — add SPA module-level constants and static mount**

Add these near the top of the file (after imports, before the class definition):

```python
# Milestone 1: SPA-owned paths (the SPA's React Router handles them).
# Each future migrated page adds its path here; when a path is in this
# set, CherryPy serves the SPA's index.html rather than a Mako handler.
_SPA_ROUTES = {"/"}

# Absolute path to the built SPA bundle inside the Docker image.
# Vite emits ./webui/dist/ at repo root during build.
_SPA_DIST = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "webui", "dist"
)
```

Make sure `os` is already imported at the top (it likely is — verify before adding).

- [ ] **Step 3: Add a CherryPy app config entry that mounts `/static/webui/` as a static dir**

Find the `start_web_server` function (or equivalent startup code that calls `cherrypy.tree.mount(...)`). Add to its config dict:

```python
cherrypy_config = {
    # ... existing entries ...
    "/static/webui": {
        "tools.staticdir.on": True,
        "tools.staticdir.dir": _SPA_DIST,
        "tools.staticdir.index": "index.html",
    },
}
```

- [ ] **Step 4: Replace the `index()` method body**

Find the existing method (decorated with `@cherrypy.expose` right before `def index(`). Replace its body with SPA-index serving:

```python
@cherrypy.expose
def index(self, *args, **kwargs) -> str:
    """Serve the SPA shell for SPA-owned paths.

    Milestone 1: only '/' is SPA-owned. Future migrations add entries
    to _SPA_ROUTES and this handler serves index.html for each.
    """
    index_path = os.path.join(_SPA_DIST, "index.html")
    if not os.path.isfile(index_path):
        # Fall back to a plain HTML page if the SPA bundle is missing
        # (e.g. developer ran the backend without building the UI).
        return (
            "<html><body><h1>SpiderFoot</h1>"
            "<p>Web UI bundle not found at {}. Run "
            "<code>cd webui && npm run build</code> or use "
            "<code>npm run dev</code> on port 5173.</p>"
            "</body></html>"
        ).format(_SPA_DIST)
    with open(index_path, encoding="utf-8") as fh:
        return fh.read()
```

- [ ] **Step 5: Delete the `scanlist.tmpl` file**

```bash
git rm spiderfoot/templates/scanlist.tmpl
```

- [ ] **Step 6: Find any `Template(filename=".../scanlist.tmpl")` references or helper imports**

```bash
grep -nE "scanlist\.tmpl|scanlist_tmpl" sfwebui.py
```

If any references remain, remove them. Commonly there's a `Template(...)` variable assignment and usage in the original `index()` — both should be gone now.

- [ ] **Step 7: Test the backend in isolation**

```bash
python3 ./sf.py -l 127.0.0.1:5001 &
sleep 3
curl -s http://127.0.0.1:5001/ | head -10
kill %1
```

Expected: either the SPA's `index.html` content (if `webui/dist/` exists locally — you built it in Task 2 step 5) or the fallback HTML message. Both are acceptable.

- [ ] **Step 8: Run the full test suite**

```bash
./test/run 2>&1 | tail -5
```
Expected: 1460 passed + 35 skipped (unchanged — the Mako template deletion doesn't affect any Python tests because no pytest test imports scanlist.tmpl).

- [ ] **Step 9: Commit**

```bash
git add sfwebui.py
git rm spiderfoot/templates/scanlist.tmpl
git commit -m "$(cat <<'EOF'
webui: CherryPy integration — serve SPA at /, retire Mako scanlist

sfwebui.py mounts webui/dist/ at /static/webui/ as a CherryPy
staticdir; the index() handler serves webui/dist/index.html for
SPA-owned paths. Milestone 1 has one SPA route (/).

Graceful fallback: if the SPA bundle is missing at runtime (dev
without a build), index() returns a plain HTML page instructing
the user to run `npm run build` or the dev server. Keeps
local-dev-without-webui workable.

scanlist.tmpl deleted — its functionality is now in
webui/src/pages/ScanListPage.tsx.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Dockerfile — Node build stage

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Read the current `Dockerfile`**

```bash
cat Dockerfile
```

Identify the existing stages (there should be `FROM python:3.12-slim-bookworm AS build` and a final `FROM python:3.12-slim-bookworm` stage).

- [ ] **Step 2: Insert a new `ui-build` stage before the Python stages**

Edit `Dockerfile`. Add this new stage at the top of the file, before the existing `FROM python:3.12-slim-bookworm AS build` line:

```dockerfile
# Build the SPA. Node is only present during this stage — the final
# runtime image carries only the emitted dist/ assets.
FROM node:22-slim AS ui-build
WORKDIR /app
COPY webui/package.json webui/package-lock.json webui/
RUN cd webui && npm ci
COPY webui/ webui/
RUN cd webui && npm run build
```

- [ ] **Step 3: Add the SPA copy to the runtime stage**

Find the final runtime stage (the `FROM python:3.12-slim-bookworm` without a stage-name — the one that ends with `CMD`). After the existing `COPY . .` line, add:

```dockerfile
COPY --from=ui-build /app/webui/dist /home/spiderfoot/webui/dist
```

- [ ] **Step 4: Verify the Docker build**

```bash
docker build -t sf-webui-verify . 2>&1 | tail -20
```

Expected: build succeeds. The `ui-build` stage runs `npm ci` + `npm run build`, then the runtime stage copies `/app/webui/dist` → `/home/spiderfoot/webui/dist`.

If the build fails with a node version error, bump `node:22-slim` to the current Node LTS.

- [ ] **Step 5: Run the container and verify the SPA serves**

```bash
docker run --rm -d --name sf-webui-smoke -p 127.0.0.1:5994:5001 sf-webui-verify
sleep 6
curl -s http://127.0.0.1:5994/ | head -5
docker stop sf-webui-smoke
```

Expected: the first line of output is HTML with `<html>` or similar, and the content includes either SpiderFoot's SPA bundle markers (script tags referencing `/static/webui/assets/...`) or at minimum the SPA's `index.html` content.

- [ ] **Step 6: Clean up the verify image**

```bash
docker rmi sf-webui-verify
```

- [ ] **Step 7: Commit**

```bash
git add Dockerfile
git commit -m "$(cat <<'EOF'
Dockerfile: add Node ui-build stage for the SPA bundle

Runs npm ci + npm run build in a throw-away node:22-slim image,
then COPY --from=ui-build /app/webui/dist → runtime. Runtime image
carries no Node binaries — only the emitted static assets (~200KB
gzipped).

CherryPy's /static/webui/ static mount serves those assets in
production; the SPA's index() handler serves webui/dist/index.html
for SPA-owned routes.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Playwright E2E tests + seed fixture DB

**Files:**
- Create: `webui/tests/e2e/fixtures/seed_db.py`
- Create: `webui/tests/e2e/fixtures/.gitkeep` (ensures dir exists post-clone)
- Create: `webui/tests/e2e/scan-list.spec.ts`
- Create: `webui/tests/e2e/empty-state.spec.ts`
- Create: `webui/playwright.config.ts`
- Modify: `webui/package.json` — add Playwright dep + scripts
- Modify: `test/run` — add webui test steps

- [ ] **Step 1: Install Playwright**

```bash
cd webui && npm install -D @playwright/test
cd webui && npx playwright install --with-deps chromium
```

- [ ] **Step 2: Create `webui/playwright.config.ts`**

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,          // each test boots its own SpiderFoot
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
});
```

- [ ] **Step 3: Create `webui/tests/e2e/fixtures/seed_db.py`**

This Python script builds a pre-seeded SQLite DB for the E2E tests. Playwright tests invoke it via `playwright.config.ts`'s `webServer` block in step 4.

```python
#!/usr/bin/env python3
"""Seed a SpiderFoot SQLite DB with deterministic scans for Playwright E2E.

Usage:
    python3 seed_db.py <output-db-path> [--empty]

--empty produces a DB with zero scan rows (for the empty-state test).
"""
import os
import sys
import time
import uuid

# Allow the script to run from the repo root.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, REPO_ROOT)

from spiderfoot import SpiderFootDb


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: seed_db.py <output-db-path> [--empty]", file=sys.stderr)
        return 2
    db_path = sys.argv[1]
    empty = "--empty" in sys.argv[2:]
    if os.path.exists(db_path):
        os.remove(db_path)
    db = SpiderFootDb({"__database": db_path}, init=True)

    if empty:
        return 0

    now = int(time.time())
    scans = [
        (str(uuid.uuid4()), "monthly-recon", "spiderfoot.net",
         now - 7200, now - 7200, now - 3600, "FINISHED"),
        (str(uuid.uuid4()), "ongoing-1", "example.com",
         now - 300, now - 300, 0, "RUNNING"),
        (str(uuid.uuid4()), "failed-1", "bad.input",
         now - 86400, now - 86400, now - 86300, "ERROR-FAILED"),
        (str(uuid.uuid4()), "finished-2", "another.example.org",
         now - 172800, now - 172800, now - 172000, "FINISHED"),
        (str(uuid.uuid4()), "finished-3", "third.example.net",
         now - 259200, now - 259200, now - 259100, "FINISHED"),
    ]
    with db.dbhLock:
        for guid, name, target, created, started, ended, status in scans:
            db.dbh.execute(
                "INSERT INTO tbl_scan_instance (guid, name, seed_target, "
                "created, started, ended, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (guid, name, target, created, started, ended, status),
            )
        db.conn.commit()
    print(f"Seeded {len(scans)} scans into {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Update `webui/playwright.config.ts` with a webServer block**

Replace the whole file with:

```typescript
import { defineConfig, devices } from '@playwright/test';
import * as path from 'path';

const REPO_ROOT = path.resolve(__dirname, '..');
const FIXTURE_DIR = path.resolve(__dirname, 'tests/e2e/fixtures');
const SEED_SCRIPT = path.resolve(FIXTURE_DIR, 'seed_db.py');

const SPIDERFOOT_DATA = path.resolve(FIXTURE_DIR, 'spiderfoot-e2e');

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
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
    // Seed the fixture DB each run (cleans previous run's state), then
    // boot SpiderFoot pointing at the seeded DATA dir.
    command:
      `rm -rf ${SPIDERFOOT_DATA} && ` +
      `mkdir -p ${SPIDERFOOT_DATA} && ` +
      `python3 ${SEED_SCRIPT} ${SPIDERFOOT_DATA}/spiderfoot.db && ` +
      `SPIDERFOOT_DATA=${SPIDERFOOT_DATA} ` +
      `python3 ${REPO_ROOT}/sf.py -l 127.0.0.1:5990`,
    url: 'http://127.0.0.1:5990/',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
```

- [ ] **Step 5: Create `webui/tests/e2e/scan-list.spec.ts`**

```typescript
import { test, expect } from '@playwright/test';

test.describe('Scan list', () => {
  test('renders all seeded scans with correct statuses', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Scans' })).toBeVisible();

    await expect(page.getByText('monthly-recon')).toBeVisible();
    await expect(page.getByText('ongoing-1')).toBeVisible();
    await expect(page.getByText('failed-1')).toBeVisible();
    await expect(page.getByText('finished-2')).toBeVisible();
    await expect(page.getByText('finished-3')).toBeVisible();

    // Two distinct FINISHED badges
    const finishedBadges = page.locator('text=FINISHED');
    await expect(finishedBadges).toHaveCount(3);
  });

  test('filter narrows to finished scans only', async ({ page }) => {
    await page.goto('/');
    await page.getByText('Finished', { exact: true }).click();

    await expect(page.getByText('monthly-recon')).toBeVisible();
    await expect(page.getByText('finished-2')).toBeVisible();
    await expect(page.getByText('finished-3')).toBeVisible();
    await expect(page.getByText('ongoing-1')).not.toBeVisible();
    await expect(page.getByText('failed-1')).not.toBeVisible();
  });

  test('delete flow removes a scan after confirmation', async ({ page }) => {
    await page.goto('/');
    const rowName = 'failed-1';
    await expect(page.getByText(rowName)).toBeVisible();

    // Find the failed-1 row's action menu and click Delete.
    await page
      .getByRole('button', { name: new RegExp(`Actions for ${rowName}`) })
      .click();
    await page.getByRole('menuitem', { name: 'Delete' }).click();

    // Confirm in the modal.
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByRole('button', { name: 'Delete' }).click();

    // Row should disappear.
    await expect(page.getByText(rowName)).not.toBeVisible();
  });
});
```

- [ ] **Step 6: Create `webui/tests/e2e/empty-state.spec.ts`**

This test uses a different fixture DB (empty) by overriding the DB seed. Simplest approach: use a separate Playwright project with its own webServer config. Add this spec file:

```typescript
import { test, expect } from '@playwright/test';
import { spawnSync } from 'node:child_process';
import * as path from 'path';

const FIXTURE_DIR = path.resolve(__dirname, 'fixtures');
const SEED_SCRIPT = path.resolve(FIXTURE_DIR, 'seed_db.py');
const DATA_DIR = path.resolve(FIXTURE_DIR, 'spiderfoot-e2e');
const DB_PATH = path.resolve(DATA_DIR, 'spiderfoot.db');

test.describe('Empty state', () => {
  test.beforeAll(async () => {
    // Re-seed the fixture DB as empty, then make the running sf.py
    // pick it up by sending it a restart-relevant request? Simpler:
    // just delete all rows and let the running server serve the
    // empty response.
    const result = spawnSync('python3', [
      '-c',
      `import sys; sys.path.insert(0, "${path.resolve(__dirname, '..', '..', '..')}"); ` +
      `from spiderfoot import SpiderFootDb; ` +
      `db = SpiderFootDb({"__database": "${DB_PATH}"}); ` +
      `with db.dbhLock: db.dbh.execute("DELETE FROM tbl_scan_instance"); db.conn.commit()`,
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
```

(Note: empty-state test runs AFTER the other scan-list tests. The last test — delete — removes `failed-1` but the other 4 scans remain. We explicitly empty the DB in `beforeAll`. This means test ordering matters; Playwright runs specs in filename order by default so `empty-state.spec.ts` runs after `scan-list.spec.ts` alphabetically.)

- [ ] **Step 7: Add Playwright scripts to `webui/package.json`**

Update the `"scripts"` block to:
```json
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test": "vitest",
  "test:e2e": "playwright test"
}
```

- [ ] **Step 8: Run the Playwright suite locally**

```bash
cd webui && npm run test:e2e
```

Expected: the `webServer` block seeds the DB, starts SpiderFoot on :5990, runs the 4 tests, all pass. If any fail, inspect the trace under `webui/test-results/`.

- [ ] **Step 9: Modify `test/run` to include webui tests**

Read `test/run`:
```bash
cat test/run
```

Replace its contents with:

```bash
#!/bin/bash
# Run unit and integration tests (excluding module integration tests).
# These same tests are run on all pull requests automatically.
#
# Must be run from SpiderFoot root directory; ie:
# ./test/run

set -e

if [ -d webui ]; then
    echo "Running webui build + tests ..."
    (
        cd webui
        npm ci
        npm run build
        npm test -- --run
        # Playwright: install Chromium only if missing, then run.
        if ! npx playwright --version >/dev/null 2>&1; then
            echo "Playwright not installed — install with: cd webui && npx playwright install --with-deps chromium"
            exit 1
        fi
        npm run test:e2e
    )
fi

echo Running flake8 ...
time python3 -m flake8 . --count --show-source --statistics

echo Running pytest ...
time python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ --durations=5 --cov-report html --cov=. .
```

- [ ] **Step 10: Run the full `./test/run` end-to-end**

```bash
./test/run 2>&1 | tail -20
```

Expected: webui build + Vitest (6 passed) + Playwright (4 passed) + flake8 clean + pytest 1460 passed + 35 skipped.

- [ ] **Step 11: Commit**

```bash
git add webui/playwright.config.ts webui/tests/ webui/package.json webui/package-lock.json test/run
git commit -m "$(cat <<'EOF'
webui: Playwright E2E tests + test/run integration

Four Playwright Chromium tests: scan-list renders all seeded scans
with correct status badges, status filter narrows to FINISHED,
delete flow removes a scan via the ⋮ menu + confirm modal, and
empty-state placeholder shows when no scans exist.

Fixture DB is seeded by webui/tests/e2e/fixtures/seed_db.py which
imports SpiderFootDb and inserts five deterministic scan rows.
playwright.config.ts's webServer block rebuilds the DB each run
and boots sf.py on :5990.

test/run grows a webui block at the top: npm ci, npm run build,
npm test (Vitest), npm run test:e2e (Playwright). Runs before
flake8/pytest. Keeps all verification under one entry point.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Docs refresh + final verification

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/BACKLOG.md`

- [ ] **Step 1: Add a "Web UI" section to `CLAUDE.md`**

Add this section immediately before the existing `## Conventions to follow` section:

```markdown
## Web UI

SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestone 1 (2026-04-20) migrated the scan-list page (`/`); all other Mako pages (`/newscan`, `/scaninfo`, `/opts`, etc.) remain unchanged and reachable.

**SPA stack:** Vite + React 19 + TypeScript + TanStack Query + Mantine + React Router. Vitest for unit tests, Playwright for E2E.

**Dev workflow:**
1. `python3 ./sf.py -l 127.0.0.1:5001` — CherryPy backend + legacy pages.
2. `cd webui && npm run dev` — Vite dev server on `:5173` with hot reload; proxies API calls to CherryPy.
3. Open `http://localhost:5173` in the browser.

**Production build:** `cd webui && npm run build` outputs `webui/dist/`; the Docker image's `ui-build` stage does this automatically. CherryPy serves the built assets from `/static/webui/` and the SPA's `index.html` for any SPA-owned route (list in `_SPA_ROUTES` in `sfwebui.py`).

**Adding a migrated page** (reference for future milestones):
1. Build the component in `webui/src/pages/<Foo>Page.tsx`.
2. Add its route to `webui/src/router.tsx`.
3. Add the path to `_SPA_ROUTES` in `sfwebui.py`.
4. Delete the old Mako template + `@cherrypy.expose` handler.
5. Add a Vitest render smoke test + a Playwright E2E spec.
6. Remove the corresponding Robot Framework acceptance test if one exists.
```

- [ ] **Step 2: Update `docs/superpowers/BACKLOG.md`**

Find the "UI modernization" discussion area (if it exists, or add a new section). Add:

```markdown
### UI modernization — page-by-page migration

**Foundation shipped:** milestone 1 (2026-04-20) — scan list page + full toolchain (Vite + React + Mantine + Vitest + Playwright). See `docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md`.

**Remaining Mako pages to migrate** (each its own spec):
- `/newscan` (`newscan.tmpl`, 116 lines) — scan creation form + module picker. Small.
- `/scaninfo?id=<guid>` (`scaninfo.tmpl`, 905 lines) — the beast. Has tabs for events, correlations, graph, log. Probably needs sub-milestones.
- `/opts` (`opts.tmpl`, 199 lines) — settings / API keys / global config.
- `/error` — tiny error page; can ride with the next migration.

**Retirements triggered by each migration:**
- Delete the Mako template + CherryPy handler.
- Remove the corresponding Robot Framework acceptance test if any.
- Add the path to `_SPA_ROUTES` in `sfwebui.py`.
- Add Playwright coverage for the new page.
```

- [ ] **Step 3: Final verification run**

```bash
./test/run 2>&1 | tail -10
```

Expected: webui build + Vitest (6 passed) + Playwright (4 passed) + flake8 clean + pytest 1460 passed + 35 skipped.

- [ ] **Step 4: Live browser smoke test**

```bash
python3 ./sf.py -l 127.0.0.1:5001 &
SF_PID=$!
sleep 3
# Expect SPA shell HTML served at /
curl -s http://127.0.0.1:5001/ | head -5
kill $SF_PID
```

Expected: HTML content that includes either SPA-bundle script tags (if you had a prior `npm run build`) or the fallback "SPA bundle missing" message. Both are acceptable for this check.

- [ ] **Step 5: Commit docs**

```bash
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — milestone 1 Web UI

Adds a "Web UI" section to CLAUDE.md describing the SPA stack, dev
workflow, and the recipe for adding each subsequent migrated page.
Updates BACKLOG.md to reflect milestone 1 as shipped and enumerates
the remaining Mako pages that still need migration: /newscan,
/scaninfo, /opts, /error.

Each remaining page gets its own spec + plan cycle. Scaninfo is
the big one at 905 lines of Mako and likely needs sub-milestones
by tab.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Report completion**

Final summary for the user:
- 8 commits landed (scaffold → Mantine → API → ScanListPage → CherryPy → Dockerfile → Playwright → docs).
- `webui/` subdirectory established with React + TypeScript + Mantine + TanStack Query + Vitest + Playwright.
- Scan-list page live at `/`; Mako `scanlist.tmpl` retired.
- `./test/run` runs the SPA build + tests before flake8 + pytest.
- Docker image bundles the built assets with no runtime Node dependency.
- Follow-up: the remaining Mako pages (`/newscan`, `/scaninfo`, `/opts`, `/error`) each get their own spec → plan → implementation cycle.
