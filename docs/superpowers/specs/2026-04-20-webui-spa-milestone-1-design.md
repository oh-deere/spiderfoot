# Web UI lift — milestone 1 (Scan List page)

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Start replacing SpiderFoot's CherryPy + Mako + jQuery + Bootstrap 3 UI with a modern React SPA, **one page at a time**. Milestone 1 migrates the scan list (`/` root page) and establishes the full toolchain: Vite + React + TypeScript + TanStack Query + Mantine + Vitest + Playwright, served from a new `webui/` subdirectory of the repo.

The existing Mako-rendered `scanlist.tmpl` is retired as part of this milestone. Every other Mako page (scan-detail, new-scan, opts, etc.) continues to work unchanged — the new SPA takes over only the `/` root path.

Architecture decisions already settled:
- Same repo, `webui/` subdirectory (not a separate repo).
- React + TypeScript + Vite + TanStack Query + Mantine.
- Theme (colors, typography) mirrored from `auth.ohdeere.se` login page for OhDeere stack consistency.
- CherryPy stays; SPA consumes existing `@cherrypy.tools.json_out()` JSON endpoints.
- Page-by-page migration: each SPA-owned path is explicit in CherryPy routing, falls through to Mako for the rest.

## Non-goals

- **Not** migrating other Mako pages (scan-detail, new-scan, opts). Each is its own spec later.
- **Not** replacing CherryPy. It stays as the HTTP server, session store, module orchestrator, and static-file host for `webui/dist/`.
- **Not** integrating with `auth.ohdeere.se` OIDC. The SPA reuses CherryPy's existing session auth. OIDC integration gets its own spec when we're ready.
- **Not** building a shared SpiderFoot component library separate from Mantine. Custom components (status badges, scan-row menu) live in `webui/src/components/` and stay local.
- **Not** adding a backend-for-frontend layer. SPA calls CherryPy JSON endpoints directly.
- **Not** introducing Postgres. Storage backend is orthogonal; can switch later without touching the SPA.
- **Not** adding new scan-list functionality beyond what the Mako page already has. Feature parity first; enhancements (search, sorting, bulk actions, real-time updates via WebSocket) get their own specs.
- **Not** retiring Robot Framework acceptance tests. They still cover unmigrated Mako pages. Retire each Robot test when its page migrates.

## Design

### File structure

```
webui/                                    # new subdirectory at repo root
├── package.json
├── tsconfig.json
├── vite.config.ts
├── playwright.config.ts
├── index.html
├── src/
│   ├── main.tsx                          # React entry
│   ├── theme.ts                          # Mantine theme — colors from auth.ohdeere.se
│   ├── router.tsx                        # React Router config
│   ├── api/
│   │   ├── client.ts                     # fetch wrapper, ApiError class
│   │   └── scans.ts                      # listScans(), deleteScan()
│   ├── components/
│   │   └── ScanStatusBadge.tsx           # status pill (FINISHED / RUNNING / ABORTED / ...)
│   ├── pages/
│   │   └── ScanListPage.tsx              # the page itself
│   ├── types.ts                          # Scan, ScanStatus types
│   ├── main.test.tsx                     # smoke test for renders
│   └── api/scans.test.ts                 # API-layer mapping tests
├── tests/
│   └── e2e/
│       ├── scan-list.spec.ts             # 4 Playwright tests
│       └── fixtures/
│           └── seed-db.py                # builds test/fixtures/spiderfoot.e2e.db
├── public/
│   └── favicon.svg
└── dist/                                 # Vite build output — gitignored
```

Additional files touched at repo root:
- `Dockerfile` — new Node build stage producing `webui/dist/`.
- `sfwebui.py` — add SPA static-file mount, add routing for `/` to serve SPA, delete `index()` handler that renders `scanlist.tmpl`.
- `spiderfoot/templates/scanlist.tmpl` — deleted.
- `test/run` — add Node build + Vitest + Playwright steps before the final pytest run.
- `.gitignore` — add `webui/node_modules/`, `webui/dist/`, `webui/test-results/`, `webui/playwright-report/`.

### Build & serve flow

**Development (two processes):**
- `python3 ./sf.py -l 127.0.0.1:5001` — CherryPy serves legacy pages and JSON endpoints.
- `cd webui && npm run dev` — Vite on `:5173` with hot reload. `vite.config.ts` proxies all non-asset paths to `:5001`, so API calls Just Work.
- Developer opens `localhost:5173` to see the new UI.

**Production (single process):**
- `npm run build` in `webui/` produces `webui/dist/` (hashed JS + CSS + index.html).
- Docker build copies `webui/dist/` into the final Python image.
- `sfwebui.py` mounts `webui/dist/` as CherryPy static root; configures `/` to serve `webui/dist/index.html`; adds SPA routes (only `/` for milestone 1) to a passthrough handler that serves `index.html` so React Router can handle client-side routing.
- Single Docker image serves everything at `:5001`.

**Dockerfile changes** (append to existing multi-stage build):

```dockerfile
# New stage: build the SPA
FROM node:22-slim AS ui-build
WORKDIR /app
COPY webui/package*.json webui/
RUN cd webui && npm ci
COPY webui webui
RUN cd webui && npm run build

# Existing runtime stage gets:
COPY --from=ui-build /app/webui/dist /home/spiderfoot/webui/dist
```

Node is not present in the runtime image — only the built static assets. Image size delta: ~200KB gzipped (JS + CSS + HTML).

### CherryPy integration (`sfwebui.py`)

Add a module-level constant listing the SPA-owned paths:
```python
_SPA_ROUTES = {"/"}   # milestone 1: just the root. Each migrated page adds its path here.
```

Add a CherryPy handler that serves `webui/dist/index.html` for any SPA-owned path, and mount `webui/dist/` as the static root under a non-conflicting URL prefix (e.g. `/static/webui/`). Vite's `base` config targets that prefix so hashed asset URLs (`/static/webui/assets/index-abc123.js`) resolve correctly.

The existing `index()` method (the CherryPy handler that currently serves `scanlist.tmpl`) is deleted. Its `/` route is claimed by the SPA handler.

### Scan List page design

**Page layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  SpiderFoot · Scans                          [+ New Scan]   │
├─────────────────────────────────────────────────────────────┤
│  [filter: all | running | finished | aborted | failed]      │
├─────────────────────────────────────────────────────────────┤
│  Status   Name         Target           Events   Started ⋮ │
│  ───────────────────────────────────────────────────────── │
│  ✅  FIN   monthly      spiderfoot.net    142    2h ago  ⋮ │
│  ▶  RUN   ongoing-1    example.com        47    5m ago  ⋮ │
│  ⚠  ERR   failed-1     bad.input           0    1d ago  ⋮ │
└─────────────────────────────────────────────────────────────┘
```

Mantine components: `AppShell` (header + main), `Table` (scan rows), `Badge` (status), `SegmentedControl` (status filter), `ActionIcon` + `Menu` (per-row ⋮), `Modal` (delete confirm), `Button` ("+ New Scan" — links to legacy `/newscan` until that page is migrated).

**Clicking a scan row** navigates to legacy `/scaninfo?id=<guid>` via a full-page link (not React Router, since that path isn't SPA-owned yet). When scan-detail migrates in a future milestone, the same link becomes a React Router link automatically.

### Typed API layer

The current CherryPy `/scanlist` endpoint returns a JSON array of positional tuples. The SPA wraps this in a typed layer so components never touch the positional shape:

```typescript
// webui/src/types.ts
export type ScanStatus =
  | "CREATED" | "STARTING" | "STARTED" | "RUNNING"
  | "ABORT-REQUESTED" | "ABORTED" | "FINISHED" | "ERROR-FAILED";

export type Scan = {
  guid: string;
  name: string;
  target: string;
  createdAt: number;    // unix seconds
  startedAt: number;
  endedAt: number;
  status: ScanStatus;
  eventCount: number;
};

// webui/src/api/scans.ts
import { fetchJson } from "./client";

export async function listScans(): Promise<Scan[]> {
  const rows = await fetchJson<unknown[][]>("/scanlist");
  return rows.map(r => ({
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
  await fetchJson(`/scandelete?id=${encodeURIComponent(guid)}`, { method: "DELETE" });
}
```

The `fetchJson` wrapper throws a typed `ApiError(status, body)` on non-2xx; components catch it via TanStack Query's error surface and render a Mantine `Alert`.

**TanStack Query config** in `main.tsx`:
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, refetchInterval: 5_000 },  // 5s polling for running scans
  },
});
```

5-second polling covers milestone 1. WebSocket / server-sent events for real-time scan progress is a future enhancement.

### Theme

`webui/src/theme.ts` creates a Mantine theme with primary/secondary colors, font family, and border-radius settings pulled from the current OhDeere auth-server login page branding (eye-dropped at design time). Lives as a hand-written constant for now; a later spec can pull from a shared design-token package if OhDeere introduces one.

### Error handling

| Condition | Behaviour |
|---|---|
| API returns 401 | Full-page reload. CherryPy's login redirect handles the rest. |
| API returns 5xx or network error | `ApiError` thrown, TanStack Query surfaces it, page shows a Mantine `Alert` with "Retry" button that calls `refetch()`. |
| `webui/dist/` missing at CherryPy startup | Log a `WARNING`; legacy Mako `/` handler remains callable as a fallback (the delete of `index()` is the last step in the migration commit, so this only happens if Docker build skipped the Node stage). |
| Vite dev server crashes | Developer sees browser connection error. `npm run dev` restart fixes it. |

### Testing

**Three layers:**

1. **Vitest unit tests** in `webui/src/**/*.test.{ts,tsx}`:
   - API layer: `scans.test.ts` verifies the positional-tuple → typed-Scan mapping.
   - Page smoke test: `ScanListPage.test.tsx` renders with a mocked TanStack Query result, asserts the table is present.
   - ~5 tests total for milestone 1.

2. **Playwright E2E tests** in `webui/tests/e2e/scan-list.spec.ts`:
   - **Setup:** `playwright.config.ts` declares a `webServer` that runs `python3 ./sf.py -l 127.0.0.1:5990` with `SPIDERFOOT_DATA=./test/fixtures/spiderfoot-e2e` pointing at a pre-seeded SQLite DB. Fixture DB is built once by `webui/tests/e2e/fixtures/seed-db.py` committed to the repo (deterministic scan data — 3 FINISHED, 1 RUNNING, 1 ERROR-FAILED, 1 empty for the empty-state test).
   - Playwright installs Chromium only (`npx playwright install --with-deps chromium`), headless in CI, headed locally via `--headed`.
   - **4 tests for milestone 1:**
     1. Scan list renders: navigate to `/`, assert all 5 fixture scans shown, correct status badges.
     2. Status filter narrows the list: click "Finished" — only 3 FINISHED scans shown.
     3. Delete flow: row menu → Delete → confirm modal → OK → row disappears, confirmed via `listScans()` count drop.
     4. Empty state: with empty fixture DB (separate playwright project config), "No scans yet" placeholder renders.

3. **Robot Framework acceptance tests** (existing `test/acceptance/`): unchanged. They still cover the Mako pages that stay after this milestone.

### CI integration

`./test/run` grows three steps before the final pytest:

```bash
# (webui block — new)
if [ -d webui ]; then
    cd webui
    npm ci
    npm run build          # Vite production build
    npm test -- --run      # Vitest
    npx playwright install --with-deps chromium
    npx playwright test    # E2E against real SpiderFoot
    cd ..
fi

# (existing pytest block unchanged)
```

Total CI time delta: ~30-60s for npm install + build + Vitest + Chromium install + ~4 Playwright tests.

### Developer workflow

First-time setup:
```bash
cd webui && npm install
cd webui && npx playwright install --with-deps chromium
```

Per-session dev:
```bash
# Terminal 1
python3 ./sf.py -l 127.0.0.1:5001

# Terminal 2
cd webui && npm run dev

# Browser: http://localhost:5173
```

Pre-commit:
```bash
./test/run
```

Adding a future page (reference for later migrations):
1. Build the React component in `webui/src/pages/FooPage.tsx`.
2. Add the route to `webui/src/router.tsx`.
3. Add the path to `_SPA_ROUTES` in `sfwebui.py`.
4. Delete the old `@cherrypy.expose` handler and its Mako template.
5. Add Vitest render smoke test + Playwright spec.
6. Delete the corresponding Robot Framework acceptance test if one exists.

## Definition of done (milestone 1)

1. Running `python3 ./sf.py -l 127.0.0.1:5001` + `cd webui && npm run dev` lets a developer browse the new scan list at `:5173`.
2. `docker build -t sf-webui-verify . && docker run -p 5001:5001 sf-webui-verify` — scan list accessible at `localhost:5001/`, fully functional.
3. Feature parity with the old Mako scan list: shows all scans, status badges, target, event count, start/end times.
4. Status filter (all / running / finished / aborted / failed) narrows the list.
5. Per-row ⋮ menu with View (navigates to legacy `/scaninfo`) and Delete (confirmation modal → removes scan).
6. `./test/run` green including Vitest + Playwright + existing pytest suite.
7. Old `scanlist.tmpl` deleted; its Mako handler in `sfwebui.py` removed.
8. Robot Framework acceptance tests still pass for the unmigrated Mako pages.

## Rollout

Single-branch, multi-commit work. Suggested commit order:
1. **Scaffold `webui/` with Vite + React + TS** (empty app, "hello world", package.json, tsconfig, vite.config).
2. **Add Mantine + TanStack Query + theme** (`main.tsx`, `theme.ts`, `QueryClient`).
3. **Add typed API layer** (`api/client.ts`, `api/scans.ts`, `types.ts`) + Vitest unit tests.
4. **Add ScanListPage component + smoke test**.
5. **CherryPy integration**: `sfwebui.py` SPA routing + static mount; delete old `index()` handler + `scanlist.tmpl`.
6. **Dockerfile** Node build stage + `COPY --from=ui-build`.
7. **`./test/run` step additions** for webui build + Vitest + Playwright.
8. **Playwright fixture DB seed script** (`webui/tests/e2e/fixtures/seed-db.py`) + the 4 E2E tests.
9. **Docs refresh**: `CLAUDE.md` gets a "Web UI" section pointing at `webui/`, BACKLOG.md gets the remaining page-migration items listed.

Each commit stands on its own (suite green after each).

## Follow-ups enabled

- Every subsequent page migration is ~1/5 the scope of milestone 1 (no scaffolding, no design system, no Dockerfile changes — just component + route + API wrapper + tests).
- The `/scaninfo` page is the biggest remaining piece (905-line Mako template today). Its migration will likely need splitting into sub-milestones by tab (events tab, correlations tab, graph tab, log tab).
- **Real-time scan progress**: once comfortable with the SPA, adding a WebSocket endpoint on CherryPy that pushes scan-event updates means the scan-detail page can live-update instead of polling.
- **Auth integration with `auth.ohdeere.se`**: separate spec. Remove CherryPy session auth, redirect to OIDC flow, store JWT in httpOnly cookie.
- **Design system extraction**: if OhDeere ever creates a shared React component library, pull the theme and reusable components into `@ohdeere/ui` and import from both this SPA and others.
- **Retire Robot Framework**: once every Mako page is migrated, retire `test/acceptance/` in favour of Playwright-only.
