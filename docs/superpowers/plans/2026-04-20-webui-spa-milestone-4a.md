# Web UI SPA — Milestone 4a (`/scaninfo` shell + Status/Info/Log) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `/scaninfo` onto the SPA with a tab shell + three working tabs (Status, Info, Log) + placeholders for the remaining three (Browse, Correlations, Graph) that link to a renamed legacy handler at `/scaninfo-legacy`.

**Architecture:** 6 tasks. Backend rename lands first, then frontend work (types + API, shell + placeholder, three tab bodies, router + Playwright), docs close out. No new Python endpoints — the JSON surface already exists.

**Tech Stack:** Python 3.12 + CherryPy (unchanged), React 19 + Mantine 9 + TanStack Query 5 + React Router 7 + Vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-4a-design.md`.

---

## File Structure

### Backend (Python)
- **Modify** `sfwebui.py` — rename current `scaninfo()` to `scaninfo_legacy()` at route `/scaninfo-legacy`; add a new `scaninfo()` returning `self._serve_spa_shell()`; extend `_SPA_ROUTES`.
- **Modify** `test/integration/test_sfwebui.py` — update or relocate `test_scaninfo_unknown_scan_id_returns_error` to target the legacy URL; add `test_scaninfo_returns_spa_shell` asserting the new SPA behavior.
- **Modify** `test/unit/test_spiderfootwebui.py` — update the `test_scaninfo*` unit tests to test either the legacy method or the new SPA-shell handler, whichever applies.

### Frontend (React)
- **Create** `webui/src/api/scaninfo.ts`, `webui/src/api/scaninfo.test.ts`.
- **Create** `webui/src/pages/ScanInfoPage.tsx`, `webui/src/pages/ScanInfoPage.test.tsx`.
- **Create** `webui/src/pages/scaninfo/PlaceholderTab.tsx`, `webui/src/pages/scaninfo/StatusTab.tsx`, `webui/src/pages/scaninfo/InfoTab.tsx`, `webui/src/pages/scaninfo/LogTab.tsx`.
- **Modify** `webui/src/types.ts` — add `ScanStatusPayload`, `ScanSummaryRow`, `ScanOptsPayload`, `ScanLogEntry`.
- **Modify** `webui/src/router.tsx` — add `/scaninfo` route.

### E2E
- **Create** `webui/tests/e2e/05-scaninfo.spec.ts`.

### Docs
- **Modify** `CLAUDE.md` — Web UI section updated for M4a.
- **Modify** `docs/superpowers/BACKLOG.md` — mark M4a shipped.

---

## Context for the implementer

- **Branch:** commit directly on `master`. HEAD is at a5998b81 (this milestone's spec commit).
- **Baseline:** 43 Vitest + 9 Playwright + flake8 clean + 1464 pytest + 34 skipped.
- **SPA-shell helper:** `sfwebui.py` already has `_serve_spa_shell()` + `_SPA_ROUTES = {"/", "/newscan", "/opts"}`. This milestone adds `/scaninfo` to the set.
- **Existing JSON endpoints — no changes needed:**
  - `GET /scanstatus?id=<guid>` → `[name, target, created, started, ended, status, riskmatrix]` (empty list if not found).
  - `GET /scansummary?id=<guid>&by=type` → `[[type_id, type_label, last_seen, count, unique_count, scan_status], ...]`.
  - `GET /scanopts?id=<guid>` → `{meta, config, configdesc}` dict. Frozen scan config.
  - `GET /scanlog?id=<guid>&limit=500` → `[[generated_ms, component, level, message, hash], ...]`.
  - `GET /scanexportlogs?id=<guid>` → Excel file (plain download).
  - `GET /stopscan?id=<guid>` → JSON. Empty string on success; `jsonify_error` on failure.
- **ScanListPage "View" action** already links to `/scaninfo?id=<guid>`. After this milestone that URL serves the SPA; no scan-list change needed.
- **`/newscan` success redirect** already lands at `/scaninfo?id=<new-guid>` — will now render the SPA Status tab.
- **Mantine v9:** `Tabs`, `Alert`, `Anchor`, `Badge`, `Button`, `Code`, `Accordion`, `SimpleGrid`, `Table`, `Loader`, `Group`, `Stack`, `Title`.
- **Back link:** `<Anchor href="/">Scans</Anchor>` = full reload (matches milestone-2 newscan → scaninfo legacy-anchor convention).
- **`isRunning` helper** already exists semantically in `ScanListPage.tsx`'s `FILTER_GROUPS.running`. The new helper lives in `types.ts` (or a new `webui/src/utils/scanStatus.ts`) and is a simple enum check.
- **CSRF:** no token required for any `/scaninfo` endpoint; all are GET.
- **Tabs order:** match the Mako template — `Status | Correlations | Browse | Graph | Info | Log`. Placeholder tabs are `correlations`, `browse`, `graph`. Default active tab is `status`.

---

## Task 1: Backend — rename `scaninfo()` + add SPA-shell handler + pytest

**Files:**
- Modify: `sfwebui.py` — handler rename + new handler + `_SPA_ROUTES`.
- Modify: `test/integration/test_sfwebui.py` — two adjustments.
- Modify: `test/unit/test_spiderfootwebui.py` — one adjustment.

### Step 1: Locate the current `scaninfo()` method

```bash
grep -nE "def scaninfo\(|def scaninfo_" /Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py
```

You'll find the current method (renders `scaninfo.tmpl` via Mako). Keep the body, change the name.

### Step 2: Rename `scaninfo` → `scaninfo_legacy` and add new `scaninfo`

Find the existing method:

```python
@cherrypy.expose
def scaninfo(self: 'SpiderFootWebUi', id: str) -> str:
    """Information about a selected scan.
    ...
    """
    # current Mako-rendering body
    ...
```

Rename it in place to `scaninfo_legacy` and update the docstring:

```python
@cherrypy.expose
def scaninfo_legacy(self: 'SpiderFootWebUi', id: str) -> str:
    """Legacy Mako-rendered scan-detail page.

    Temporarily retained during the SPA migration of /scaninfo.
    Browse/Correlations/Graph tabs on the new SPA page link here
    for functional fallback. Retired in milestone 4c alongside
    scaninfo.tmpl and viz.js.

    Args:
        id (str): scan id

    Returns:
        str: scan info page HTML
    """
    # existing body unchanged
```

Immediately above it (or at a sensible spot elsewhere in the class — match the file's ordering convention), add the new SPA-shell handler:

```python
@cherrypy.expose
def scaninfo(self: 'SpiderFootWebUi', id: str = None) -> str:
    """Serve the SPA shell at /scaninfo.

    Milestone 4a moved the scan-detail page into the SPA. The SPA
    reads the `id` query parameter via React Router's useSearchParams.

    Returns:
        str: SPA shell HTML.
    """
    return self._serve_spa_shell()
```

Note: CherryPy routes the `scaninfo` method name to `/scaninfo` and `scaninfo_legacy` to `/scaninfo-legacy` automatically.

### Step 3: Extend `_SPA_ROUTES`

Find `_SPA_ROUTES = {"/", "/newscan", "/opts"}`. Change to `_SPA_ROUTES = {"/", "/newscan", "/opts", "/scaninfo"}`.

### Step 4: Update integration tests

Open `test/integration/test_sfwebui.py`. Find tests that hit `/scaninfo`. Expected relocations:

If there's a `test_scaninfo_returns_200` asserting Mako body content, update it to assert the SPA shell (mirror the `test_opts_returns_200` pattern from milestone 3):

```python
def test_scaninfo_returns_spa_shell(self):
    self.getPage("/scaninfo?id=doesnotexist")
    self.assertStatus('200 OK')
    body = self.body.decode() if isinstance(self.body, bytes) else self.body
    self.assertTrue(
        '<div id="root"></div>' in body or 'Web UI bundle not found' in body,
        msg=f"Unexpected /scaninfo body: {body[:300]}"
    )
```

If there's an existing `test_scaninfo_unknown_scan_id_returns_error` that currently asserts "Scan ID not found." in the body, that content is now served by `/scaninfo-legacy`. Change the URL in the test:

```python
def test_scaninfo_legacy_unknown_scan_id_returns_error(self):
    self.getPage("/scaninfo-legacy?id=doesnotexist")
    self.assertStatus('200 OK')
    self.assertInBody("Invalid scan ID.")
```

(Rename for clarity; keep the same body assertion against the renamed handler.)

### Step 5: Update unit tests

Open `test/unit/test_spiderfootwebui.py`. Find tests that invoke `sfwebui.scaninfo(...)`. Update them to either:
- Rename to invoke `sfwebui.scaninfo_legacy(...)` and keep the existing Mako-specific assertions, OR
- Update to the SPA-shell assertion (the `<div id="root">` or `Web UI bundle not found` fallback) when testing `sfwebui.scaninfo(...)`.

Both paths need coverage — keep one of each. If the existing test is:

```python
def test_scaninfo(self):
    """Test scaninfo(self, id)"""
    opts = self.default_options
    opts['__modules__'] = dict()
    sfwebui = SpiderFootWebUi(self.web_default_options, opts)
    scaninfo = sfwebui.scaninfo("example scan instance")
    self.assertIsInstance(scaninfo, str)
```

Split it into:

```python
def test_scaninfo(self):
    """Test scaninfo(self, id) — serves SPA shell."""
    opts = self.default_options
    opts['__modules__'] = dict()
    sfwebui = SpiderFootWebUi(self.web_default_options, opts)
    scaninfo = sfwebui.scaninfo("example scan instance")
    self.assertIsInstance(scaninfo, str)
    self.assertTrue(
        '<div id="root"></div>' in scaninfo or 'Web UI bundle not found' in scaninfo,
        msg=f"Unexpected /scaninfo body: {scaninfo[:300]}"
    )

def test_scaninfo_legacy(self):
    """Test scaninfo_legacy(self, id) — renders Mako template."""
    opts = self.default_options
    opts['__modules__'] = dict()
    sfwebui = SpiderFootWebUi(self.web_default_options, opts)
    scaninfo = sfwebui.scaninfo_legacy("example scan instance")
    self.assertIsInstance(scaninfo, str)
```

### Step 6: Run pytest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -5
```

Expected: **1464 passed or 1465 passed** (depending on whether unit-test split adds one). If the count drifts outside that window, investigate and report.

### Step 7: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add sfwebui.py test/integration/test_sfwebui.py test/unit/test_spiderfootwebui.py
git commit -m "$(cat <<'EOF'
webui: scaninfo() serves SPA shell; old Mako handler preserved

Milestone 4a takes /scaninfo into the SPA. The handler becomes a
one-liner via _serve_spa_shell(); _SPA_ROUTES grows to include
/scaninfo.

The old Mako implementation is renamed scaninfo_legacy() at the
temporary route /scaninfo-legacy — the SPA's placeholder tabs for
Browse/Correlations/Graph link there until milestones 4b and 4c
fill those in. Milestone 4c retires /scaninfo-legacy plus
scaninfo.tmpl and viz.js.

Relocated the existing scaninfo integration test's
"Invalid scan ID." body assertion onto /scaninfo-legacy; the
/scaninfo unit test now asserts SPA-shell response, with a
companion test_scaninfo_legacy covering the Mako path.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4a-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Frontend — types + scaninfo API + Vitest

**Files:**
- Modify: `webui/src/types.ts` — add 4 new types.
- Create: `webui/src/api/scaninfo.ts`, `webui/src/api/scaninfo.test.ts`.

### Step 1: Extend `webui/src/types.ts`

Append to the existing file. `ScanStatus` and `RiskMatrix` are defined earlier in the same file — just reference them; no import needed:

```typescript
export type ScanStatusPayload = {
  name: string;
  target: string;
  created: string;
  started: string;
  ended: string;
  status: ScanStatus;
  riskMatrix: RiskMatrix;
};

export type ScanSummaryRow = {
  typeId: string;
  typeLabel: string;
  lastSeen: string;
  count: number;
  uniqueCount: number;
};

export type ScanOptsPayload = {
  meta: string[];                          // raw [name, target, created, started, ended, status]
  config: Record<string, unknown>;
  configDesc: Record<string, string>;
};

export type ScanLogEntry = {
  generatedMs: number;
  component: string;
  level: string;
  message: string;
};
```

Also export a small helper in the same file:

```typescript
export function isScanRunning(status: ScanStatus): boolean {
  return (
    status === 'CREATED' ||
    status === 'STARTING' ||
    status === 'STARTED' ||
    status === 'RUNNING'
  );
}
```

### Step 2: Create `webui/src/api/scaninfo.ts`

```typescript
import { ApiError, fetchJson } from './client';
import type {
  ScanStatusPayload,
  ScanSummaryRow,
  ScanOptsPayload,
  ScanLogEntry,
  ScanStatus,
  RiskMatrix,
} from '../types';

type ScanStatusTuple = [string, string, string, string, string, ScanStatus, RiskMatrix];

export async function fetchScanStatus(id: string): Promise<ScanStatusPayload> {
  const result = await fetchJson<ScanStatusTuple | []>(
    `/scanstatus?id=${encodeURIComponent(id)}`,
  );
  if (!Array.isArray(result) || result.length === 0) {
    throw new ApiError(404, `Scan ${id} not found`);
  }
  const [name, target, created, started, ended, status, riskMatrix] = result;
  return { name, target, created, started, ended, status, riskMatrix };
}

type ScanSummaryTuple = [string, string, string, number, number, ScanStatus];

export async function fetchScanSummary(id: string): Promise<ScanSummaryRow[]> {
  const rows = await fetchJson<ScanSummaryTuple[]>(
    `/scansummary?id=${encodeURIComponent(id)}&by=type`,
  );
  return rows.map(([typeId, typeLabel, lastSeen, count, uniqueCount]) => ({
    typeId,
    typeLabel,
    lastSeen,
    count,
    uniqueCount,
  }));
}

export async function fetchScanOpts(id: string): Promise<ScanOptsPayload> {
  return fetchJson<ScanOptsPayload>(`/scanopts?id=${encodeURIComponent(id)}`);
}

type ScanLogTuple = [number, string, string, string, string];
const LOG_LIMIT = 500;

export async function fetchScanLog(
  id: string,
  limit: number = LOG_LIMIT,
): Promise<ScanLogEntry[]> {
  const rows = await fetchJson<ScanLogTuple[]>(
    `/scanlog?id=${encodeURIComponent(id)}&limit=${limit}`,
  );
  return rows.map(([generatedMs, component, level, message]) => ({
    generatedMs,
    component,
    level,
    message,
  }));
}

export async function stopScan(id: string): Promise<void> {
  // /stopscan returns "" on success, an error tuple on failure.
  // We treat any non-success response as an error.
  const body = await fetchJson<string | { error: { message: string } }>(
    `/stopscan?id=${encodeURIComponent(id)}`,
  );
  if (typeof body === 'object' && body && 'error' in body) {
    throw new Error(body.error.message ?? 'Failed to stop scan');
  }
}
```

### Step 3: Create `webui/src/api/scaninfo.test.ts`

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import {
  fetchScanStatus,
  fetchScanSummary,
  fetchScanLog,
  fetchScanOpts,
  stopScan,
} from './scaninfo';
import { ApiError } from './client';

describe('fetchScanStatus', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('unwraps the 7-tuple response into a typed payload', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          'my-scan',
          'example.com',
          '2026-04-20 10:00:00',
          '2026-04-20 10:00:01',
          '2026-04-20 10:10:00',
          'FINISHED',
          { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 2 },
        ]),
        { status: 200 },
      ),
    );
    const result = await fetchScanStatus('abc');
    expect(result).toEqual({
      name: 'my-scan',
      target: 'example.com',
      created: '2026-04-20 10:00:00',
      started: '2026-04-20 10:00:01',
      ended: '2026-04-20 10:10:00',
      status: 'FINISHED',
      riskMatrix: { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 2 },
    });
  });

  it('throws a 404 ApiError when the response is empty', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('[]', { status: 200 }),
    );
    await expect(fetchScanStatus('missing')).rejects.toBeInstanceOf(ApiError);
  });
});

describe('fetchScanSummary', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps rows to typed ScanSummaryRow[]', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['INTERNET_NAME', 'Internet Name', '2026-04-20 14:23:01', 42, 8, 'FINISHED'],
          ['IP_ADDRESS', 'IP Address', '2026-04-20 14:23:05', 10, 10, 'FINISHED'],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchScanSummary('abc');
    expect(rows).toEqual([
      {
        typeId: 'INTERNET_NAME',
        typeLabel: 'Internet Name',
        lastSeen: '2026-04-20 14:23:01',
        count: 42,
        uniqueCount: 8,
      },
      {
        typeId: 'IP_ADDRESS',
        typeLabel: 'IP Address',
        lastSeen: '2026-04-20 14:23:05',
        count: 10,
        uniqueCount: 10,
      },
    ]);
  });
});

describe('fetchScanLog', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps rows to typed ScanLogEntry[] and sends the default limit', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          [1_700_000_000_000, 'sfp_countryname', 'INFO', 'Module started', 'h1'],
          [1_700_000_100_000, 'sfp_countryname', 'DEBUG', 'Hit', 'h2'],
        ]),
        { status: 200 },
      ),
    );
    const rows = await fetchScanLog('abc');
    expect(rows).toEqual([
      {
        generatedMs: 1_700_000_000_000,
        component: 'sfp_countryname',
        level: 'INFO',
        message: 'Module started',
      },
      {
        generatedMs: 1_700_000_100_000,
        component: 'sfp_countryname',
        level: 'DEBUG',
        message: 'Hit',
      },
    ]);
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/scanlog?id=abc&limit=500');
  });
});

describe('fetchScanOpts', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns the raw payload shape', async () => {
    const payload = {
      meta: ['n', 't', 'c', 's', 'e', 'FINISHED'],
      config: { 'global.webroot': '/sf' },
      configdesc: { 'global.webroot': 'Web root' },
    };
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    const result = await fetchScanOpts('abc');
    expect(result).toEqual(payload);
  });
});

describe('stopScan', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('resolves on empty-string success response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response('""', { status: 200 }),
    );
    await expect(stopScan('abc')).resolves.toBeUndefined();
  });

  it('throws on error response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify({ error: { http_status: '400', message: 'Already finished' } }),
        { status: 200 },
      ),
    );
    await expect(stopScan('abc')).rejects.toThrow('Already finished');
  });
});
```

### Step 4: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **43 existing + 8 new = 51 passing**.

### Step 5: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

Expected: success.

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/types.ts webui/src/api/scaninfo.ts webui/src/api/scaninfo.test.ts
git commit -m "$(cat <<'EOF'
webui: typed API for /scanstatus, /scansummary, /scanopts, /scanlog, /stopscan

Adds ScanStatusPayload / ScanSummaryRow / ScanOptsPayload /
ScanLogEntry types and an isScanRunning helper, plus the
scaninfo.ts wrapper module. Each function maps the backend's
positional-tuple response into a typed object so consumers never
see the tuple shape.

fetchScanStatus() throws a 404 ApiError when the backend returns
an empty list (scan ID not found) so the page renders a clean
"Scan not found" state.

8 Vitest cases cover tuple -> object mapping, empty-response
handling, the URL encoding + limit the log fetch uses, and the
success + error paths of stopScan().

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4a-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Frontend — ScanInfoPage shell + PlaceholderTab + Vitest shell tests

**Files:**
- Create: `webui/src/pages/ScanInfoPage.tsx` — wrapper with header + tab shell (tabs render empty bodies for now; Task 4 fills them).
- Create: `webui/src/pages/scaninfo/PlaceholderTab.tsx`.
- Create: `webui/src/pages/ScanInfoPage.test.tsx` — 3 shell-level Vitest cases.

### Step 1: Create `webui/src/pages/scaninfo/PlaceholderTab.tsx`

```tsx
import { Alert, Anchor, Stack, Text } from '@mantine/core';

export function PlaceholderTab({
  tabLabel,
  scanId,
}: {
  tabLabel: string;
  scanId: string;
}) {
  return (
    <Alert color="blue" title="This view is being migrated" mt="md">
      <Stack gap="xs">
        <Text size="sm">
          The updated <strong>{tabLabel}</strong> view arrives in a follow-up
          milestone. Use the legacy view for now.
        </Text>
        <Anchor href={`/scaninfo-legacy?id=${encodeURIComponent(scanId)}`}>
          Open legacy {tabLabel} view
        </Anchor>
      </Stack>
    </Alert>
  );
}
```

### Step 2: Create `webui/src/pages/ScanInfoPage.tsx` (shell only)

```tsx
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Anchor,
  Breadcrumbs,
  Button,
  Group,
  Loader,
  Stack,
  Tabs,
  Title,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { useSearchParams } from 'react-router-dom';
import { fetchScanStatus, stopScan } from '../api/scaninfo';
import { ScanStatusBadge } from '../components/ScanStatusBadge';
import { ApiError } from '../api/client';
import { isScanRunning } from '../types';
import { PlaceholderTab } from './scaninfo/PlaceholderTab';

type TabKey =
  | 'status'
  | 'correlations'
  | 'browse'
  | 'graph'
  | 'info'
  | 'log';

export function ScanInfoPage() {
  const [params] = useSearchParams();
  const id = params.get('id') ?? '';
  const [activeTab, setActiveTab] = useState<TabKey>('status');
  const queryClient = useQueryClient();

  const statusQuery = useQuery({
    queryKey: ['scanstatus', id],
    queryFn: () => fetchScanStatus(id),
    enabled: id.length > 0,
    refetchInterval: (query) =>
      query.state.data && isScanRunning(query.state.data.status) ? 5_000 : false,
  });

  const abortMutation = useMutation({
    mutationFn: () => stopScan(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scanstatus', id] });
    },
  });

  if (!id) {
    return (
      <Alert color="red" title="Missing scan id" mt="md">
        The scan-detail URL requires an <code>?id=&lt;guid&gt;</code> query
        parameter. <Anchor href="/">Back to scan list</Anchor>.
      </Alert>
    );
  }

  if (statusQuery.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }

  if (statusQuery.isError) {
    const err = statusQuery.error;
    const is404 = err instanceof ApiError && err.status === 404;
    return (
      <Alert color="red" title={is404 ? 'Scan not found' : 'Failed to load scan'} mt="md">
        {is404
          ? `No scan with id "${id}" exists.`
          : (err as Error).message ?? 'Unknown error'}
        <Group mt="sm">
          <Button size="xs" component="a" href="/">
            Back to scan list
          </Button>
        </Group>
      </Alert>
    );
  }

  const status = statusQuery.data!;
  const running = isScanRunning(status.status);

  const openAbortConfirm = () =>
    modals.openConfirmModal({
      title: 'Abort scan?',
      children: `This aborts "${status.name}" — running modules stop and the scan is marked ABORTED.`,
      labels: { confirm: 'Abort', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => abortMutation.mutate(),
    });

  const refreshAll = () => {
    void queryClient.invalidateQueries({ queryKey: ['scanstatus', id] });
    void queryClient.invalidateQueries({ queryKey: ['scansummary', id] });
    void queryClient.invalidateQueries({ queryKey: ['scanopts', id] });
    void queryClient.invalidateQueries({ queryKey: ['scanlog', id] });
  };

  return (
    <Stack>
      <Breadcrumbs>
        {/* Plain <a>: full-page reload back to SPA scan list. */}
        <Anchor href="/">Scans</Anchor>
        <span>{status.name}</span>
      </Breadcrumbs>

      <Group justify="space-between">
        <Group>
          <Title order={2}>{status.name}</Title>
          <ScanStatusBadge status={status.status} />
        </Group>
        <Group>
          {running && (
            <Button
              color="red"
              variant="light"
              disabled={abortMutation.isPending}
              loading={abortMutation.isPending}
              onClick={openAbortConfirm}
            >
              Abort
            </Button>
          )}
          <Button variant="subtle" onClick={refreshAll}>
            Refresh
          </Button>
        </Group>
      </Group>

      {abortMutation.isError && (
        <Alert color="red" title="Abort failed">
          {(abortMutation.error as Error).message}
        </Alert>
      )}

      <Tabs value={activeTab} onChange={(v) => setActiveTab((v ?? 'status') as TabKey)}>
        <Tabs.List>
          <Tabs.Tab value="status">Status</Tabs.Tab>
          <Tabs.Tab value="correlations">Correlations</Tabs.Tab>
          <Tabs.Tab value="browse">Browse</Tabs.Tab>
          <Tabs.Tab value="graph">Graph</Tabs.Tab>
          <Tabs.Tab value="info">Info</Tabs.Tab>
          <Tabs.Tab value="log">Log</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="status" pt="md">
          {/* Task 4 fills in StatusTab */}
          <Alert color="gray" title="Status tab coming in Task 4">Stub.</Alert>
        </Tabs.Panel>
        <Tabs.Panel value="correlations" pt="md">
          <PlaceholderTab tabLabel="Correlations" scanId={id} />
        </Tabs.Panel>
        <Tabs.Panel value="browse" pt="md">
          <PlaceholderTab tabLabel="Browse" scanId={id} />
        </Tabs.Panel>
        <Tabs.Panel value="graph" pt="md">
          <PlaceholderTab tabLabel="Graph" scanId={id} />
        </Tabs.Panel>
        <Tabs.Panel value="info" pt="md">
          {/* Task 4 fills in InfoTab */}
          <Alert color="gray" title="Info tab coming in Task 4">Stub.</Alert>
        </Tabs.Panel>
        <Tabs.Panel value="log" pt="md">
          {/* Task 4 fills in LogTab */}
          <Alert color="gray" title="Log tab coming in Task 4">Stub.</Alert>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
```

### Step 3: Create `webui/src/pages/ScanInfoPage.test.tsx`

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ScanInfoPage } from './ScanInfoPage';

describe('ScanInfoPage', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function renderAt(url: string) {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <ModalsProvider>
            <MemoryRouter initialEntries={[url]}>
              <Routes>
                <Route path="/scaninfo" element={<ScanInfoPage />} />
              </Routes>
            </MemoryRouter>
          </ModalsProvider>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockStatus(status: string, extras: Record<string, unknown> = {}) {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url.startsWith('/scanstatus')) {
        return Promise.resolve(
          new Response(
            JSON.stringify([
              'my-scan',
              'example.com',
              '2026-04-20 10:00:00',
              '2026-04-20 10:00:01',
              status === 'FINISHED' ? '2026-04-20 10:10:00' : 'Not yet',
              status,
              { HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 },
              ...Object.values(extras),
            ]),
            { status: 200 },
          ),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  it('renders scan name + status badge + six tab labels', async () => {
    mockStatus('FINISHED');
    renderAt('/scaninfo?id=abc');
    expect(await screen.findByText('my-scan')).toBeInTheDocument();
    expect(screen.getByText('FINISHED')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Status' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Correlations' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Browse' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Graph' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Info' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Log' })).toBeInTheDocument();
  });

  it('hides Abort button on terminal status', async () => {
    mockStatus('FINISHED');
    renderAt('/scaninfo?id=abc');
    await screen.findByText('my-scan');
    expect(screen.queryByRole('button', { name: 'Abort' })).not.toBeInTheDocument();
  });

  it('shows Abort button while running and switching to Correlations tab shows the placeholder with legacy link', async () => {
    mockStatus('RUNNING');
    renderAt('/scaninfo?id=abc');
    await screen.findByText('my-scan');
    expect(screen.getByRole('button', { name: 'Abort' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('tab', { name: 'Correlations' }));
    const legacyLink = await screen.findByRole('link', {
      name: /Open legacy Correlations view/,
    });
    expect(legacyLink).toHaveAttribute('href', '/scaninfo-legacy?id=abc');
  });
});
```

### Step 4: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **51 + 3 = 54 passing**.

### Step 5: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/ScanInfoPage.tsx webui/src/pages/ScanInfoPage.test.tsx webui/src/pages/scaninfo/PlaceholderTab.tsx
git commit -m "$(cat <<'EOF'
webui: ScanInfoPage shell + PlaceholderTab

Top-level /scaninfo wrapper. Reads the scan id from ?id= via
useSearchParams, fetches /scanstatus, renders a header (name +
ScanStatusBadge + Abort when running + Refresh), and a six-tab
Mantine Tabs control.

Task 4 fills in StatusTab / InfoTab / LogTab bodies — they're
stubbed with a gray "coming in Task 4" Alert in this commit to
keep the shell-level tests green.

PlaceholderTab handles the three not-yet-migrated tabs
(Correlations / Browse / Graph). It renders a centered Alert
with a link to /scaninfo-legacy?id=<guid> so users retain
functional access to those views throughout 4a and 4b.

Polling: /scanstatus refetches every 5s while status is in
running states, stops on terminal. Abort button opens a confirm
modal and fires /stopscan.

Three shell-level Vitest cases: header + 6 tabs render, Abort
is hidden on terminal and shown on running, Correlations tab
shows the placeholder with the legacy-link href.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4a-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Frontend — StatusTab + InfoTab + LogTab

**Files:**
- Create: `webui/src/pages/scaninfo/StatusTab.tsx`, `InfoTab.tsx`, `LogTab.tsx`.
- Modify: `webui/src/pages/ScanInfoPage.tsx` — swap the three stubbed tabs to real components.

### Step 1: Create `webui/src/pages/scaninfo/StatusTab.tsx`

```tsx
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Card,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { fetchScanSummary } from '../../api/scaninfo';
import { isScanRunning } from '../../types';
import type { ScanStatusPayload } from '../../types';

export function StatusTab({ id, status }: { id: string; status: ScanStatusPayload }) {
  const query = useQuery({
    queryKey: ['scansummary', id],
    queryFn: () => fetchScanSummary(id),
    refetchInterval: () => (isScanRunning(status.status) ? 5_000 : false),
  });

  const totalEvents = useMemo(
    () => (query.data ?? []).reduce((sum, r) => sum + r.count, 0),
    [query.data],
  );

  if (query.isLoading) {
    return (
      <Group justify="center" mt="md">
        <Loader />
      </Group>
    );
  }

  if (query.isError) {
    return (
      <Alert color="red" title="Failed to load summary">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = (query.data ?? []).slice().sort((a, b) => b.count - a.count);

  return (
    <Stack>
      <Card withBorder>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Stat label="Target" value={status.target} />
          <Stat label="Started" value={status.started} />
          <Stat label="Ended" value={status.ended} />
          <Stat label="Total events" value={totalEvents.toString()} />
        </SimpleGrid>
      </Card>

      {rows.length === 0 ? (
        <Alert color="gray">No events produced yet.</Alert>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Event type</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>Count</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>Unique</Table.Th>
              <Table.Th>Last seen</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r) => (
              <Table.Tr key={r.typeId}>
                <Table.Td>
                  <Stack gap={0}>
                    <Text size="sm" fw={500}>{r.typeLabel}</Text>
                    <Text size="xs" c="dimmed">{r.typeId}</Text>
                  </Stack>
                </Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>{r.count}</Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>{r.uniqueCount}</Table.Td>
                <Table.Td>{r.lastSeen}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" fw={500}>{value}</Text>
    </Stack>
  );
}
```

### Step 2: Create `webui/src/pages/scaninfo/InfoTab.tsx`

```tsx
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Accordion,
  Alert,
  Code,
  Group,
  Loader,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { fetchScanOpts } from '../../api/scaninfo';

const META_LABELS = ['Name', 'Target', 'Target type', 'Modules', 'Created', 'Started', 'Ended'];

export function InfoTab({ id }: { id: string }) {
  const query = useQuery({
    queryKey: ['scanopts', id],
    queryFn: () => fetchScanOpts(id),
  });

  const { globalKvs, moduleKvs } = useMemo(() => {
    const config = (query.data?.config ?? {}) as Record<string, unknown>;
    const globalKvs: [string, unknown][] = [];
    const moduleKvs: [string, unknown][] = [];
    for (const [k, v] of Object.entries(config)) {
      if (k.startsWith('global.')) globalKvs.push([k, v]);
      else if (k.startsWith('module.')) moduleKvs.push([k, v]);
    }
    globalKvs.sort(([a], [b]) => a.localeCompare(b));
    moduleKvs.sort(([a], [b]) => a.localeCompare(b));
    return { globalKvs, moduleKvs };
  }, [query.data]);

  if (query.isLoading) {
    return (
      <Group justify="center" mt="md">
        <Loader />
      </Group>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Alert color="red" title="Failed to load scan config">
        {(query.error as Error)?.message ?? 'Unknown error'}
      </Alert>
    );
  }

  const meta = query.data.meta ?? [];

  return (
    <Stack>
      <Table withTableBorder>
        <Table.Tbody>
          {meta.map((v, i) => (
            <Table.Tr key={i}>
              <Table.Td style={{ width: 180 }}>
                <Text size="sm" fw={500}>{META_LABELS[i] ?? `Field ${i}`}</Text>
              </Table.Td>
              <Table.Td>
                <Code>{String(v)}</Code>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <Accordion variant="separated">
        <Accordion.Item value="global">
          <Accordion.Control>
            Global settings ({globalKvs.length})
          </Accordion.Control>
          <Accordion.Panel>
            <KvTable rows={globalKvs} />
          </Accordion.Panel>
        </Accordion.Item>
        <Accordion.Item value="module">
          <Accordion.Control>
            Module settings ({moduleKvs.length})
          </Accordion.Control>
          <Accordion.Panel>
            <KvTable rows={moduleKvs} />
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}

function KvTable({ rows }: { rows: [string, unknown][] }) {
  if (rows.length === 0) return <Text size="sm" c="dimmed">No entries.</Text>;
  return (
    <Table striped>
      <Table.Tbody>
        {rows.map(([k, v]) => (
          <Table.Tr key={k}>
            <Table.Td style={{ width: '40%' }}>
              <Code>{k}</Code>
            </Table.Td>
            <Table.Td>
              <Code>{Array.isArray(v) ? v.join(', ') : String(v)}</Code>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
```

### Step 3: Create `webui/src/pages/scaninfo/LogTab.tsx`

```tsx
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { fetchScanLog } from '../../api/scaninfo';
import { isScanRunning } from '../../types';
import type { ScanStatusPayload } from '../../types';

const LOG_LIMIT = 500;

function levelColor(level: string): string {
  switch (level.toUpperCase()) {
    case 'ERROR':
      return 'red';
    case 'WARN':
    case 'WARNING':
      return 'orange';
    case 'INFO':
      return 'blue';
    case 'DEBUG':
      return 'gray';
    default:
      return 'gray';
  }
}

export function LogTab({ id, status }: { id: string; status: ScanStatusPayload }) {
  const query = useQuery({
    queryKey: ['scanlog', id],
    queryFn: () => fetchScanLog(id),
    refetchInterval: () => (isScanRunning(status.status) ? 5_000 : false),
  });

  if (query.isLoading) {
    return (
      <Group justify="center" mt="md">
        <Loader />
      </Group>
    );
  }
  if (query.isError) {
    return (
      <Alert color="red" title="Failed to load log">
        {(query.error as Error).message}
      </Alert>
    );
  }

  const rows = query.data ?? [];
  const truncated = rows.length >= LOG_LIMIT;

  return (
    <Stack>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          {truncated
            ? `Showing ${rows.length} of many lines — download for the full log.`
            : `${rows.length} log ${rows.length === 1 ? 'entry' : 'entries'}`}
        </Text>
        <Button
          component="a"
          href={`/scanexportlogs?id=${encodeURIComponent(id)}`}
          leftSection={<IconDownload size={14} />}
          variant="light"
        >
          Download logs
        </Button>
      </Group>

      {rows.length === 0 ? (
        <Alert color="gray">No log entries yet.</Alert>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 180 }}>Timestamp</Table.Th>
              <Table.Th style={{ width: 160 }}>Component</Table.Th>
              <Table.Th style={{ width: 80 }}>Level</Table.Th>
              <Table.Th>Message</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r, i) => (
              <Table.Tr key={i}>
                <Table.Td>{new Date(r.generatedMs).toISOString()}</Table.Td>
                <Table.Td>
                  <Text size="xs">{r.component}</Text>
                </Table.Td>
                <Table.Td>
                  <Badge color={levelColor(r.level)} variant="light">
                    {r.level}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" style={{ wordBreak: 'break-word' }}>
                    {r.message}
                  </Text>
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

### Step 4: Wire the three tabs into `ScanInfoPage.tsx`

Open `webui/src/pages/ScanInfoPage.tsx`. Add imports:

```tsx
import { StatusTab } from './scaninfo/StatusTab';
import { InfoTab } from './scaninfo/InfoTab';
import { LogTab } from './scaninfo/LogTab';
```

Replace the three stub `<Alert color="gray" title="… coming in Task 4">Stub.</Alert>` lines with:

```tsx
<Tabs.Panel value="status" pt="md">
  <StatusTab id={id} status={status} />
</Tabs.Panel>

...

<Tabs.Panel value="info" pt="md">
  <InfoTab id={id} />
</Tabs.Panel>
<Tabs.Panel value="log" pt="md">
  <LogTab id={id} status={status} />
</Tabs.Panel>
```

### Step 5: Run Vitest + build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -4
```

Expected: **54 passing** (no new tests yet — Task 4 focuses on components; they're exercised through the shell's existing tests and the Playwright E2E in Task 5).

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/scaninfo/StatusTab.tsx webui/src/pages/scaninfo/InfoTab.tsx webui/src/pages/scaninfo/LogTab.tsx webui/src/pages/ScanInfoPage.tsx
git commit -m "$(cat <<'EOF'
webui: ScanInfoPage Status / Info / Log tab bodies

Three typed tabs built on top of the scaninfo API layer from
Task 2:

- StatusTab: Card of top-level stats + sorted Table of event
  types (typeLabel / count / unique / last seen). Polls every
  5s while the scan is running.

- InfoTab: read-only scan config display. Meta row table + two
  Accordion sections (Global / Module settings). Data frozen —
  no polling.

- LogTab: Table of log entries with level-colored Badge +
  download button linking to /scanexportlogs. Polls every 5s
  while running; caps at 500 visible rows with a "download for
  full" hint when truncated.

ScanInfoPage.tsx swaps the three Task 3 stubs to the real
components. Placeholder tabs (Correlations / Browse / Graph)
still render via PlaceholderTab -> /scaninfo-legacy.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4a-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Router wiring + Playwright

**Files:**
- Modify: `webui/src/router.tsx` — add `/scaninfo` route.
- Create: `webui/tests/e2e/05-scaninfo.spec.ts`.

### Step 1: Modify `webui/src/router.tsx`

Replace contents:

```tsx
import { createBrowserRouter } from 'react-router-dom';
import { ScanListPage } from './pages/ScanListPage';
import { NewScanPage } from './pages/NewScanPage';
import { OptsPage } from './pages/OptsPage';
import { ScanInfoPage } from './pages/ScanInfoPage';

export const router = createBrowserRouter([
  { path: '/', element: <ScanListPage /> },
  { path: '/newscan', element: <NewScanPage /> },
  { path: '/opts', element: <OptsPage /> },
  { path: '/scaninfo', element: <ScanInfoPage /> },
]);
```

### Step 2: Create `webui/tests/e2e/05-scaninfo.spec.ts`

The Playwright fixture seeds a `monthly-recon` scan with status `FINISHED`. We look it up by name, grab its guid from the DOM on the scan list, then navigate to `/scaninfo?id=<guid>`.

```typescript
import { test, expect } from '@playwright/test';

// Runs after 04-opts.spec.ts. Uses the "monthly-recon" FINISHED
// scan seeded by seed_db.py.

async function openFinishedScanInfo(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/');
  // Find the "monthly-recon" row's anchor — it points at /scaninfo?id=<guid>.
  const anchor = page.getByRole('link', { name: 'monthly-recon' });
  await expect(anchor).toBeVisible();
  const href = await anchor.getAttribute('href');
  expect(href).toMatch(/\/scaninfo\?id=.+/);
  await anchor.click();
  await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 10_000 });
}

test.describe('Scan info page (M4a: Status + Info + Log)', () => {
  test('Status tab renders scan summary after navigating from scan list', async ({ page }) => {
    await openFinishedScanInfo(page);
    await expect(page.getByRole('heading', { name: 'monthly-recon' })).toBeVisible();
    await expect(page.getByText('FINISHED')).toBeVisible();

    // The Status tab is the default. "Total events" stat should be present.
    await expect(page.getByText('Total events')).toBeVisible();
  });

  test('Info tab renders the scan meta + global/module settings accordions', async ({ page }) => {
    await openFinishedScanInfo(page);
    await page.getByRole('tab', { name: 'Info' }).click();
    await expect(page.getByRole('cell', { name: 'Target' })).toBeVisible();
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
```

### Step 3: Build to confirm TS compiles

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 4: Run Playwright

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run test:e2e 2>&1 | tail -20
```

Expected: **9 existing + 3 new = 12 passing** (3 scan-list + 1 empty-state + 3 new-scan + 2 opts + 3 scaninfo).

### Step 5: Full `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 54 Vitest + 12 Playwright + flake8 clean + ~1464-1466 pytest (depending on Task 1's unit-test split).

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/router.tsx webui/tests/e2e/05-scaninfo.spec.ts
git commit -m "$(cat <<'EOF'
webui: /scaninfo router wiring + Playwright E2E

Router now has 4 routes: /, /newscan, /opts, /scaninfo.

05-scaninfo.spec.ts exercises the full navigation path: scan
list -> click "monthly-recon" -> /scaninfo?id=<guid>. Three
tests cover the Status tab summary render, Info tab accordion
controls, and Log tab download button's href.

Runs against the seeded FINISHED scan from the fixture DB;
placeholder tabs (Browse / Correlations / Graph) aren't tested
here since 4b+4c will replace their content.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4a-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Docs refresh + final verify

**Files:**
- Modify: `CLAUDE.md` — Web UI section milestone list.
- Modify: `docs/superpowers/BACKLOG.md` — mark M4a shipped.

### Step 1: Update `CLAUDE.md`

Find the Web UI top paragraph:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1–3 (2026-04-20) migrated `/` (scan list), `/newscan` (scan creation), and `/opts` (settings). Remaining Mako pages (`/scaninfo`, shared chrome via `HEADER.tmpl`/`FOOTER.tmpl`/`error.tmpl`) are unchanged and reachable.
```

Replace with:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1–4a (2026-04-20) migrated `/` (scan list), `/newscan` (scan creation), `/opts` (settings), and `/scaninfo` with the Status/Info/Log tabs; Browse/Correlations/Graph tabs render a placeholder that links to the still-Mako `/scaninfo-legacy` for functional fallback until milestones 4b+4c fill them in. The final sweep retires shared chrome (`HEADER.tmpl`/`FOOTER.tmpl`/`error.tmpl`) along with the legacy route.
```

### Step 2: Update `BACKLOG.md`

Under `### UI modernization — page-by-page migration` → `**Shipped:**` append:

```
- Milestone 4a (2026-04-20) — `/scaninfo` SPA shell + Status/Info/Log tabs. Browse/Correlations/Graph tabs render a placeholder linking to the temporarily-retained `/scaninfo-legacy` Mako handler. Zero new JSON endpoints — reuses `/scanstatus`, `/scansummary`, `/scanopts`, `/scanlog`, `/scanexportlogs`, `/stopscan`.
```

Update the **Remaining Mako pages** block to reflect M4a:

```
**Remaining Mako pages to migrate** (each its own spec + plan):
- `/scaninfo` — Browse + Correlations tabs (milestone 4b).
- `/scaninfo` — Graph tab + `viz.js` replacement (milestone 4c). Picks a React-native graph library (react-flow / cytoscape / keep sigma wrapped).
- Final sweep: retires `/scaninfo-legacy`, `scaninfo.tmpl`, `HEADER.tmpl`, `FOOTER.tmpl`, `error.tmpl`, `spiderfoot.js`, legacy CSS, and `spiderfoot/static/node_modules/`. Also folds in the Clone-scan UX (scan list menu + new JSON endpoint).
```

Update the specs line so it references `{1,2,3,4a}-design.md`.

### Step 3: Run `./test/run` one final time

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build OK + 54 Vitest + 12 Playwright + flake8 clean + ~1464-1466 pytest / 34 skipped.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — milestone 4a Web UI

Updates the Web UI section to reflect M4a shipped: /scaninfo is
now SPA-served with the Status/Info/Log tabs migrated; Browse,
Correlations, and Graph render a placeholder that links to the
temporary /scaninfo-legacy route.

BACKLOG.md reshuffles the remaining-pages list: milestone 4b
fills Browse + Correlations, 4c swaps out viz.js for Graph, and
the final-sweep milestone retires the legacy route + shared
chrome.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-4a-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 5: Milestone summary

Report to the user:
- 6 commits across M4a.
- SPA now owns `/`, `/newscan`, `/opts`, `/scaninfo` (3 of 6 tabs).
- 54 Vitest + 12 Playwright + flake8 clean + pytest all green.
- Legacy escape hatch at `/scaninfo-legacy?id=X` remains live for the 3 not-yet-migrated tabs; retires in M4c.
- Up next: M4b (Browse + Correlations) or other backlog work.
