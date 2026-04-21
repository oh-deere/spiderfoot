# Web UI SPA — Milestone 5 (final sweep) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire every remaining Mako template, legacy JS/CSS bundle, and vendored `node_modules/`. Convert `self.error()` + `error_page_404` to plain-HTML helpers. Add the Clone-scan UX deferred from M2. After this milestone: no Mako, no jQuery, no vendored legacy deps.

**Architecture:** 6 tasks. Backend Mako purge lands first (keeps CI stable during the rest of the work), then the new `/clonescan` endpoint + Python test, then the frontend Clone wrapper (API + NewScanPage prefill + ScanListPage menu item), then the file-system retirement sweep + `/static` mount removal + Playwright, finally docs.

**Tech Stack:** Python 3.12 + CherryPy (unchanged). React 19, Mantine 9, TanStack Query 5, React Router 7, Vitest 2, Playwright 1.

**Spec:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-5-design.md`.

---

## File Structure

### Backend (Python)
- **Modify** `sfwebui.py` — drop Mako imports + `self.lookup`; rewrite `self.error()` + `error_page_404()` to inline HTML; add `/clonescan` JSON endpoint.
- **Modify** `sf.py` — remove the `/static` entry from `cherrypy.quickstart` config.
- **Modify** `test/integration/test_sfwebui.py` — update or remove assertions that grepped Mako-era strings; add 1 new `/clonescan` 404 test.
- **Modify** `test/unit/test_spiderfootwebui.py` — update any Mako-era HTML body assertions; update `test_error`.

### Frontend (React)
- **Modify** `webui/src/api/scans.ts` — add `fetchScanClone(id)`.
- **Modify** `webui/src/api/scans.test.ts` — 1 new Vitest case.
- **Modify** `webui/src/pages/NewScanPage.tsx` — read `?clone=<guid>`, fetch prefill, seed state.
- **Modify** `webui/src/pages/NewScanPage.test.tsx` — 1 new Vitest case.
- **Modify** `webui/src/pages/ScanListPage.tsx` — add `Clone` Menu.Item.

### Retirements (files removed)
- `spiderfoot/templates/HEADER.tmpl` (134 lines)
- `spiderfoot/templates/FOOTER.tmpl` (25 lines)
- `spiderfoot/templates/error.tmpl` (7 lines)
- `spiderfoot/templates/` (directory empty after above)
- `spiderfoot/static/js/spiderfoot.js` (198 lines)
- `spiderfoot/static/css/spiderfoot.css`
- `spiderfoot/static/css/dark.css`
- `spiderfoot/static/css/` (directory empty after above)
- `spiderfoot/static/package.json`
- `spiderfoot/static/package-lock.json` (if present)
- `spiderfoot/static/node_modules/` (entire directory)
- `spiderfoot/static/img/*` (after grep audit confirms no SPA references)

### E2E
- **Create** `webui/tests/e2e/08-clone-scan.spec.ts` — 1 case.

### Docs
- **Modify** `CLAUDE.md` — final state description.
- **Modify** `docs/superpowers/BACKLOG.md` — mark M5 shipped; the UI modernization section becomes a historical note.

---

## Context for the implementer

- **Branch:** master, direct commits. HEAD is `5796cd12` (M5 spec commit).
- **Baseline:** 69 Vitest + 15 Playwright + flake8 clean + 1464 pytest + 34 skipped.
- **Mako surface inventory** (gathered during brainstorming):
  - `from mako.lookup import TemplateLookup` — sfwebui.py:28
  - `from mako.template import Template` — sfwebui.py:29
  - `self.lookup = TemplateLookup(directories=[''])` — sfwebui.py:62 (in `__init__`)
  - `Template(filename='spiderfoot/templates/error.tmpl', ...)` — sfwebui.py:172 (`error_page_404`)
  - `Template(filename='spiderfoot/templates/error.tmpl', ...)` — sfwebui.py:229 (`error`)
  - No other Mako references in sfwebui.py after M4c.
- **23 `self.error(...)` callers** — all keep working; only the helper's body changes.
- **`_wants_json()` + `_json_response()` helpers** are in place (added in M3). They're still valid and used by savesettings / startscan JSON paths.
- **`self.docroot`** is set in `SpiderFootWebUi.__init__` from the app config. Safe to use in the rewritten helpers.
- **`html.escape`** is in the `html` module, already imported at the top of `sfwebui.py`. No new import needed.
- **Mantine v9:** `Menu.Item` accepts `component="a"` + `href` (pattern already used in ScanListPage for Delete confirm).
- **`@typescript-eslint/no-explicit-any`** is active — use `Mock` from vitest where needed.
- **`erasableSyntaxOnly: true`** — use `import type` for type-only imports.
- **`scanConfigGet(id)`** returns a dict with `_modulesenabled` as comma-separated string of module names (confirmed by reading `spiderfoot/db.py:scanConfigGet` during brainstorming; used by existing `rerunscan` handler).
- **`scanInstanceGet(id)`** returns tuple `[name, target, created, started, ended, status, ...]`. Index 0 = name, index 1 = target.

---

## Task 1: Backend — drop Mako + rewrite `self.error()` + `error_page_404()`

**Files:**
- Modify: `sfwebui.py`.
- Modify: `test/integration/test_sfwebui.py`.
- Modify: `test/unit/test_spiderfootwebui.py`.

### Step 1: Remove Mako imports + `self.lookup`

Edit `/Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py`:

- Delete the two imports at the top of the file:
  ```python
  from mako.lookup import TemplateLookup
  from mako.template import Template
  ```
- Find `self.lookup = TemplateLookup(directories=[''])` in `__init__` (around line 62) and delete the entire line.

### Step 2: Rewrite `self.error(message)`

Find the existing method (around line 220). Replace the body:

```python
def error(self: 'SpiderFootWebUi', message: str) -> str:
    """Render a minimal HTML error page.

    Fallback for legacy non-JSON callers (curl, sfcli form-posts).
    SPA flows branch on Accept: application/json and never reach here.

    Args:
        message (str): error message

    Returns:
        str: HTML error page.
    """
    safe_message = html.escape(message)
    return (
        "<!DOCTYPE html>"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>SpiderFoot — Error</title></head>"
        "<body style=\"font-family: sans-serif; padding: 2rem; "
        "max-width: 48rem; margin: 0 auto;\">"
        "<h1>Something went wrong</h1>"
        f"<p>{safe_message}</p>"
        f"<p><a href=\"{self.docroot}/\">← Back to scan list</a></p>"
        "</body></html>"
    )
```

No changes to any of the 23 callers — they keep calling `return self.error("...")` and get a string back.

### Step 3: Rewrite `error_page_404()`

Find the existing method (around line 160). Replace the body:

```python
def error_page_404(
    self: 'SpiderFootWebUi',
    status: str,
    message: str,
    traceback: str,
    version: str,
) -> str:
    """CherryPy custom 404 handler — plain inline HTML.

    Args:
        status (str): HTTP response status code and message
        message (str): Error message
        traceback (str): Error stack trace (ignored)
        version (str): CherryPy version (ignored)

    Returns:
        str: HTTP response template
    """
    return (
        "<!DOCTYPE html>"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>SpiderFoot — Not Found</title></head>"
        "<body style=\"font-family: sans-serif; padding: 2rem; "
        "max-width: 48rem; margin: 0 auto;\">"
        "<h1>Page not found</h1>"
        f"<p>{html.escape(status)}: {html.escape(message)}</p>"
        f"<p><a href=\"{self.docroot}/\">← Back to scan list</a></p>"
        "</body></html>"
    )
```

Keep the signature (status, message, traceback, version) — CherryPy passes all four; removing any would crash on 404.

### Step 4: Grep for lingering Mako references

```bash
grep -nE "Template\(|TemplateLookup|mako\.|self\.lookup" /Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py
```

Expected: zero matches. If anything remains, remove it (could be a stale comment).

### Step 5: Update Python tests that grep Mako-era HTML

```bash
grep -rnE "alert-danger|navbar-default|spiderfoot-header|aboutmodal|SpiderFoot v\$\{version\}" /Users/olahjort/Projects/OhDeere/spiderfoot/test/
```

For each match:
- If the test is asserting the presence of Mako-era chrome (navbar, footer, HEADER strings), **update the assertion** to match the new minimal HTML — look for `"Something went wrong"` / `"Page not found"` / `"Back to scan list"` as stable anchors.
- If the test's only assertion was the Mako chrome (no behavioral coverage), delete it.

Also look for tests that pass through `self.error(...)` directly:

```bash
grep -n "def test_error\|sfwebui.error(" /Users/olahjort/Projects/OhDeere/spiderfoot/test/unit/test_spiderfootwebui.py
```

Any `test_error` that asserted the Mako-rendered body needs updating:

```python
def test_error(self):
    """Test error(self, message) — returns HTML error page."""
    opts = self.default_options
    opts['__modules__'] = dict()
    sfwebui = SpiderFootWebUi(self.web_default_options, opts)
    error_page = sfwebui.error("example error message")
    self.assertIsInstance(error_page, str)
    self.assertIn("Something went wrong", error_page)
    self.assertIn("example error message", error_page)
```

### Step 6: Run pytest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -5
```

Expected: **1464 passed, 34 skipped** (baseline preserved if all assertion updates were complete). If the count drops by a handful, those are the tests that had Mako-specific body assertions — fix them in Step 5 and re-run.

### Step 7: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add sfwebui.py test/integration/test_sfwebui.py test/unit/test_spiderfootwebui.py
git commit -m "$(cat <<'EOF'
webui: self.error() + error_page_404() rewrite to inline HTML

Drops mako.lookup + mako.template imports from sfwebui.py and the
self.lookup attribute from __init__. Both HTML-producing helpers
now return inline HTML strings — doctype + minimal inline CSS +
error message + "Back to scan list" link. No more HEADER/FOOTER/
error.tmpl references.

All 23 self.error(...) callers are unchanged: same signature,
same string return type. SPA flows branch on Accept: application/
json via _wants_json() / _json_response() and never reach these
helpers.

test_error and a handful of integration tests updated to assert
the new minimal HTML anchors ("Something went wrong" / "Back to
scan list") instead of Mako-era chrome.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-5-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Backend — new `/clonescan` JSON endpoint

**Files:**
- Modify: `sfwebui.py` — add handler.
- Modify: `test/integration/test_sfwebui.py` — TDD: failing test first.

### Step 1: Write the failing test

Edit `/Users/olahjort/Projects/OhDeere/spiderfoot/test/integration/test_sfwebui.py`. Add:

```python
def test_clonescan_unknown_scan_returns_404(self):
    """/clonescan returns JSON 404 for unknown scan IDs."""
    self.getPage("/clonescan?id=doesnotexist")
    self.assertStatus('404 Not Found')
    body = json.loads(self.body)
    self.assertEqual(body['error']['http_status'], '404')
    self.assertIn('does not exist', body['error']['message'])
```

### Step 2: Run the test — expect FAIL

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest test/integration/test_sfwebui.py -k test_clonescan_unknown_scan_returns_404 -v 2>&1 | tail -10
```

Expected: FAIL. Most likely 404 with the default CherryPy body (not JSON) because the handler doesn't exist.

### Step 3: Add the `/clonescan` handler

Locate a sensible spot in `sfwebui.py` (near the other scan-management handlers — the rerunscan / scaninfo group, around line ~855). Add:

```python
@cherrypy.expose
@cherrypy.tools.json_out()
def clonescan(self: 'SpiderFootWebUi', id: str) -> dict:
    """Return prefill data for cloning a scan into /newscan.

    Args:
        id (str): scan ID to clone

    Returns:
        dict: { scanName, scanTarget, modulelist, typelist, usecase }
    """
    dbh = SpiderFootDb(self.config)
    info = dbh.scanInstanceGet(id)
    if not info:
        return self.jsonify_error('404', f"Scan {id} does not exist")
    scan_config = dbh.scanConfigGet(id)
    if not scan_config:
        return self.jsonify_error('404', f"Scan {id} has no config")
    module_list = scan_config.get('_modulesenabled', '').split(',')
    filtered_modules = [
        m for m in module_list if m and m != 'sfp__stor_stdout'
    ]
    return {
        'scanName': info[0],
        'scanTarget': info[1],
        'modulelist': filtered_modules,
        'typelist': [],
        'usecase': '',
    }
```

### Step 4: Run the test — expect PASS

```bash
python3 -m pytest test/integration/test_sfwebui.py -k test_clonescan_unknown_scan_returns_404 -v 2>&1 | tail -10
```

Expected: PASS.

### Step 5: Full suite — confirm nothing broke

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1465 passed, 34 skipped** (+1 vs Task 1).

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add sfwebui.py test/integration/test_sfwebui.py
git commit -m "$(cat <<'EOF'
webui: /clonescan JSON endpoint for scan-prefill UX

Returns {scanName, scanTarget, modulelist, typelist, usecase}
for the given scan ID, or jsonify_error('404', ...) if the scan
is unknown. Used by the SPA's NewScanPage to prefill the form
when landing at /newscan?clone=<guid>.

Module list is pulled from scanConfigGet's _modulesenabled (same
field rerunscan reads). sfp__stor_stdout is filtered out because
it only matters in CLI scans — NewScanPage adds sfp__stor_db
automatically at submit time.

typelist is empty (not preserved in scanConfigGet) and usecase
is empty (module-list prefill takes priority in the SPA).

1 TDD integration test covers the 404 path; happy-path cloning
is exercised end-to-end by the M5 Playwright case.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-5-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Frontend — `fetchScanClone` API + 1 Vitest case

**Files:**
- Modify: `webui/src/api/scans.ts` — add wrapper.
- Modify: `webui/src/api/scans.test.ts` — 1 new Vitest case.

### Step 1: Extend `webui/src/api/scans.ts`

Add at the bottom of the file:

```typescript
type CloneScanResponse = {
  scanName: string;
  scanTarget: string;
  modulelist: string[];
  typelist: string[];
  usecase: string;
};

export type ScanClonePrefill = {
  scanName: string;
  scanTarget: string;
  moduleList: string[];
  typeList: string[];
  usecase: UseCase;
};

export async function fetchScanClone(id: string): Promise<ScanClonePrefill> {
  const raw = await fetchJson<CloneScanResponse>(
    `/clonescan?id=${encodeURIComponent(id)}`,
  );
  return {
    scanName: raw.scanName,
    scanTarget: raw.scanTarget,
    moduleList: raw.modulelist ?? [],
    typeList: raw.typelist ?? [],
    usecase: (raw.usecase || 'all') as UseCase,
  };
}
```

Note: `UseCase` is already imported in the file (used by `startScan`). If the compiler complains it's unused, leave it — the new code references it.

### Step 2: Extend `webui/src/api/scans.test.ts`

Add `fetchScanClone` to the top-of-file import. At the end of the file, append:

```typescript
describe('fetchScanClone', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('normalizes snake_case modulelist/typelist into camelCase + sane defaults', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify({
          scanName: 'original',
          scanTarget: 'example.com',
          modulelist: ['sfp_countryname', 'sfp_dnsresolve'],
          typelist: [],
          usecase: '',
        }),
        { status: 200 },
      ),
    );
    const result = await fetchScanClone('abc');
    expect(result).toEqual({
      scanName: 'original',
      scanTarget: 'example.com',
      moduleList: ['sfp_countryname', 'sfp_dnsresolve'],
      typeList: [],
      usecase: 'all',
    });
    const [url] = (globalThis.fetch as Mock).mock.calls[0];
    expect(url).toBe('/clonescan?id=abc');
  });
});
```

### Step 3: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **69 existing + 1 new = 70 passing**.

### Step 4: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

Expected: success.

### Step 5: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/api/scans.ts webui/src/api/scans.test.ts
git commit -m "$(cat <<'EOF'
webui: typed fetchScanClone for /clonescan

ScanClonePrefill + fetchScanClone(id) wrap the /clonescan
endpoint. Normalizes the backend's snake_case modulelist/typelist
into camelCase moduleList/typeList, and defaults usecase='all'
when the server sends an empty string (Mantine's Radio.Group
requires a non-empty value).

1 Vitest case covers the shape mapping + URL encoding.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-5-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Frontend — NewScanPage prefill + ScanListPage Clone menu + 1 Vitest case

**Files:**
- Modify: `webui/src/pages/NewScanPage.tsx` — read `?clone=<guid>`, fetch prefill, seed state.
- Modify: `webui/src/pages/NewScanPage.test.tsx` — 1 new Vitest case.
- Modify: `webui/src/pages/ScanListPage.tsx` — add `Clone` Menu.Item.

### Step 1: Extend `webui/src/pages/NewScanPage.tsx`

Add imports:

```tsx
import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchScanClone } from '../api/scans';
```

Inside the `NewScanPage` component, after the existing `modulesQuery` / `typesQuery` hooks but before the effects that seed default selections:

```tsx
const [searchParams] = useSearchParams();
const cloneId = searchParams.get('clone');

const cloneQuery = useQuery({
  queryKey: ['clonescan', cloneId],
  queryFn: () => fetchScanClone(cloneId!),
  enabled: !!cloneId,
  staleTime: Infinity,
});

// Seed the form state once from the clone response. Guard with a ref
// so user edits after prefill aren't clobbered.
const cloneSeededRef = useRef(false);
useEffect(() => {
  if (cloneSeededRef.current) return;
  if (!cloneQuery.data) return;
  if (!modulesQuery.data) return;
  // Apply clone prefill.
  cloneSeededRef.current = true;
  setScanName(`${cloneQuery.data.scanName} (clone)`);
  setScanTarget(cloneQuery.data.scanTarget);
  if (cloneQuery.data.moduleList.length > 0) {
    setMode('module');
    setSelectedModules(new Set(cloneQuery.data.moduleList));
  } else if (cloneQuery.data.typeList.length > 0) {
    setMode('type');
    setSelectedTypes(new Set(cloneQuery.data.typeList));
  } else {
    setMode('usecase');
    setUsecase(cloneQuery.data.usecase);
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [cloneQuery.data, modulesQuery.data]);
```

The existing "default: all modules + all types checked" effect (from M2) may conflict with the clone seed. Check: that effect runs once when `modulesQuery.data` first arrives, initializing `selectedModules` to the full set. The clone-seed effect above fires after both `cloneQuery.data` and `modulesQuery.data` are ready — it overwrites `selectedModules` with the clone's specific list. Verify the order with a `console.log` during implementation; if the clone seed lands first and then the "check all" default overwrites it, flip the default-check effect to skip when `cloneId` is set:

```tsx
// Default: all modules + all types checked once loaded — unless we're
// cloning, in which case the clone-seed effect handles selection.
useEffect(() => {
  if (cloneId) return;
  if (modulesQuery.data && selectedModules.size === 0) {
    setSelectedModules(new Set(modulesQuery.data.map((m) => m.name)));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [modulesQuery.data, cloneId]);

useEffect(() => {
  if (cloneId) return;
  if (typesQuery.data && selectedTypes.size === 0) {
    setSelectedTypes(new Set(typesQuery.data.map((t) => t.id)));
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [typesQuery.data, cloneId]);
```

Also update the loading branch: the page must wait for the clone fetch to resolve before showing the form. In the existing `if (modulesQuery.isLoading || typesQuery.isLoading)` check, add `|| (cloneId && cloneQuery.isLoading)`.

### Step 2: Extend `webui/src/pages/NewScanPage.test.tsx`

Add a new test case at the bottom of the existing `describe` block:

```tsx
it('prefills the form when navigated with ?clone=<guid>', async () => {
  (globalThis.fetch as Mock).mockImplementation((url: string) => {
    if (url === '/modules') {
      return Promise.resolve(
        new Response(
          JSON.stringify([
            { name: 'sfp_countryname', descr: 'Country name', api_key: false },
            { name: 'sfp_dnsresolve', descr: 'DNS resolver', api_key: false },
          ]),
          { status: 200 },
        ),
      );
    }
    if (url === '/eventtypes') {
      return Promise.resolve(
        new Response(JSON.stringify([['Domain Name', 'DOMAIN_NAME']]), {
          status: 200,
        }),
      );
    }
    if (url.startsWith('/clonescan')) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            scanName: 'monthly-recon',
            scanTarget: 'spiderfoot.net',
            modulelist: ['sfp_countryname'],
            typelist: [],
            usecase: '',
          }),
          { status: 200 },
        ),
      );
    }
    return Promise.reject(new Error(`Unexpected URL ${url}`));
  });

  // Render at /newscan?clone=abc — use MemoryRouter from react-router-dom.
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/newscan?clone=abc']}>
          <Routes>
            <Route path="/newscan" element={<NewScanPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );

  // Scan Name input is set to "monthly-recon (clone)".
  const nameInput = await screen.findByLabelText(/Scan Name/);
  expect((nameInput as HTMLInputElement).value).toBe('monthly-recon (clone)');
  // Scan Target input is set to "spiderfoot.net".
  const targetInput = screen.getByLabelText(/Scan Target/);
  expect((targetInput as HTMLInputElement).value).toBe('spiderfoot.net');
});
```

Make sure `MemoryRouter` and `Routes` + `Route` are imported at the top of the test file (they already are in ScanInfoPage.test.tsx — mirror that pattern):

```tsx
import { MemoryRouter, Route, Routes } from 'react-router-dom';
```

The existing NewScanPage tests use `render(...)` without a router. The existing tests keep using that — only this new test needs `MemoryRouter`.

Actually, NewScanPage uses `useSearchParams` from react-router-dom now that we've added clone support. The existing tests render NewScanPage outside a Router — that would crash. Fix: wrap the existing `renderPage()` helper in a MemoryRouter too. Add this at the top of the file's inner helper:

```tsx
import { MemoryRouter } from 'react-router-dom';

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/newscan']}>
          <NewScanPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}
```

Wrapping with `<MemoryRouter>` but no `<Routes>` / `<Route>` is fine — `useSearchParams` just reads from the wrapper's location. The path matcher only matters if we're testing route resolution.

### Step 3: Extend `webui/src/pages/ScanListPage.tsx`

Find the existing Menu.Dropdown inside the row actions (around the Delete menu item):

```tsx
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
```

Add a `Clone` item between View and Delete:

```tsx
<Menu.Dropdown>
  <Menu.Item
    component="a"
    href={`/scaninfo?id=${scan.guid}`}
  >
    View
  </Menu.Item>
  <Menu.Item
    component="a"
    href={`/newscan?clone=${encodeURIComponent(scan.guid)}`}
  >
    Clone
  </Menu.Item>
  <Menu.Item
    color="red"
    onClick={() => openDeleteConfirm(scan)}
  >
    Delete
  </Menu.Item>
</Menu.Dropdown>
```

Plain anchor = full-page reload into /newscan, matching the existing `View` link's convention.

### Step 4: Run Vitest

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected: **70 + 1 = 71 passing**.

If tests fail because existing NewScanPage tests now need a Router wrapper (they didn't before), make sure `renderPage()` wraps in MemoryRouter — see Step 2.

### Step 5: Build

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

### Step 6: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/NewScanPage.tsx webui/src/pages/NewScanPage.test.tsx webui/src/pages/ScanListPage.tsx
git commit -m "$(cat <<'EOF'
webui: Clone-scan UX — NewScanPage prefill + ScanListPage menu

NewScanPage now reads ?clone=<guid> via useSearchParams. When
present, fetches /clonescan and seeds form state: name gets the
" (clone)" suffix, target + modulelist are copied, selection
mode is derived from whichever list is populated. Existing
"default: all checked" effects skip when cloneId is set so the
prefill isn't clobbered.

ScanListPage row action menu gains a Clone item between View and
Delete. Plain <a> href="/newscan?clone=<guid>" triggers a full-
page reload into /newscan, matching the existing View link.

1 Vitest case: render NewScanPage at /newscan?clone=abc with
mocked /clonescan, assert both Scan Name + Scan Target inputs
carry the cloned values.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-5-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Retirements + `/static` mount removal + Playwright

**Files:**
- Modify: `sf.py` — remove `/static` from conf dict.
- Delete: `spiderfoot/templates/` (entire directory — HEADER.tmpl, FOOTER.tmpl, error.tmpl).
- Delete: `spiderfoot/static/js/spiderfoot.js`.
- Delete: `spiderfoot/static/css/` (entire directory — spiderfoot.css, dark.css).
- Delete: `spiderfoot/static/package.json` + `spiderfoot/static/package-lock.json` (if present).
- Delete: `spiderfoot/static/node_modules/` (entire directory).
- Delete: `spiderfoot/static/img/` (after grep audit).
- Create: `webui/tests/e2e/08-clone-scan.spec.ts`.

### Step 1: Audit for any remaining references

```bash
grep -rnE "/static/node_modules|/static/js/|/static/css/|/static/img/|spiderfoot\.js|spiderfoot\.css|dark\.css|HEADER\.tmpl|FOOTER\.tmpl|error\.tmpl" /Users/olahjort/Projects/OhDeere/spiderfoot --include="*.py" --include="*.tsx" --include="*.ts" --include="*.tmpl" --include="*.robot" --include="*.html"
```

Expected matches to act on:
- `sfwebui.py` should have no such references left after M4c + Task 1.
- `sf.py` — the `/static` mount config. Fix in Step 3.
- `webui/` — none expected.
- `docs/` — intentional history. Leave.

If anything else references these paths, flag it and update or delete before proceeding.

### Step 2: Audit `/static/img/`

```bash
grep -rn "/static/img/" /Users/olahjort/Projects/OhDeere/spiderfoot --include="*.py" --include="*.tsx" --include="*.ts" --include="*.tmpl" --include="*.html"
```

Expected: zero matches. If confirmed, `spiderfoot/static/img/` is safe to delete. If a match remains (e.g. a default favicon reference), either keep the single image file + a narrow `/static/img/` mount or move the asset into `webui/public/`.

### Step 3: Remove the legacy `/static` mount from `sf.py`

```bash
grep -n "'/static'\|'/static/webui'" /Users/olahjort/Projects/OhDeere/spiderfoot/sf.py
```

Locate the `conf` dict. Replace its body so only `/static/webui` remains:

```python
conf = {
    '/static/webui': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': _SPA_DIST,
        'tools.staticdir.index': 'index.html',
    },
}
```

(Keep the surrounding `_SPA_DIST` constant reference unchanged.)

### Step 4: Delete templates, JS, CSS

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git rm -r spiderfoot/templates/
git rm spiderfoot/static/js/spiderfoot.js
git rm -r spiderfoot/static/css/
git rm spiderfoot/static/package.json
git rm -f spiderfoot/static/package-lock.json   # use -f since it might not exist
```

Verify the `spiderfoot/static/js/` directory ends up empty. If so, `git rm -r` it too:

```bash
ls spiderfoot/static/js/ 2>/dev/null && rmdir spiderfoot/static/js/ 2>/dev/null || true
```

### Step 5: Delete node_modules + img (if audit passed)

`spiderfoot/static/node_modules/` is likely `.gitignore`'d already (node_modules usually are), but check:

```bash
ls spiderfoot/static/node_modules/ 2>&1 | head -5
```

If the directory exists on disk, delete it outright (it's regenerable; nobody wants it in a future install):

```bash
rm -rf spiderfoot/static/node_modules/
```

If it was tracked in git (unlikely but possible for historical vendored builds), use `git rm -r` instead.

If the Step-2 audit confirmed no SPA reference to `/static/img/`, delete it:

```bash
git rm -r spiderfoot/static/img/
```

### Step 6: Sanity-check the `/newscan`, `/scaninfo`, etc. routes still resolve

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 ./sf.py -l 127.0.0.1:5991 &
SF_PID=$!
sleep 5
curl -sI http://127.0.0.1:5991/ | head -1
curl -sI http://127.0.0.1:5991/newscan | head -1
curl -sI http://127.0.0.1:5991/scaninfo?id=doesnotexist | head -1
curl -sI http://127.0.0.1:5991/opts | head -1
curl -sI http://127.0.0.1:5991/static/webui/favicon.svg | head -1
curl -sI http://127.0.0.1:5991/static/img/ 2>&1 | head -1
curl -sI http://127.0.0.1:5991/static/node_modules/ 2>&1 | head -1
kill $SF_PID
```

Expected: first four return 200; favicon returns 200 (SPA still serves it); the last two return 404 (legacy /static paths gone).

### Step 7: Create `webui/tests/e2e/08-clone-scan.spec.ts`

```typescript
import { test, expect } from '@playwright/test';

test.describe('Clone scan (M5)', () => {
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
```

### Step 8: Full `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 71 Vitest + 16 Playwright + flake8 clean + 1465 pytest / 34 skipped.

If anything fails, report and STOP.

### Step 9: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add sf.py webui/tests/e2e/08-clone-scan.spec.ts
git rm -rf spiderfoot/templates/ spiderfoot/static/js/ spiderfoot/static/css/ spiderfoot/static/img/ 2>/dev/null || true
git rm spiderfoot/static/package.json
git rm -f spiderfoot/static/package-lock.json 2>/dev/null || true
git commit -m "$(cat <<'EOF'
webui: final sweep — delete Mako, legacy JS/CSS, static mount

Mako purge:
- spiderfoot/templates/HEADER.tmpl (134 lines)
- spiderfoot/templates/FOOTER.tmpl (25 lines)
- spiderfoot/templates/error.tmpl (7 lines)

Legacy JS/CSS:
- spiderfoot/static/js/spiderfoot.js (198 lines)
- spiderfoot/static/css/spiderfoot.css + dark.css

Vendored dependencies:
- spiderfoot/static/package.json + package-lock.json
- spiderfoot/static/node_modules/ (jquery, bootstrap3, d3, sigma,
  tablesorter, alertifyjs — tens of MB of regenerable bundles)

CherryPy:
- /static mount (serving spiderfoot/static/) removed from sf.py.
  Only /static/webui (serving webui/dist/) remains.

Playwright:
- 08-clone-scan.spec.ts: scan list Clone action lands on
  /newscan?clone=<guid> with the name prefilled.

After this commit: no Mako, no jQuery, no Bootstrap 3, no
vendored legacy node_modules/. The only HTML in Python is ~35
lines of fallback inside self.error(), error_page_404(), and
_serve_spa_shell() — analogous to Spring Boot's default error
page.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-5-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Docs refresh + final verify

**Files:**
- Modify: `CLAUDE.md` — Web UI section now describes the finished state.
- Modify: `docs/superpowers/BACKLOG.md` — mark M5 shipped; UI modernization section becomes historical.

### Step 1: Update `CLAUDE.md`

Find the Web UI top paragraph. Replace with:

```
SpiderFoot's UI runs entirely on the React SPA in `webui/`. The original CherryPy + Mako + jQuery + Bootstrap 3 surface has been fully retired (milestones 1–5, 2026-04-20). The SPA owns `/` (scan list), `/newscan` (scan creation), `/opts` (settings), and `/scaninfo` with all six tabs (Status, Info, Log, Browse, Correlations, Graph via @visx/network + d3-force). `sfwebui.py` retains ~35 lines of inline-HTML fallback inside `self.error()`, `error_page_404()`, and `_serve_spa_shell()` for legacy non-JSON callers (curl, sfcli, dev-without-build) — analogous to Spring Boot's default error page.
```

Also refresh the "Adding a migrated page" recipe — no migrations left, so rewrite as a "Adding a new page" recipe:

```
**Adding a new SPA page:**
1. Build the component in `webui/src/pages/<Foo>Page.tsx` with unit tests at `webui/src/pages/<Foo>Page.test.tsx`.
2. Add its route to `webui/src/router.tsx`.
3. Add the path to `_SPA_ROUTES` in `sfwebui.py` for documentation, and add a one-line `@cherrypy.expose` handler: `return self._serve_spa_shell()`.
4. Add a Playwright E2E spec under `webui/tests/e2e/`.
```

### Step 2: Update `docs/superpowers/BACKLOG.md`

Under `### UI modernization — page-by-page migration`:

**Shipped block** — append:

```
- Milestone 5 (2026-04-20) — final sweep. Retires HEADER.tmpl, FOOTER.tmpl, error.tmpl, spiderfoot.js, spiderfoot.css, dark.css, spiderfoot/static/node_modules/, and the legacy /static CherryPy mount. Converts self.error() + error_page_404() to inline HTML (no Mako). Adds Clone-scan UX: new GET /clonescan JSON endpoint, NewScanPage reads ?clone=<guid> and seeds form state, ScanListPage row menu gains a Clone action. Closes the UI retirement.
```

Update the specs glob to `{1,2,3,4a,4b,4c,5}` if present.

**Remaining Mako pages block** — delete the whole block. Replace with:

```
**UI modernization complete.** No Mako templates remain.
```

### Step 3: Final `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 71 Vitest + 16 Playwright + flake8 clean + 1465 pytest / 34 skipped.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — milestone 5 (UI retirement complete)

Updates the Web UI section to reflect the finished state: SPA
owns every route; ~35 lines of inline-HTML fallback remain in
Python helpers (analogous to Spring Boot defaults).

BACKLOG.md marks M5 shipped and removes the "remaining Mako
pages" block — nothing remains.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-5-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 5: Milestone + overall summary

Report:
- Number of commits across M5.
- All Mako retired. Legacy JS/CSS/node_modules gone.
- Clone-scan UX shipped end-to-end.
- Final test totals.
- Overall: 5 milestones (M1 → M5), spanning 2026-04-20. Complete UI modernization: CherryPy + Mako + jQuery + Bootstrap 3 → React 19 + Mantine 9 + TanStack Query + Vitest + Playwright + @visx/network + d3-force.

## Report Format

- **Status:** DONE | BLOCKED
- Final `./test/run` one-line summary
- Commit SHA
- Milestone summary + overall UI retirement summary
