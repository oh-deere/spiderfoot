# Web UI SPA — Milestone 2 (`/newscan`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate SpiderFoot's `/newscan` page from Mako + jQuery + Bootstrap 3 to the React SPA. Retire `newscan.tmpl`, its companion JS, and the orphaned `clonescan` handler. Extend two JSON endpoints so the SPA can consume module metadata and submit scans cleanly.

**Architecture:** 8 tasks in TDD order. Backend changes land first (helper refactor + JSON extensions + Python test cleanup) so the frontend work has a stable target. Frontend then adds typed API + components + page + router in three tasks. Retirements and docs close out.

**Tech Stack:** Python 3.12 + CherryPy (unchanged), React 19 + Mantine 9 + TanStack Query 5 + React Router 7 + Vitest + Playwright. `@tabler/icons-react` is already a transitive dep of Mantine; if not, add it.

**Spec:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md`.

---

## File Structure

### Backend (Python)
- **Modify** `sfwebui.py` — add `_serve_spa_shell()` private method; refactor `index()` to use it; replace `newscan()` body with it; remove `clonescan()`; extend `modules()` JSON shape; extend `startscan()` with JSON success branch.
- **Modify** `test/unit/test_spiderfootwebui.py` — delete `test_clonescan`; update `test_newscan` to assert SPA-shell serving (or delete since it's a no-op placeholder).
- **Modify** `test/integration/test_sfwebui.py` — delete `test_clonescan`; update `test_newscan_returns_200` to assert SPA shell.

### Frontend (React)
- **Create** `webui/src/pages/NewScanPage.tsx`, `webui/src/pages/NewScanPage.test.tsx`.
- **Create** `webui/src/components/UseCaseTab.tsx`, `webui/src/components/ModuleTab.tsx`, `webui/src/components/TypeTab.tsx`.
- **Create** `webui/src/api/modules.ts`.
- **Modify** `webui/src/types.ts` (add `Module`, `EventType`, `SelectionMode`, `UseCase`).
- **Modify** `webui/src/api/scans.ts` (add `startScan`).
- **Modify** `webui/src/router.tsx` (add `/newscan` route).

### E2E + Robot
- **Create** `webui/tests/e2e/03-new-scan.spec.ts`.
- **Modify** `test/acceptance/scan.robot` — remove `New scan page should render` keyword (still referenced in `Main navigation pages should render correctly`).

### Retirements
- **Delete** `spiderfoot/templates/newscan.tmpl`.
- **Delete** `spiderfoot/static/js/spiderfoot.newscan.js`.

### Docs
- **Modify** `CLAUDE.md` — update Web UI section's "Adding a migrated page" recipe with the `_serve_spa_shell()` pattern.
- **Modify** `docs/superpowers/BACKLOG.md` — mark milestone 2 shipped; bump remaining-Mako count.

---

## Context for the implementer

- **Branch:** commit directly on `master` (matches milestone 1 pattern).
- **Baseline:** 12 Vitest + 4 Playwright + flake8 clean + 1460 pytest + 35 skipped, all via `./test/run`.
- **SPA-shell serving after milestone 1:** `sfwebui.py` defines `_SPA_ROUTES = {"/"}` and `_SPA_DIST` module constants, plus an `index()` method that reads `webui/dist/index.html`. This plan factors the file-read logic into a helper.
- **`/startscan` current semantics:** when any of name/target/module-selection is missing, returns `["ERROR", "<message>"]` JSON if `Accept: application/json`, else `self.error(<html>)`. On success, raises `cherrypy.HTTPRedirect` to `/scaninfo?id=<guid>`. The integration test suite at `test/integration/test_sfwebui.py:180-206` exercises these paths without setting `Accept: application/json`, so the HTML branch stays green and we only add a JSON success branch.
- **`config['__modules__'][m]['opts']`** is a dict of opt keys → default values. An "API-key module" has at least one opt key containing `"api_key"` (case-sensitive; matches the existing Mako template's `k.find("api_key") >= 0` logic).
- **Removed `clonescan`** — no reachable caller after milestone 1 (the Mako scanlist had the Clone button). Unit test at `test_spiderfootwebui.py:261-269` and integration at `test_sfwebui.py:109-112` must be removed.
- **Backend-first ordering:** Tasks 1-3 modify sfwebui.py; frontend tasks start fresh from Task 4 against stable JSON surface.
- **Mantine v9:** `<Tabs>`, `<Radio.Group>`, `<TextInput>`, `<Table>`, `<Checkbox>`, `<Button>`, `<Alert>`, `<Loader>`, `<Accordion>`. Icons from `@tabler/icons-react` — check if already installed: `cd webui && npm ls @tabler/icons-react 2>/dev/null | head -2`. Install with `npm install @tabler/icons-react` if missing.

---

## Task 1: Backend — SPA-shell helper + newscan handler + clonescan retirement

**Files:**
- Modify: `sfwebui.py` — add `_serve_spa_shell()`, refactor `index()`, replace `newscan()` body, remove `clonescan()`.
- Modify: `test/unit/test_spiderfootwebui.py` — delete `test_clonescan` (lines 261-269); keep `test_newscan` as-is (no-op placeholder, harmless).
- Modify: `test/integration/test_sfwebui.py` — delete `test_clonescan` (lines 109-112); update `test_newscan_returns_200` (lines 103-107) to assert the SPA-shell response.
- Modify: `sfwebui.py` — add `/newscan` to `_SPA_ROUTES`.

- [ ] **Step 1: Read the current `_SPA_DIST` / `index()` / `newscan()` / `clonescan()` lines**

Use Grep to locate them (current positions may drift from the numbers below if earlier work touched the file):

```bash
grep -nE "_SPA_(ROUTES|DIST)|def index\(|def newscan\(|def clonescan\(" sfwebui.py
```

You should find:
- `_SPA_ROUTES = {"/"}` near top of file.
- `_SPA_DIST = os.path.join(...)` near top.
- `def index()` that reads `webui/dist/index.html`.
- `def newscan()` that renders `newscan.tmpl`.
- `def clonescan(self, id)` that renders `newscan.tmpl` with pre-filled values.

- [ ] **Step 2: Add `_serve_spa_shell()` helper + refactor `index()`**

Locate the `index()` method. Replace it + add the helper above it (still inside the class). Expected shape:

```python
def _serve_spa_shell(self) -> str:
    """Serve the SPA's index.html shell, or a dev-friendly fallback
    if the Vite bundle is missing.

    Shared by every SPA-owned route handler. Adding a new SPA page
    is `return self._serve_spa_shell()` in the route's @cherrypy.expose
    method.
    """
    index_path = os.path.join(_SPA_DIST, "index.html")
    if not os.path.isfile(index_path):
        return (
            f"<html><body><h1>SpiderFoot</h1>"
            f"<p>Web UI bundle not found at {_SPA_DIST}. Run "
            f"<code>cd webui &amp;&amp; npm run build</code> "
            f"or use the dev server on port 5173.</p>"
            f"</body></html>"
        )
    with open(index_path, encoding="utf-8") as fh:
        return fh.read()

@cherrypy.expose
def index(self: 'SpiderFootWebUi') -> str:
    """Serve the SPA shell at /."""
    return self._serve_spa_shell()
```

- [ ] **Step 3: Replace `newscan()` body**

Find the `@cherrypy.expose def newscan(...)` method (currently renders Mako). Replace its body:

```python
@cherrypy.expose
def newscan(self: 'SpiderFootWebUi') -> str:
    """Serve the SPA shell at /newscan.

    Milestone 2 moved the scan-creation form into the SPA. See
    webui/src/pages/NewScanPage.tsx.
    """
    return self._serve_spa_shell()
```

Leave existing imports alone; no new ones needed.

- [ ] **Step 4: Remove `clonescan()`**

Find the `@cherrypy.expose def clonescan(self, id)` method (currently renders `newscan.tmpl` with pre-filled values). Delete the entire method — decorator + def line + body.

Check for other usages of `clonescan` by string:

```bash
grep -nE "clonescan" sfwebui.py
```

Should be zero after the deletion.

- [ ] **Step 5: Add `/newscan` to `_SPA_ROUTES`**

Find the line:
```python
_SPA_ROUTES = {"/"}
```

Replace with:
```python
_SPA_ROUTES = {"/", "/newscan"}
```

(The set is documentation for human readers; CherryPy routes by method name. Still keeping it in sync with reality.)

- [ ] **Step 6: Delete `test_clonescan` from unit tests**

Edit `test/unit/test_spiderfootwebui.py`. Find:

```python
def test_clonescan(self):
    """
    Test clonescan(self, id)
    """
    opts = self.default_options
    opts['__modules__'] = dict()
    sfwebui = SpiderFootWebUi(self.web_default_options, opts)
    clone_scan = sfwebui.clonescan("example scan instance")
    self.assertIsInstance(clone_scan, str)
```

Delete the entire method (decorator if present, `def` line, docstring, body, and the blank line after).

- [ ] **Step 7: Delete `test_clonescan` from integration tests**

Edit `test/integration/test_sfwebui.py`. Find:

```python
def test_clonescan(self):
    self.getPage("/clonescan?id=doesnotexist")
    self.assertStatus('200 OK')
    self.assertInBody("Invalid scan ID.")
```

Delete the entire method.

- [ ] **Step 8: Update `test_newscan_returns_200`**

In `test/integration/test_sfwebui.py`, find:

```python
def test_newscan_returns_200(self):
    self.getPage("/newscan")
    self.assertStatus('200 OK')
    self.assertInBody("Scan Name")
    self.assertInBody("Scan Target")
```

Replace with:

```python
def test_newscan_returns_200(self):
    self.getPage("/newscan")
    self.assertStatus('200 OK')
    # The SPA shell is served — the Vite bundle may be present
    # (real build) or missing (test env without webui build), so
    # accept either the SPA bundle marker or the dev-fallback page.
    body = self.body.decode() if isinstance(self.body, bytes) else self.body
    self.assertTrue(
        '<div id="root"></div>' in body or 'Web UI bundle not found' in body,
        msg=f"Unexpected /newscan body: {body[:300]}"
    )
```

(The `index()` integration test at nearby lines uses the same pattern already — if it doesn't, also update that test to match, and note it in the commit.)

- [ ] **Step 9: Run pytest to confirm no regressions**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -5
```

Expected: 1459 passed + 35 skipped (one less than baseline because we deleted one clonescan unit test and one clonescan integration test, minus one if the no-op `test_newscan` still exists, so exact count is 1458 or 1459 — check after and adjust the commit message accordingly).

- [ ] **Step 10: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add sfwebui.py test/unit/test_spiderfootwebui.py test/integration/test_sfwebui.py
git commit -m "$(cat <<'EOF'
webui: newscan handler serves SPA shell; retire clonescan

Factors the index()-handler file-read + fallback HTML into a
_serve_spa_shell() helper so every SPA-owned route can be a
one-liner: `return self._serve_spa_shell()`. newscan() becomes
the second caller; _SPA_ROUTES is extended to {"/" , "/newscan"}
for reader documentation.

clonescan() is removed — no reachable caller once milestone 1
retired the Mako scan list with its Clone button. Clone UX +
JSON endpoint land as a future milestone (see BACKLOG.md).
test_clonescan unit + integration tests deleted; test_newscan
integration test updated to assert SPA-shell response.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Backend — extend `/modules` with `api_key`

**Files:**
- Modify: `sfwebui.py` — extend `modules()` handler.

- [ ] **Step 1: Write a failing integration test first**

Edit `test/integration/test_sfwebui.py`. Find the existing `test_modules` method (or similar — grep for `def test_modules`); if none exists, add:

```python
def test_modules_returns_api_key_flag(self):
    """Modules JSON should include an api_key bool flag for each module."""
    self.getPage("/modules")
    self.assertStatus('200 OK')
    body = json.loads(self.body)
    self.assertIsInstance(body, list)
    self.assertGreater(len(body), 0)
    first = body[0]
    self.assertIn('name', first)
    self.assertIn('descr', first)
    self.assertIn('api_key', first)
    self.assertIsInstance(first['api_key'], bool)
```

Place this alongside the other `test_modules*` tests in that file. Check existing imports for `json` — if missing, add `import json` at the top.

- [ ] **Step 2: Run the test and verify it fails**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest test/integration/test_sfwebui.py::TestSpiderFootWebUiRoutes::test_modules_returns_api_key_flag -v 2>&1 | tail -10
```

Expected: FAIL with `KeyError: 'api_key'` or `AssertionError: 'api_key' not found`.

- [ ] **Step 3: Extend `modules()` in `sfwebui.py`**

Find the `def modules(self: 'SpiderFootWebUi') -> list` method. Inside the `for m in modinfo:` loop, extend the dict literal:

Before:
```python
ret.append({'name': m, 'descr': self.config['__modules__'][m]['descr']})
```

After:
```python
opts = self.config['__modules__'][m].get('opts', {})
api_key = any('api_key' in k for k in opts)
ret.append({
    'name': m,
    'descr': self.config['__modules__'][m]['descr'],
    'api_key': api_key,
})
```

- [ ] **Step 4: Run the test and verify it passes**

```bash
python3 -m pytest test/integration/test_sfwebui.py::TestSpiderFootWebUiRoutes::test_modules_returns_api_key_flag -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite — no regressions**

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -5
```

Expected: +1 passed vs. Task 1 completion.

- [ ] **Step 6: Commit**

```bash
git add sfwebui.py test/integration/test_sfwebui.py
git commit -m "$(cat <<'EOF'
webui: /modules JSON gains api_key flag

Each module object now has api_key: bool derived from whether any
opt key contains "api_key". The SPA's NewScanPage uses this to
render a lock icon next to modules that need an API key before
they can run.

Additive, non-breaking for sfcli.py (which reads only name/descr).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Backend — `/startscan` JSON success branch

**Files:**
- Modify: `sfwebui.py` — add JSON success branch to `startscan()`.
- Modify: `test/integration/test_sfwebui.py` — add a JSON success test.

- [ ] **Step 1: Read the current `startscan()` end of function to understand success path**

```bash
grep -n "def startscan\|HTTPRedirect.*scaninfo\|scanId" sfwebui.py | head -20
```

You're looking for the block that eventually raises `cherrypy.HTTPRedirect(f"{self.docroot}/scaninfo?id={scanId}")` after the scan is kicked off.

- [ ] **Step 2: Write the failing JSON success test**

Edit `test/integration/test_sfwebui.py`. Add:

```python
def test_startscan_json_accept_returns_success_and_scan_id(self):
    """When Accept: application/json is set and all params are valid,
    /startscan returns ["SUCCESS", <scanId>] instead of redirecting.
    """
    headers = [("Accept", "application/json")]
    # Use modulelist with a single safe module to minimize side effects.
    self.getPage(
        "/startscan?scanname=sparkscan&scantarget=spiderfoot.net"
        "&modulelist=sfp_countryname&typelist=&usecase=",
        headers=headers,
    )
    self.assertStatus('200 OK')
    body = json.loads(self.body)
    self.assertIsInstance(body, list)
    self.assertEqual(body[0], "SUCCESS")
    self.assertIsInstance(body[1], str)
    self.assertTrue(len(body[1]) > 0)
```

Place it in the same class as the other startscan tests.

- [ ] **Step 3: Run — expect failure**

```bash
python3 -m pytest test/integration/test_sfwebui.py::TestSpiderFootWebUiRoutes::test_startscan_json_accept_returns_success_and_scan_id -v 2>&1 | tail -15
```

Expected: FAIL — currently `startscan` raises `HTTPRedirect` even when `Accept: application/json`, so the test will either see a 303 redirect or assertion failure.

- [ ] **Step 4: Add JSON success branch**

Find the end of `startscan()` where the successful redirect is raised. You'll see something like:

```python
raise cherrypy.HTTPRedirect(f"{self.docroot}/scaninfo?id={scanId}")
```

Just before that line, add:

```python
accept = cherrypy.request.headers.get('Accept') or ''
if 'application/json' in accept:
    cherrypy.response.headers['Content-Type'] = "application/json; charset=utf-8"
    return json.dumps(["SUCCESS", scanId]).encode('utf-8')
```

Keep the existing `HTTPRedirect` raise afterwards for the HTML form-submit path.

- [ ] **Step 5: Run the test — expect pass**

```bash
python3 -m pytest test/integration/test_sfwebui.py::TestSpiderFootWebUiRoutes::test_startscan_json_accept_returns_success_and_scan_id -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 6: Run the full suite — confirm nothing broke**

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -5
```

Expected: +1 passed vs. Task 2 completion.

- [ ] **Step 7: Commit**

```bash
git add sfwebui.py test/integration/test_sfwebui.py
git commit -m "$(cat <<'EOF'
webui: /startscan returns JSON SUCCESS when Accept is JSON

Symmetric with the existing JSON error path — when the caller sets
Accept: application/json and the scan has been kicked off,
/startscan now returns ["SUCCESS", scanId] instead of raising an
HTTPRedirect to /scaninfo. The SPA uses this to navigate via
window.location.href rather than losing control in a POST->303.

Legacy HTML form posts (no Accept header) still get the 303
redirect, so sfcli.py and the (deleted, not yet replaced) Mako
form path are unaffected.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Frontend — types + API layer

**Files:**
- Modify: `webui/src/types.ts` — add `Module`, `EventType`, `SelectionMode`, `UseCase`.
- Create: `webui/src/api/modules.ts` — `listModules()`, `listEventTypes()`.
- Modify: `webui/src/api/scans.ts` — add `startScan()`.
- Modify: `webui/src/api/scans.test.ts` — add startScan tests.
- Create: `webui/src/api/modules.test.ts`.

- [ ] **Step 1: Extend `webui/src/types.ts`**

Append to the existing file:

```typescript
export type Module = {
  name: string;
  descr: string;
  api_key: boolean;
};

export type EventType = {
  id: string;
  label: string;
};

export type SelectionMode = 'usecase' | 'type' | 'module';

export type UseCase = 'all' | 'Footprint' | 'Investigate' | 'Passive';
```

- [ ] **Step 2: Create `webui/src/api/modules.ts`**

```typescript
import { fetchJson } from './client';
import type { Module, EventType } from '../types';

export async function listModules(): Promise<Module[]> {
  const rows = await fetchJson<Module[]>('/modules');
  // Sort client-side for stable display. Server sorts by name already,
  // but we can't rely on that contract.
  return rows.slice().sort((a, b) => a.name.localeCompare(b.name));
}

export async function listEventTypes(): Promise<EventType[]> {
  // /eventtypes returns [[label, id], ...] — map to typed objects.
  const rows = await fetchJson<[string, string][]>('/eventtypes');
  return rows.map(([label, id]) => ({ id, label }));
}
```

- [ ] **Step 3: Extend `webui/src/api/scans.ts`**

Append (after the existing `deleteScan`):

```typescript
export type StartScanParams = {
  scanName: string;
  scanTarget: string;
  mode: import('../types').SelectionMode;
  usecase: import('../types').UseCase;
  moduleList: string[];  // module names; empty array when mode != 'module'
  typeList: string[];    // event type ids; empty array when mode != 'type'
};

export async function startScan(params: StartScanParams): Promise<string> {
  const body = new URLSearchParams();
  body.set('scanname', params.scanName);
  body.set('scantarget', params.scanTarget);
  body.set(
    'modulelist',
    params.mode === 'module' ? params.moduleList.join(',') : '',
  );
  body.set(
    'typelist',
    params.mode === 'type' ? params.typeList.map((t) => `type_${t}`).join(',') : '',
  );
  body.set('usecase', params.mode === 'usecase' ? params.usecase : '');

  const result = await fetchJson<[string, string]>('/startscan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  // Server returns ["SUCCESS", <scanId>] or ["ERROR", <message>].
  if (!Array.isArray(result) || result.length < 2) {
    throw new Error(`Malformed /startscan response: ${JSON.stringify(result)}`);
  }
  if (result[0] !== 'SUCCESS') {
    throw new Error(result[1] ?? 'Unknown error starting scan');
  }
  return result[1];
}
```

- [ ] **Step 4: Create `webui/src/api/modules.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { listModules, listEventTypes } from './modules';

describe('listModules', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns typed Module[] with api_key flag preserved', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          { name: 'sfp_alpha', descr: 'first', api_key: false },
          { name: 'sfp_beta', descr: 'second', api_key: true },
        ]),
        { status: 200 },
      ),
    );
    const modules = await listModules();
    expect(modules).toHaveLength(2);
    expect(modules[0]).toEqual({ name: 'sfp_alpha', descr: 'first', api_key: false });
    expect(modules[1].api_key).toBe(true);
  });

  it('sorts modules by name', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          { name: 'sfp_z', descr: 'z', api_key: false },
          { name: 'sfp_a', descr: 'a', api_key: false },
        ]),
        { status: 200 },
      ),
    );
    const modules = await listModules();
    expect(modules.map((m) => m.name)).toEqual(['sfp_a', 'sfp_z']);
  });
});

describe('listEventTypes', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('maps [label, id] tuples to typed EventType objects', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          ['Domain Name', 'DOMAIN_NAME'],
          ['IP Address', 'IP_ADDRESS'],
        ]),
        { status: 200 },
      ),
    );
    const types = await listEventTypes();
    expect(types).toEqual([
      { id: 'DOMAIN_NAME', label: 'Domain Name' },
      { id: 'IP_ADDRESS', label: 'IP Address' },
    ]);
  });
});
```

- [ ] **Step 5: Add startScan test to `webui/src/api/scans.test.ts`**

At the bottom of the file (inside the same file, as a new `describe`):

```typescript
describe('startScan', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('returns the scanId on SUCCESS response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS', 'abc-guid']), { status: 200 }),
    );
    const scanId = await startScan({
      scanName: 'test',
      scanTarget: 'example.com',
      mode: 'usecase',
      usecase: 'all',
      moduleList: [],
      typeList: [],
    });
    expect(scanId).toBe('abc-guid');
  });

  it('throws the server message on ERROR response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['ERROR', 'Unrecognised target type.']), { status: 200 }),
    );
    await expect(
      startScan({
        scanName: 'test',
        scanTarget: 'not-a-real-target',
        mode: 'usecase',
        usecase: 'all',
        moduleList: [],
        typeList: [],
      }),
    ).rejects.toThrow('Unrecognised target type.');
  });

  it('sends module mode with modulelist populated and other lists empty', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS', 'abc']), { status: 200 }),
    );
    await startScan({
      scanName: 't',
      scanTarget: 'x',
      mode: 'module',
      usecase: 'all',
      moduleList: ['sfp_alpha', 'sfp_beta'],
      typeList: [],
    });
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('modulelist')).toBe('sfp_alpha,sfp_beta');
    expect(body.get('typelist')).toBe('');
    expect(body.get('usecase')).toBe('');
  });

  it('sends type mode with typelist prefixed "type_" and other lists empty', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS', 'abc']), { status: 200 }),
    );
    await startScan({
      scanName: 't',
      scanTarget: 'x',
      mode: 'type',
      usecase: 'all',
      moduleList: [],
      typeList: ['DOMAIN_NAME', 'IP_ADDRESS'],
    });
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('typelist')).toBe('type_DOMAIN_NAME,type_IP_ADDRESS');
    expect(body.get('modulelist')).toBe('');
  });
});
```

Import `startScan` at the top of the file alongside `listScans, deleteScan`.

- [ ] **Step 6: Run all Vitest — confirm 8 existing + 6 new pass**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -10
```

Expected: ~18 tests total pass (12 from milestone 1 + 2 new modules tests + 4 new startScan tests = 18).

- [ ] **Step 7: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/types.ts webui/src/api/modules.ts webui/src/api/modules.test.ts webui/src/api/scans.ts webui/src/api/scans.test.ts
git commit -m "$(cat <<'EOF'
webui: typed API for /modules, /eventtypes, /startscan

listModules() returns Module[] with the new api_key flag.
listEventTypes() maps the [label, id] tuple response to typed
objects. startScan() builds the application/x-www-form-urlencoded
body conditionally based on the selected mode — module/type/usecase
are mutually exclusive client-side, matching the server's branch
ordering in sfwebui.startscan().

Vitest covers SUCCESS/ERROR unwrap, module-mode serialization,
type-mode "type_" prefix, and empty fallbacks.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Frontend — UseCaseTab + ModuleTab + TypeTab components

**Files:**
- Create: `webui/src/components/UseCaseTab.tsx`, `ModuleTab.tsx`, `TypeTab.tsx`.

- [ ] **Step 1: Check `@tabler/icons-react` availability**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm ls @tabler/icons-react 2>&1 | head -3
```

If absent (`(empty)` or error), install it:

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm install @tabler/icons-react
```

- [ ] **Step 2: Create `webui/src/components/UseCaseTab.tsx`**

```tsx
import { Radio, Stack, Text } from '@mantine/core';
import type { UseCase } from '../types';

const USECASE_OPTIONS: { value: UseCase; label: string; description: string }[] = [
  {
    value: 'all',
    label: 'All',
    description:
      'Get anything and everything about the target. All SpiderFoot modules will be enabled (slow) but every possible piece of information about the target will be obtained and analysed.',
  },
  {
    value: 'Footprint',
    label: 'Footprint',
    description:
      "Understand what information this target exposes to the Internet. Gain an understanding about the target's network perimeter, associated identities and other information that is obtained through a lot of web crawling and search engine use.",
  },
  {
    value: 'Investigate',
    label: 'Investigate',
    description:
      "Best for when you suspect the target to be malicious but need more information. Some basic footprinting will be performed in addition to querying of blacklists and other sources that may have information about your target's maliciousness.",
  },
  {
    value: 'Passive',
    label: 'Passive',
    description:
      "When you don't want the target to even suspect they are being investigated. As much information will be gathered without touching the target or their affiliates, therefore only modules that do not touch the target will be enabled.",
  },
];

export function UseCaseTab({
  value,
  onChange,
}: {
  value: UseCase;
  onChange: (v: UseCase) => void;
}) {
  return (
    <Radio.Group value={value} onChange={(v) => onChange(v as UseCase)}>
      <Stack gap="md">
        {USECASE_OPTIONS.map((opt) => (
          <Radio
            key={opt.value}
            value={opt.value}
            label={
              <>
                <Text fw={600}>{opt.label}</Text>
                <Text size="sm" c="dimmed">
                  {opt.description}
                </Text>
              </>
            }
          />
        ))}
      </Stack>
    </Radio.Group>
  );
}
```

- [ ] **Step 3: Create `webui/src/components/ModuleTab.tsx`**

```tsx
import { useMemo } from 'react';
import {
  Button,
  Checkbox,
  Group,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { IconKey } from '@tabler/icons-react';
import type { Module } from '../types';

export function ModuleTab({
  modules,
  selected,
  onChange,
  filter,
  onFilterChange,
}: {
  modules: Module[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  filter: string;
  onFilterChange: (v: string) => void;
}) {
  const filtered = useMemo(
    () => modules.filter((m) => m.name.toLowerCase().includes(filter.toLowerCase())),
    [modules, filter],
  );

  const toggle = (name: string) => {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  };

  const selectAll = () => onChange(new Set(modules.map((m) => m.name)));
  const deselectAll = () => onChange(new Set());

  return (
    <Stack>
      <Group>
        <TextInput
          placeholder="Filter modules..."
          value={filter}
          onChange={(e) => onFilterChange(e.currentTarget.value)}
          style={{ flex: 1 }}
          aria-label="Filter modules"
        />
        <Button variant="light" onClick={selectAll}>
          Select All
        </Button>
        <Button variant="light" onClick={deselectAll}>
          De-Select All
        </Button>
      </Group>

      {filtered.length === 0 ? (
        <Text c="dimmed" ta="center" mt="md">
          No modules match "{filter}".
        </Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 40 }} />
              <Table.Th>Module</Table.Th>
              <Table.Th>Description</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map((m) => (
              <Table.Tr key={m.name}>
                <Table.Td>
                  <Checkbox
                    checked={selected.has(m.name)}
                    onChange={() => toggle(m.name)}
                    aria-label={`Toggle ${m.name}`}
                  />
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <Text>{m.name}</Text>
                    {m.api_key && (
                      <Tooltip label="Needs API key">
                        <IconKey size={14} />
                      </Tooltip>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{m.descr}</Text>
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

- [ ] **Step 4: Create `webui/src/components/TypeTab.tsx`**

```tsx
import { useMemo } from 'react';
import {
  Button,
  Checkbox,
  Group,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import type { EventType } from '../types';

export function TypeTab({
  types,
  selected,
  onChange,
  filter,
  onFilterChange,
}: {
  types: EventType[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  filter: string;
  onFilterChange: (v: string) => void;
}) {
  const filtered = useMemo(
    () =>
      types.filter((t) => t.label.toLowerCase().includes(filter.toLowerCase())),
    [types, filter],
  );

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  };

  const selectAll = () => onChange(new Set(types.map((t) => t.id)));
  const deselectAll = () => onChange(new Set());

  return (
    <Stack>
      <Group>
        <TextInput
          placeholder="Filter types..."
          value={filter}
          onChange={(e) => onFilterChange(e.currentTarget.value)}
          style={{ flex: 1 }}
          aria-label="Filter event types"
        />
        <Button variant="light" onClick={selectAll}>
          Select All
        </Button>
        <Button variant="light" onClick={deselectAll}>
          De-Select All
        </Button>
      </Group>

      {filtered.length === 0 ? (
        <Text c="dimmed" ta="center" mt="md">
          No types match "{filter}".
        </Text>
      ) : (
        <SimpleGrid cols={2}>
          {filtered.map((t) => (
            <Checkbox
              key={t.id}
              label={t.label}
              checked={selected.has(t.id)}
              onChange={() => toggle(t.id)}
            />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
```

- [ ] **Step 5: Build to confirm TS compiles**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -10
```

Expected: build succeeds. If `@tabler/icons-react` types aren't found, double-check the install from Step 1 landed in `package.json` dependencies.

- [ ] **Step 6: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/components/UseCaseTab.tsx webui/src/components/ModuleTab.tsx webui/src/components/TypeTab.tsx webui/package.json webui/package-lock.json
git commit -m "$(cat <<'EOF'
webui: tab components for the new-scan form

UseCaseTab: Mantine Radio.Group wrapping the 4 legacy options
(All/Footprint/Investigate/Passive) with per-option description.
Default value is 'all' — set by the consumer.

ModuleTab: TextInput filter + Select All / De-Select All buttons
+ Mantine Table of checkboxes. Lock icon (@tabler/icons IconKey)
next to modules with api_key: true. Client-side substring filter
on module name, case-insensitive.

TypeTab: TextInput filter + Select All / De-Select All + two-column
SimpleGrid of checkboxes. Preserves the dense current layout in
fewer SLOC than the Mako row/col HTML.

All three components are controlled — state lives in the
composing NewScanPage (Task 6).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Frontend — NewScanPage + router + Vitest

**Files:**
- Create: `webui/src/pages/NewScanPage.tsx`, `webui/src/pages/NewScanPage.test.tsx`.
- Modify: `webui/src/router.tsx`.

- [ ] **Step 1: Create `webui/src/pages/NewScanPage.tsx`**

```tsx
import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Accordion,
  Alert,
  Button,
  Group,
  Loader,
  Stack,
  Tabs,
  TextInput,
  Title,
  Text,
} from '@mantine/core';
import { listModules, listEventTypes } from '../api/modules';
import { startScan } from '../api/scans';
import { UseCaseTab } from '../components/UseCaseTab';
import { ModuleTab } from '../components/ModuleTab';
import { TypeTab } from '../components/TypeTab';
import type { SelectionMode, UseCase } from '../types';

export function NewScanPage() {
  const [scanName, setScanName] = useState('');
  const [scanTarget, setScanTarget] = useState('');
  const [mode, setMode] = useState<SelectionMode>('usecase');
  const [usecase, setUsecase] = useState<UseCase>('all');
  const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set());
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());
  const [moduleFilter, setModuleFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  const modulesQuery = useQuery({
    queryKey: ['modules'],
    queryFn: listModules,
    staleTime: Infinity,  // module list rarely changes at runtime
  });
  const typesQuery = useQuery({
    queryKey: ['eventtypes'],
    queryFn: listEventTypes,
    staleTime: Infinity,
  });

  // Default: all modules + all types checked, matching legacy Mako behavior.
  useEffect(() => {
    if (modulesQuery.data && selectedModules.size === 0) {
      setSelectedModules(new Set(modulesQuery.data.map((m) => m.name)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modulesQuery.data]);

  useEffect(() => {
    if (typesQuery.data && selectedTypes.size === 0) {
      setSelectedTypes(new Set(typesQuery.data.map((t) => t.id)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typesQuery.data]);

  const submitMutation = useMutation({
    mutationFn: startScan,
    onSuccess: (scanId) => {
      window.location.href = `/scaninfo?id=${scanId}`;
    },
  });

  const submitDisabled =
    !scanName.trim() ||
    !scanTarget.trim() ||
    (mode === 'module' && selectedModules.size === 0) ||
    (mode === 'type' && selectedTypes.size === 0) ||
    submitMutation.isPending;

  if (modulesQuery.isLoading || typesQuery.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }

  if (modulesQuery.isError || typesQuery.isError) {
    const err = (modulesQuery.error ?? typesQuery.error) as Error;
    return (
      <Alert color="red" title="Failed to load form data" mt="md">
        {err.message}
        <Group mt="sm">
          <Button
            size="xs"
            onClick={() => {
              modulesQuery.refetch();
              typesQuery.refetch();
            }}
          >
            Retry
          </Button>
        </Group>
      </Alert>
    );
  }

  const handleSubmit = () => {
    submitMutation.mutate({
      scanName,
      scanTarget,
      mode,
      usecase,
      moduleList: Array.from(selectedModules),
      typeList: Array.from(selectedTypes),
    });
  };

  return (
    <Stack>
      <Title order={2}>New Scan</Title>

      {submitMutation.isError && (
        <Alert color="red" title="Failed to start scan">
          {(submitMutation.error as Error).message}
        </Alert>
      )}

      <Group grow>
        <TextInput
          label="Scan Name"
          placeholder="The name of this scan."
          value={scanName}
          onChange={(e) => setScanName(e.currentTarget.value)}
          required
        />
        <TextInput
          label="Scan Target"
          placeholder="The target of your scan."
          value={scanTarget}
          onChange={(e) => setScanTarget(e.currentTarget.value)}
          required
        />
      </Group>

      <Accordion variant="separated">
        <Accordion.Item value="target-types">
          <Accordion.Control>
            Target types — what can I enter?
          </Accordion.Control>
          <Accordion.Panel>
            <Text size="sm">
              SpiderFoot auto-detects the target type based on format:
              <br />
              <strong>Domain Name</strong>: example.com &nbsp;|&nbsp;
              <strong>IPv4 Address</strong>: 1.2.3.4 &nbsp;|&nbsp;
              <strong>IPv6 Address</strong>: 2606:4700:4700::1111 &nbsp;|&nbsp;
              <strong>Hostname/Sub-domain</strong>: abc.example.com
              <br />
              <strong>Subnet</strong>: 1.2.3.0/24 &nbsp;|&nbsp;
              <strong>Bitcoin Address</strong> &nbsp;|&nbsp;
              <strong>E-mail</strong>: bob@example.com &nbsp;|&nbsp;
              <strong>Phone Number</strong>: +12345678901 (E.164)
              <br />
              <strong>Human Name</strong>: "John Smith" (quoted) &nbsp;|&nbsp;
              <strong>Username</strong>: "jsmith2000" (quoted) &nbsp;|&nbsp;
              <strong>Network ASN</strong>: 1234
            </Text>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      <Tabs value={mode} onChange={(v) => setMode((v ?? 'usecase') as SelectionMode)}>
        <Tabs.List>
          <Tabs.Tab value="usecase">By Use Case</Tabs.Tab>
          <Tabs.Tab value="type">By Required Data</Tabs.Tab>
          <Tabs.Tab value="module">By Module</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="usecase" pt="md">
          <UseCaseTab value={usecase} onChange={setUsecase} />
        </Tabs.Panel>
        <Tabs.Panel value="type" pt="md">
          <TypeTab
            types={typesQuery.data ?? []}
            selected={selectedTypes}
            onChange={setSelectedTypes}
            filter={typeFilter}
            onFilterChange={setTypeFilter}
          />
        </Tabs.Panel>
        <Tabs.Panel value="module" pt="md">
          <ModuleTab
            modules={modulesQuery.data ?? []}
            selected={selectedModules}
            onChange={setSelectedModules}
            filter={moduleFilter}
            onFilterChange={setModuleFilter}
          />
        </Tabs.Panel>
      </Tabs>

      <Group justify="flex-end">
        <Button
          color="red"
          disabled={submitDisabled}
          loading={submitMutation.isPending}
          onClick={handleSubmit}
        >
          Run Scan Now
        </Button>
      </Group>
    </Stack>
  );
}
```

- [ ] **Step 2: Modify `webui/src/router.tsx`**

Replace the contents with:

```tsx
import { createBrowserRouter } from 'react-router-dom';
import { ScanListPage } from './pages/ScanListPage';
import { NewScanPage } from './pages/NewScanPage';

export const router = createBrowserRouter([
  { path: '/', element: <ScanListPage /> },
  { path: '/newscan', element: <NewScanPage /> },
]);
```

- [ ] **Step 3: Create `webui/src/pages/NewScanPage.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { NewScanPage } from './NewScanPage';

describe('NewScanPage', () => {
  const originalFetch = globalThis.fetch;
  const originalLocation = window.location;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
    // Replace window.location with a mutable stand-in
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, href: '' },
      writable: true,
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
      writable: true,
    });
  });

  function renderPage() {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <NewScanPage />
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockApi(modules: unknown, types: unknown) {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url === '/modules') {
        return Promise.resolve(
          new Response(JSON.stringify(modules), { status: 200 }),
        );
      }
      if (url === '/eventtypes') {
        return Promise.resolve(
          new Response(JSON.stringify(types), { status: 200 }),
        );
      }
      if (url === '/startscan') {
        return Promise.resolve(
          new Response(JSON.stringify(['SUCCESS', 'new-guid']), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  it('renders form, modules, and event types on load', async () => {
    mockApi(
      [
        { name: 'sfp_alpha', descr: 'alpha desc', api_key: false },
        { name: 'sfp_beta', descr: 'beta desc', api_key: true },
      ],
      [['Domain Name', 'DOMAIN_NAME']],
    );
    renderPage();

    expect(await screen.findByLabelText('Scan Name')).toBeInTheDocument();
    expect(screen.getByLabelText('Scan Target')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /By Use Case/ })).toBeInTheDocument();

    // Switch to Module tab and confirm both modules are listed
    await userEvent.click(screen.getByRole('tab', { name: /By Module/ }));
    expect(await screen.findByText('sfp_alpha')).toBeInTheDocument();
    expect(screen.getByText('sfp_beta')).toBeInTheDocument();
  });

  it('disables Run Scan when scan name is empty', async () => {
    mockApi([], []);
    renderPage();
    const run = await screen.findByRole('button', { name: 'Run Scan Now' });
    expect(run).toBeDisabled();
  });

  it('submits with modulelist when in module mode', async () => {
    mockApi(
      [{ name: 'sfp_x', descr: 'x', api_key: false }],
      [['Domain Name', 'DOMAIN_NAME']],
    );
    renderPage();
    await screen.findByLabelText('Scan Name');

    await userEvent.type(screen.getByLabelText('Scan Name'), 'myscan');
    await userEvent.type(screen.getByLabelText('Scan Target'), 'example.com');
    await userEvent.click(screen.getByRole('tab', { name: /By Module/ }));
    await screen.findByText('sfp_x');

    const run = screen.getByRole('button', { name: 'Run Scan Now' });
    await userEvent.click(run);

    await waitFor(() => {
      expect(window.location.href).toBe('/scaninfo?id=new-guid');
    });
    const calls = (globalThis.fetch as Mock).mock.calls.filter(
      (c) => c[0] === '/startscan',
    );
    expect(calls).toHaveLength(1);
    const body = new URLSearchParams(calls[0][1].body);
    expect(body.get('modulelist')).toBe('sfp_x');
    expect(body.get('typelist')).toBe('');
    expect(body.get('usecase')).toBe('');
  });

  it('surfaces an Alert when /startscan returns ERROR', async () => {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url === '/modules') return Promise.resolve(new Response('[]', { status: 200 }));
      if (url === '/eventtypes') return Promise.resolve(new Response('[]', { status: 200 }));
      if (url === '/startscan') {
        return Promise.resolve(
          new Response(JSON.stringify(['ERROR', 'Unrecognised target type.']), {
            status: 200,
          }),
        );
      }
      return Promise.reject(new Error('unexpected'));
    });
    renderPage();
    await screen.findByLabelText('Scan Name');
    await userEvent.type(screen.getByLabelText('Scan Name'), 't');
    await userEvent.type(screen.getByLabelText('Scan Target'), 'bogus');
    await userEvent.click(screen.getByRole('button', { name: 'Run Scan Now' }));
    expect(
      await screen.findByText('Unrecognised target type.'),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run Vitest — 18 + 4 = 22 tests pass**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -10
```

Expected: 22 tests passing.

- [ ] **Step 5: Build — confirm TS compiles**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -10
```

Expected: success.

- [ ] **Step 6: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/NewScanPage.tsx webui/src/pages/NewScanPage.test.tsx webui/src/router.tsx
git commit -m "$(cat <<'EOF'
webui: NewScanPage composes the /newscan form

Controlled-state top-level form: name + target inputs, collapsible
"Target types" Accordion (preserves Mako help text), Mantine Tabs
hosting UseCaseTab / TypeTab / ModuleTab. Submit is guarded by
name+target+selection non-empty.

Module / type lists fetched once via TanStack Query (staleTime
Infinity — they rarely change at runtime). Defaults: all modules
checked, all types checked, usecase='all'. Tab switch doesn't
clear the other tabs' selections; only the active tab's selection
is submitted. This mirrors the Mako form's branch ordering in
sfwebui.startscan().

Success navigates via window.location.href to /scaninfo (legacy
Mako page). Error renders an inline Alert.

Router now has two routes: / and /newscan.

4 Vitest cases cover: initial render, submit-disabled-when-empty,
module-mode body serialization + success navigation, error Alert.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Retirements + Playwright + Robot cleanup

**Files:**
- Delete: `spiderfoot/templates/newscan.tmpl`.
- Delete: `spiderfoot/static/js/spiderfoot.newscan.js`.
- Modify: `test/acceptance/scan.robot` — remove the `New scan page should render` keyword.
- Create: `webui/tests/e2e/03-new-scan.spec.ts`.

- [ ] **Step 1: Delete the Mako template + companion JS**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git rm spiderfoot/templates/newscan.tmpl spiderfoot/static/js/spiderfoot.newscan.js
```

- [ ] **Step 2: Check for any lingering references**

```bash
grep -rnE "newscan\.tmpl|spiderfoot\.newscan\.js" --include="*.py" --include="*.tmpl" --include="*.robot" --include="*.html" .
```

Expected: no matches. If anything shows up, remove it.

- [ ] **Step 3: Remove `New scan page should render` keyword from `test/acceptance/scan.robot`**

Edit the file. Find:

```
New scan page should render
    Element Should Be Visible            id:scanname
    Element Should Be Visible            id:scantarget
    Element Should Be Visible            id:usetab
    Element Should Be Visible            id:typetab
    Element Should Be Visible            id:moduletab
```

Delete the keyword definition (6 lines including the header). Also search for references to it in other test cases:

```bash
grep -n "New scan page should render" test/acceptance/scan.robot
```

The "Main navigation pages should render correctly" test case (rewritten in milestone 1 to open `${URL}/newscan` directly) will reference this keyword via a `New scan page should render` line in its body — remove that line too. The test case can still verify settings navigation.

- [ ] **Step 4: Create `webui/tests/e2e/03-new-scan.spec.ts`**

```typescript
import { test, expect } from '@playwright/test';

// Runs after 02-empty-state.spec.ts — the empty-state spec wipes
// tbl_scan_instance, so /newscan still loads (it doesn't depend on
// scan data). This spec also kicks off a new scan, so the fixture
// DB gains one row afterwards; that's fine because Playwright's
// webServer reseeds per run.

test.describe('New scan form', () => {
  test('renders all three selection tabs after load', async ({ page }) => {
    await page.goto('/newscan');
    await expect(page.getByRole('heading', { name: 'New Scan' })).toBeVisible();
    await expect(page.getByRole('tab', { name: /By Use Case/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /By Required Data/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /By Module/ })).toBeVisible();
  });

  test('module filter narrows the visible list', async ({ page }) => {
    await page.goto('/newscan');
    await page.getByRole('tab', { name: /By Module/ }).click();
    // Ensure at least a known module appears before filtering
    await expect(page.getByText('sfp_countryname')).toBeVisible();
    await page.getByLabel('Filter modules').fill('country');
    await expect(page.getByText('sfp_countryname')).toBeVisible();
    await expect(page.getByText('sfp_dnsresolve')).not.toBeVisible();
  });

  test('submit kicks off a scan and redirects to scaninfo', async ({ page }) => {
    await page.goto('/newscan');
    await page.getByLabel('Scan Name').fill('playwright-newscan-smoke');
    await page.getByLabel('Scan Target').fill('spiderfoot.net');
    // Pick only sfp_countryname to keep the scan fast
    await page.getByRole('tab', { name: /By Module/ }).click();
    await page.getByLabel('Filter modules').fill('country');
    await page.getByRole('button', { name: 'De-Select All' }).click();
    await page.getByRole('checkbox', { name: 'Toggle sfp_countryname' }).click();

    await page.getByRole('button', { name: 'Run Scan Now' }).click();
    await page.waitForURL(/\/scaninfo\?id=.+/, { timeout: 10_000 });
  });
});
```

Note: the module checkbox selector uses the `aria-label` we set on the checkbox in `ModuleTab.tsx` (`Toggle <module name>`).

- [ ] **Step 5: Run Playwright specs**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run test:e2e 2>&1 | tail -20
```

Expected: 7 tests pass (3 from 01-scan-list + 1 from 02-empty-state + 3 new from 03-new-scan).

If the submit test fails with a timeout, bump `waitForURL` timeout to 30_000 — `sfp_countryname` on `spiderfoot.net` takes a few seconds.

- [ ] **Step 6: Full `./test/run` sanity check**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 22 Vitest + 7 Playwright + flake8 clean + pytest count = baseline + 2 (new api_key + startscan json tests) − 2 (deleted clonescan tests) = unchanged.

- [ ] **Step 7: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add test/acceptance/scan.robot webui/tests/e2e/03-new-scan.spec.ts
git rm spiderfoot/templates/newscan.tmpl spiderfoot/static/js/spiderfoot.newscan.js
git commit -m "$(cat <<'EOF'
webui: retire Mako newscan; add Playwright E2E for /newscan

Deletes spiderfoot/templates/newscan.tmpl (116 lines) +
spiderfoot/static/js/spiderfoot.newscan.js — both replaced by
webui/src/pages/NewScanPage.tsx.

test/acceptance/scan.robot loses the "New scan page should render"
keyword and its reference in Main navigation pages; 03-new-scan.spec.ts
replaces the coverage.

3 Playwright tests: renders all 3 tabs, filter narrows module list,
end-to-end submit lands on /scaninfo?id=...

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Docs refresh + final verification

**Files:**
- Modify: `CLAUDE.md` — update Web UI section's recipe.
- Modify: `docs/superpowers/BACKLOG.md` — mark milestone 2 shipped.

- [ ] **Step 1: Update `CLAUDE.md` Web UI section**

Find the existing `## Web UI` section (added in milestone 1). Update the "Adding a migrated page" recipe to reflect the new `_serve_spa_shell()` helper:

Replace step 3 of the recipe:

Before:
```
3. Add the path to `_SPA_ROUTES` in `sfwebui.py` and make sure `index()` (or a dedicated handler) serves the SPA shell for it.
```

After:
```
3. Add the path to `_SPA_ROUTES` in `sfwebui.py` for documentation, and replace the existing `@cherrypy.expose` handler's body with `return self._serve_spa_shell()`. The helper handles missing-bundle fallback.
```

Also append a line to the top paragraph indicating milestone 2 shipped:

Before:
```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestone 1 (2026-04-20) migrated the scan-list page (`/`); all other Mako pages (`/newscan`, `/scaninfo`, `/opts`, etc.) remain unchanged and reachable.
```

After:
```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1 and 2 (2026-04-20) migrated `/` (scan list) and `/newscan` (scan creation). Remaining Mako pages (`/scaninfo`, `/opts`, `/error`) are unchanged and reachable.
```

- [ ] **Step 2: Update `BACKLOG.md`**

Find the `### UI modernization — page-by-page migration` section. Update the "Foundation shipped" and "Remaining Mako pages" lines:

Before:
```
**Foundation shipped:** milestone 1 (2026-04-20) — scan-list page + full toolchain (Vite + React + Mantine + Vitest + Playwright). See `docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md` and `docs/superpowers/plans/2026-04-20-webui-spa-milestone-1.md`.

**Remaining Mako pages to migrate** (each its own spec + plan):
- `/newscan` (`newscan.tmpl`, ~116 lines) — scan creation form + module picker. Small.
- `/scaninfo?id=<guid>` (`scaninfo.tmpl`, ~905 lines) — the big one. Tabs for events, correlations, graph, log. Likely needs sub-milestones by tab.
- `/opts` (`opts.tmpl`, ~199 lines) — settings / API keys / global config.
- `/error` — tiny error page; can ride with the next migration.
```

After:
```
**Shipped:**
- Milestone 1 (2026-04-20) — `/` scan list + full toolchain (Vite + React + Mantine + Vitest + Playwright).
- Milestone 2 (2026-04-20) — `/newscan` scan creation form + three selection tabs + filterable module list. Retired `clonescan` handler (clone UI deferred).

Specs: `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2}-design.md`.

**Remaining Mako pages to migrate** (each its own spec + plan):
- `/scaninfo?id=<guid>` (`scaninfo.tmpl`, ~905 lines) — the big one. Tabs for events, correlations, graph, log. Likely needs sub-milestones by tab.
- `/opts` (`opts.tmpl`, ~199 lines) — settings / API keys / global config.
- `/error` — tiny error page; can ride with the next migration.
- Clone-scan UX: re-add a Clone action to the scan list menu, backed by a new JSON endpoint that returns the cloned scan's pre-fill payload. Targeted for the milestone that touches `/scaninfo` (natural entry point).
```

- [ ] **Step 3: Run `./test/run` one final time**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 22 Vitest + 7 Playwright + flake8 clean + pytest = milestone-1 baseline ± 0. All green.

- [ ] **Step 4: Commit docs**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — milestone 2 Web UI

CLAUDE.md Web UI section: updates the migration recipe to reference
the _serve_spa_shell() helper pattern, and notes milestones 1+2
shipped.

BACKLOG.md: marks milestone 2 shipped; moves /newscan out of the
"remaining" list; notes that the deferred clone-scan UX will land
with the /scaninfo milestone (natural entry point).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-2-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Milestone summary**

Report to the user:
- 8 commits landed (SPA-shell helper → /modules api_key → /startscan JSON → types+API → tab components → NewScanPage → retirements → docs).
- `/newscan` retired from Mako; SPA now owns both `/` and `/newscan`.
- 22 Vitest + 7 Playwright + flake8 clean + 1460 pytest (±0 — added 2 startscan/modules JSON tests, removed 2 clonescan tests).
- `clonescan` handler + Mako `newscan.tmpl` + `spiderfoot.newscan.js` all deleted.
- Follow-ups: Clone-scan UX (bundled into the /scaninfo milestone), remaining Mako pages (`/scaninfo`, `/opts`, `/error`).
