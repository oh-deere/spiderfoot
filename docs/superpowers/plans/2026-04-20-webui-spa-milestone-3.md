# Web UI SPA — Milestone 3 (`/opts`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate SpiderFoot's `/opts` page from Mako + jQuery + Bootstrap 3 to the React SPA. Retire `opts.tmpl` and `spiderfoot.opts.js`. Extend `/optsraw` additively so the SPA has everything it needs in a single fetch.

**Architecture:** 8 tasks. Backend work lands first (handler swap + `/optsraw` enrichment + `/savesettings` JSON branches + Python test cleanup), then frontend (types + API layer + SettingInput + OptsPage composition + router), then retirement + Playwright + docs.

**Tech Stack:** Python 3.12 + CherryPy (unchanged), React 19 + Mantine 9 + TanStack Query 5 + React Router 7 + Vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md`.

---

## File Structure

### Backend (Python)
- **Modify** `sfwebui.py` — `opts()` serves SPA shell; extend `optsraw()` with `descs` + `modules` blocks; extend `savesettings()` with JSON success/error branches; add `/opts` to `_SPA_ROUTES`.
- **Modify** `test/integration/test_sfwebui.py` — enable `test_opts_returns_200` (currently `@unittest.skip("todo")`) with SPA-shell assertion; add `test_optsraw_returns_descs_and_modules`, `test_savesettings_invalid_token_json_returns_error`, `test_savesettings_json_success` integration tests.

### Frontend (React)
- **Create** `webui/src/api/settings.ts`, `webui/src/api/settings.test.ts`.
- **Create** `webui/src/components/SettingInput.tsx`.
- **Create** `webui/src/pages/OptsPage.tsx`, `webui/src/pages/OptsPage.test.tsx`.
- **Modify** `webui/src/types.ts` — add `SettingValue`, `ModuleMeta`, `SettingsGroup`, `SettingsPayload`.
- **Modify** `webui/src/router.tsx` — add `/opts` route.

### E2E + Robot
- **Create** `webui/tests/e2e/04-opts.spec.ts`.
- **Modify** `test/acceptance/scan.robot` — remove `Settings page should render` keyword + any references (mirror milestone 2's Robot surgery).

### Retirements
- **Delete** `spiderfoot/templates/opts.tmpl` (199 lines).
- **Delete** `spiderfoot/static/js/spiderfoot.opts.js` (43 lines).

### Docs
- **Modify** `CLAUDE.md` — Web UI section notes milestone 3 shipped.
- **Modify** `docs/superpowers/BACKLOG.md` — mark milestone 3 shipped; cross `/opts` off the remaining list.

---

## Context for the implementer

- **Branch:** commit directly on `master`. Milestones 1 + 2 used this pattern; master is currently at 82aeefd7 (milestone 2 docs commit).
- **Baseline:** 30 Vitest + 7 Playwright + flake8 clean + 1460 pytest + 35 skipped.
- **Milestone-2 SPA-shell helper:** `sfwebui.py` already has `_serve_spa_shell()` (private) — both `index()` and `newscan()` are one-liners calling it. This milestone makes `opts()` the third caller.
- **`/optsraw` current shape:** `["SUCCESS", {"token": <int>, "data": {"global.foo": value, "module.sfp_x.opt": value, ...}}]`. This milestone adds two peer keys: `descs` (flat `key → description`) and `modules` (per-module name/descr/cats/labels/meta).
- **`/savesettings` current semantics:** On success, raises `cherrypy.HTTPRedirect('/opts?updated=1')`. On errors (token mismatch, parse fail, save fail), returns `self.error("<msg>")` rendering `error.tmpl`. The Accept-based branching uses the same pattern as `startscan()` (see milestone 2 commit b1c0a5c7).
- **`parseConfigFile` format:** files exported via `/optsexport` have `key=value\n` lines where keys are already in `global.foo` / `module.mod.opt` shape. The SPA's parser just splits on `=` and strips whitespace.
- **`dirty` detection:** use shallow equality on primitive values; use `JSON.stringify` comparison for lists (small, fine). Don't pull in `lodash.isEqual` — one helper function.
- **CSRF token:** server rotates on every `/optsraw` fetch via `self.token = random.SystemRandom().randint(0, 99999999)`. The SPA must send back the exact token from its most recent fetch.
- **Mantine v9:** `<NavLink>`, `<ScrollArea>`, `<TextInput>`, `<NumberInput>`, `<Switch>`, `<Table>`, `<Popover>`, `<Menu>`, `<Alert>`, `<Grid>`, `<Badge>`. `@tabler/icons-react` already installed (`IconKey`, `IconDownload`, `IconUpload`, `IconRefresh`, `IconDotsVertical`).

---

## Task 1: Backend — `opts()` serves SPA shell + integration test update

**Files:**
- Modify: `sfwebui.py` — replace `opts()` body; add `/opts` to `_SPA_ROUTES`.
- Modify: `test/integration/test_sfwebui.py` — enable skipped `test_opts_returns_200` with SPA-shell assertion.

- [ ] **Step 1: Read current `opts()` handler**

```bash
grep -nE "_SPA_ROUTES|def opts\(" /Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py
```

Current state after milestone 2: `_SPA_ROUTES = {"/", "/newscan"}`, `opts()` still renders `opts.tmpl`.

- [ ] **Step 2: Replace `opts()` body**

Find the method (search `def opts(`). Replace the whole method with:

```python
@cherrypy.expose
def opts(self: 'SpiderFootWebUi', updated: str = None) -> str:
    """Serve the SPA shell at /opts.

    Milestone 3 moved the settings form into the SPA. The `updated`
    query param (legacy Mako redirect marker) is ignored; the SPA
    surfaces save success via a Mantine notification.

    Returns:
        str: SPA shell HTML.
    """
    return self._serve_spa_shell()
```

- [ ] **Step 3: Add `/opts` to `_SPA_ROUTES`**

Find:
```python
_SPA_ROUTES = {"/", "/newscan"}
```

Change to:
```python
_SPA_ROUTES = {"/", "/newscan", "/opts"}
```

- [ ] **Step 4: Update `test_opts_returns_200`**

Edit `test/integration/test_sfwebui.py`. Find:

```python
@unittest.skip("todo")
def test_opts_returns_200(self):
    self.getPage("/opts")
    self.assertStatus('200 OK')
```

Replace with (drop the skip decorator, assert SPA shell like milestone 2's `test_newscan_returns_200`):

```python
def test_opts_returns_200(self):
    self.getPage("/opts")
    self.assertStatus('200 OK')
    body = self.body.decode() if isinstance(self.body, bytes) else self.body
    self.assertTrue(
        '<div id="root"></div>' in body or 'Web UI bundle not found' in body,
        msg=f"Unexpected /opts body: {body[:300]}"
    )
```

- [ ] **Step 5: Run pytest — confirm +1 passing**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1461 passed, 34 skipped** (one previously-skipped test is now live; total test count preserved; skip count −1).

- [ ] **Step 6: Commit**

```bash
git add sfwebui.py test/integration/test_sfwebui.py
git commit -m "$(cat <<'EOF'
webui: opts() serves SPA shell; enable /opts integration test

Milestone 3 takes /opts into the SPA. The opts() handler becomes
a one-liner calling _serve_spa_shell() (same pattern as index()
and newscan() from M1/M2). _SPA_ROUTES documentation set grows
to include /opts.

The previously-skipped test_opts_returns_200 is now live; asserts
the SPA-shell response (either the built bundle's id=root div or
the dev-fallback page).

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Backend — extend `/optsraw` with `descs` + `modules`

**Files:**
- Modify: `sfwebui.py` — add `descs` and `modules` blocks to `optsraw()` return.
- Modify: `test/integration/test_sfwebui.py` — failing test first, watch it pass.

- [ ] **Step 1: Read current `optsraw()` handler**

```bash
grep -n "def optsraw" /Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py
```

Read the method (around line 1035). It currently builds a flat `ret` dict of `global.*` / `module.*.*` keys and returns `['SUCCESS', {'token': ..., 'data': ret}]`.

- [ ] **Step 2: Write the failing test**

Edit `test/integration/test_sfwebui.py`. Add near the existing `test_optsraw`:

```python
def test_optsraw_returns_descs_and_modules(self):
    """After milestone 3, /optsraw includes per-option descs and
    per-module meta so the SPA renders without a second fetch.
    """
    self.getPage("/optsraw")
    self.assertStatus('200 OK')
    body = json.loads(self.body)
    self.assertIsInstance(body, list)
    self.assertEqual(body[0], "SUCCESS")
    payload = body[1]
    self.assertIn('token', payload)
    self.assertIn('data', payload)
    self.assertIn('descs', payload)
    self.assertIn('modules', payload)
    self.assertIsInstance(payload['descs'], dict)
    self.assertIsInstance(payload['modules'], dict)
    # At least one module meta should include the expected shape.
    first_mod = next(iter(payload['modules'].values()))
    for key in ('name', 'descr', 'cats', 'labels', 'meta'):
        self.assertIn(key, first_mod)
```

- [ ] **Step 3: Run — expect FAIL**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest test/integration/test_sfwebui.py -k test_optsraw_returns_descs_and_modules -v 2>&1 | tail -10
```

Expected: FAIL with `KeyError: 'descs'` or `AssertionError: 'descs' not found`.

- [ ] **Step 4: Extend `optsraw()`**

Locate the `optsraw()` method. After the existing `ret` loop (which builds the flat key:value map) but before the return, build the two new blocks:

```python
# Per-option descriptions, flat keyed to match `data`.
descs: dict = {}
global_descs = self.config.get('__globaloptdescs__', {})
for opt, desc in global_descs.items():
    descs["global." + opt] = desc
for mod in self.config.get('__modules__', {}):
    mod_optdescs = self.config['__modules__'][mod].get('optdescs', {}) or {}
    for opt, desc in mod_optdescs.items():
        if opt.startswith('_'):
            continue
        descs[f"module.{mod}.{opt}"] = desc

# Per-module metadata: name, descr, cats, labels, meta.
modules: dict = {}
for mod in sorted(self.config.get('__modules__', {}).keys()):
    m = self.config['__modules__'][mod]
    modules[mod] = {
        'name': m.get('name', mod),
        'descr': m.get('descr', ''),
        'cats': m.get('cats') or [],
        'labels': m.get('labels') or [],
        'meta': m.get('meta') or {},
    }

return ['SUCCESS', {'token': self.token, 'data': ret, 'descs': descs, 'modules': modules}]
```

Keep the existing data-building loop unchanged.

- [ ] **Step 5: Run the test — expect PASS**

```bash
python3 -m pytest test/integration/test_sfwebui.py -k test_optsraw_returns_descs_and_modules -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 6: Run the full suite — no regressions**

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1462 passed, 34 skipped** (one more than Task 1).

- [ ] **Step 7: Commit**

```bash
git add sfwebui.py test/integration/test_sfwebui.py
git commit -m "$(cat <<'EOF'
webui: /optsraw gains descs + modules metadata blocks

The SPA OptsPage needs per-option descriptions and per-module
meta (name, cats, labels, dataSource) to render without a second
fetch. /optsraw now includes:

- `descs`: flat `global.<opt>` / `module.<mod>.<opt>` -> description
  string. Sourced from self.config['__globaloptdescs__'] and
  per-module 'optdescs'.
- `modules`: map keyed by module name, each with {name, descr,
  cats, labels, meta}. Meta passes the raw module.meta dict through
  so the SPA can read `meta.dataSource.website` etc.

Additive. Existing /optsraw callers (the Mako /opts page is next
in line to be deleted; a couple of tests) ignore the new keys.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Backend — `/savesettings` JSON success/error branches

**Files:**
- Modify: `sfwebui.py` — add JSON branching to `savesettings()`.
- Modify: `test/integration/test_sfwebui.py` — two new tests (invalid-token + success).

- [ ] **Step 1: Read `savesettings()` end of function**

```bash
grep -nE "def savesettings|HTTPRedirect.*opts|self\.error\(" /Users/olahjort/Projects/OhDeere/spiderfoot/sfwebui.py | head -20
```

Understand the success path (`raise cherrypy.HTTPRedirect(...)`) and the two error paths (`return self.error("Invalid token...")` on CSRF mismatch, `return self.error(...)` on parse/save failure).

- [ ] **Step 2: Write the failing tests**

Edit `test/integration/test_sfwebui.py`. Add:

```python
def test_savesettings_invalid_token_json_returns_error(self):
    """When Accept: application/json is set and the CSRF token
    is invalid, /savesettings returns ['ERROR', msg] instead of
    rendering error.tmpl.
    """
    headers = [("Accept", "application/json")]
    self.getPage(
        "/savesettings?allopts=%7B%7D&token=notavalidtoken",
        headers=headers,
    )
    self.assertStatus('200 OK')
    body = json.loads(self.body)
    self.assertIsInstance(body, list)
    self.assertEqual(body[0], "ERROR")
    self.assertIn("Invalid token", body[1])

def test_savesettings_json_success_returns_success(self):
    """When Accept: application/json + valid token, /savesettings
    returns ['SUCCESS'] instead of redirecting.
    """
    # Fetch the current token via /optsraw.
    self.getPage("/optsraw")
    token = json.loads(self.body)[1]['token']

    headers = [("Accept", "application/json")]
    self.getPage(
        f"/savesettings?allopts=%7B%7D&token={token}",
        headers=headers,
    )
    self.assertStatus('200 OK')
    body = json.loads(self.body)
    self.assertIsInstance(body, list)
    self.assertEqual(body[0], "SUCCESS")
```

- [ ] **Step 3: Run — expect both FAIL**

```bash
python3 -m pytest test/integration/test_sfwebui.py -k "savesettings_invalid_token_json or savesettings_json_success" -v 2>&1 | tail -15
```

Expected: both FAIL. The invalid-token one sees HTML body (not parseable JSON); the success one sees a 303 redirect or HTML.

- [ ] **Step 4: Add a small helper + JSON branches**

Near the top of `SpiderFootWebUi` class (before `error()`, say), add a helper:

```python
def _wants_json(self) -> bool:
    """True when the caller set Accept: application/json."""
    accept = cherrypy.request.headers.get('Accept') or ''
    return 'application/json' in accept

def _json_response(self, status: str, message: str = "") -> bytes:
    """Build the server's ["SUCCESS"]/["ERROR", msg] response tuple."""
    cherrypy.response.headers['Content-Type'] = "application/json; charset=utf-8"
    if message:
        return json.dumps([status, message]).encode('utf-8')
    return json.dumps([status]).encode('utf-8')
```

Inside `savesettings()`:

- Replace every `return self.error("<msg>")` on the error paths with:
  ```python
  if self._wants_json():
      return self._json_response("ERROR", "<msg>")
      # (using whatever <msg> was previously passed to self.error)
  return self.error("<msg>")
  ```
- Before the two `raise cherrypy.HTTPRedirect(...)` success lines (one for reset success, one for save success), add:
  ```python
  if self._wants_json():
      return self._json_response("SUCCESS")
  raise cherrypy.HTTPRedirect(f"{self.docroot}/opts?updated=1")
  ```

There are likely 3 error returns and 2 success returns in the current body. Wrap all of them.

- [ ] **Step 5: Run the tests — expect PASS**

```bash
python3 -m pytest test/integration/test_sfwebui.py -k "savesettings_invalid_token_json or savesettings_json_success" -v 2>&1 | tail -10
```

Expected: both PASS.

- [ ] **Step 6: Full suite green**

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1464 passed, 34 skipped** (two more than Task 2).

- [ ] **Step 7: Commit**

```bash
git add sfwebui.py test/integration/test_sfwebui.py
git commit -m "$(cat <<'EOF'
webui: /savesettings returns JSON when Accept is JSON

Mirrors the /startscan JSON-success pattern from milestone 2. When
Accept: application/json is set:

- Valid save / reset -> ["SUCCESS"]
- Invalid CSRF token / parse failure / save failure -> ["ERROR", msg]

Legacy HTML form posts (no Accept header) still redirect to
/opts?updated=1 on success and render error.tmpl on failure,
so sfcli and any curl users are unaffected.

Two small helpers introduced: _wants_json() and _json_response()
so the JSON/HTML branching reads consistently across handlers.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Frontend — types + settings API + Vitest

**Files:**
- Modify: `webui/src/types.ts` — add `SettingValue`, `ModuleMeta`, `SettingsGroup`, `SettingsPayload`.
- Create: `webui/src/api/settings.ts` — `fetchSettings()`, `saveSettings()`, `resetSettings()`, `parseConfigFile()`, `coerceToOriginalType()`.
- Create: `webui/src/api/settings.test.ts`.

- [ ] **Step 1: Extend `webui/src/types.ts`**

Append:

```typescript
export type SettingValue = number | string | boolean | string[] | number[];

export type ModuleMeta = {
  name: string;
  descr: string;
  cats: string[];
  labels: string[];
  dataSourceWebsite?: string;
  dataSourceDescription?: string;
  apiKeyInstructions?: string[];
};

export type SettingsGroup = {
  key: string;                              // "global" or "module.sfp_foo"
  label: string;                            // "Global" or ModuleMeta.name
  settings: Record<string, SettingValue>;   // flat key -> current value
  descs: Record<string, string>;            // flat key -> description
  meta?: ModuleMeta;                        // present only for module groups
};

export type SettingsPayload = {
  token: number;
  groups: SettingsGroup[];                  // Global first, then modules sorted by name
  settings: Record<string, SettingValue>;   // flat master (for diff + serialize)
};
```

- [ ] **Step 2: Create `webui/src/api/settings.ts`**

```typescript
import { fetchJson } from './client';
import type { SettingValue, SettingsGroup, SettingsPayload, ModuleMeta } from '../types';

type OptsRawResponse = [
  'SUCCESS',
  {
    token: number;
    data: Record<string, SettingValue>;
    descs: Record<string, string>;
    modules: Record<string, {
      name: string;
      descr: string;
      cats: string[];
      labels: string[];
      meta: {
        dataSource?: {
          website?: string;
          description?: string;
          apiKeyInstructions?: string[];
        };
      };
    }>;
  },
];

function extractMeta(raw: OptsRawResponse[1]['modules'][string]): ModuleMeta {
  const ds = raw.meta?.dataSource ?? {};
  return {
    name: raw.name,
    descr: raw.descr,
    cats: raw.cats ?? [],
    labels: raw.labels ?? [],
    dataSourceWebsite: ds.website,
    dataSourceDescription: ds.description,
    apiKeyInstructions: ds.apiKeyInstructions,
  };
}

export async function fetchSettings(): Promise<SettingsPayload> {
  const raw = await fetchJson<OptsRawResponse>('/optsraw');
  if (!Array.isArray(raw) || raw[0] !== 'SUCCESS') {
    throw new Error('Unexpected /optsraw response');
  }
  const { token, data, descs, modules } = raw[1];

  // Partition flat data into per-group buckets.
  const globalSettings: Record<string, SettingValue> = {};
  const globalDescs: Record<string, string> = {};
  const modSettings = new Map<string, Record<string, SettingValue>>();
  const modDescs = new Map<string, Record<string, string>>();

  for (const [k, v] of Object.entries(data)) {
    if (k.startsWith('global.')) {
      globalSettings[k] = v;
    } else if (k.startsWith('module.')) {
      const [, mod] = k.split('.');
      if (!modSettings.has(mod)) modSettings.set(mod, {});
      modSettings.get(mod)![k] = v;
    }
  }
  for (const [k, d] of Object.entries(descs)) {
    if (k.startsWith('global.')) {
      globalDescs[k] = d;
    } else if (k.startsWith('module.')) {
      const [, mod] = k.split('.');
      if (!modDescs.has(mod)) modDescs.set(mod, {});
      modDescs.get(mod)![k] = d;
    }
  }

  const groups: SettingsGroup[] = [];
  groups.push({
    key: 'global',
    label: 'Global',
    settings: globalSettings,
    descs: globalDescs,
  });
  for (const mod of Object.keys(modules).sort()) {
    groups.push({
      key: `module.${mod}`,
      label: modules[mod].name,
      settings: modSettings.get(mod) ?? {},
      descs: modDescs.get(mod) ?? {},
      meta: extractMeta(modules[mod]),
    });
  }

  return { token, groups, settings: { ...data } };
}

function serializeValue(v: SettingValue): string {
  if (typeof v === 'boolean') return v ? '1' : '0';
  if (Array.isArray(v)) return v.join(',');
  return String(v);
}

export async function saveSettings(token: number, allopts: Record<string, SettingValue>): Promise<void> {
  // Server expects allopts as a JSON string inside a form-urlencoded body,
  // with each value already stringified in the legacy Mako convention.
  const stringified: Record<string, string> = {};
  for (const [k, v] of Object.entries(allopts)) {
    stringified[k] = serializeValue(v);
  }
  const body = new URLSearchParams();
  body.set('allopts', JSON.stringify(stringified));
  body.set('token', String(token));

  const result = await fetchJson<[string, string?]>('/savesettings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!Array.isArray(result) || result[0] !== 'SUCCESS') {
    throw new Error(result?.[1] ?? 'Unknown error saving settings');
  }
}

export async function resetSettings(token: number): Promise<void> {
  const body = new URLSearchParams();
  body.set('allopts', 'RESET');
  body.set('token', String(token));

  const result = await fetchJson<[string, string?]>('/savesettings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });
  if (!Array.isArray(result) || result[0] !== 'SUCCESS') {
    throw new Error(result?.[1] ?? 'Unknown error resetting settings');
  }
}

export function parseConfigFile(contents: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const rawLine of contents.split('\n')) {
    const line = rawLine.trim();
    if (!line || !line.includes('=')) continue;
    const eq = line.indexOf('=');
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1);  // don't trim value; preserve spaces
    if (key) out[key] = value;
  }
  return out;
}

export function coerceToOriginalType(raw: string, original: SettingValue): SettingValue {
  if (typeof original === 'boolean') {
    return raw === '1' || raw.toLowerCase() === 'true';
  }
  if (typeof original === 'number') {
    const n = Number(raw);
    return Number.isFinite(n) ? n : original;
  }
  if (Array.isArray(original)) {
    const parts = raw.split(',').map((p) => p.trim()).filter((p) => p.length > 0);
    if (original.length > 0 && typeof original[0] === 'number') {
      return parts.map(Number).filter((n) => Number.isFinite(n));
    }
    return parts;
  }
  return raw;
}
```

- [ ] **Step 3: Create `webui/src/api/settings.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import {
  fetchSettings,
  saveSettings,
  resetSettings,
  parseConfigFile,
  coerceToOriginalType,
} from './settings';

describe('fetchSettings', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('unwraps /optsraw into typed SettingsPayload with Global-first groups', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(
        JSON.stringify([
          'SUCCESS',
          {
            token: 42,
            data: {
              'global.webroot': '/sf',
              'module.sfp_x.opt_a': true,
              'module.sfp_x.opt_b': 'hello',
            },
            descs: {
              'global.webroot': 'Web root',
              'module.sfp_x.opt_a': 'Enable A',
            },
            modules: {
              sfp_x: {
                name: 'X Module',
                descr: 'summary',
                cats: ['Footprint'],
                labels: ['tool'],
                meta: {
                  dataSource: {
                    website: 'https://x.example',
                    description: 'data',
                    apiKeyInstructions: ['step 1', 'step 2'],
                  },
                },
              },
            },
          },
        ]),
        { status: 200 },
      ),
    );
    const payload = await fetchSettings();
    expect(payload.token).toBe(42);
    expect(payload.groups).toHaveLength(2);
    expect(payload.groups[0]).toMatchObject({
      key: 'global',
      label: 'Global',
      settings: { 'global.webroot': '/sf' },
      descs: { 'global.webroot': 'Web root' },
    });
    expect(payload.groups[1]).toMatchObject({
      key: 'module.sfp_x',
      label: 'X Module',
      settings: { 'module.sfp_x.opt_a': true, 'module.sfp_x.opt_b': 'hello' },
      meta: {
        name: 'X Module',
        cats: ['Footprint'],
        dataSourceWebsite: 'https://x.example',
        apiKeyInstructions: ['step 1', 'step 2'],
      },
    });
    expect(payload.settings['global.webroot']).toBe('/sf');
  });
});

describe('saveSettings', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('posts allopts as URL-encoded JSON with stringified bool/list values', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
    );
    await saveSettings(99, {
      'global.a': true,
      'global.b': 'hello',
      'global.c': 5,
      'global.d': ['x', 'y'],
    });
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('token')).toBe('99');
    const allopts = JSON.parse(body.get('allopts') ?? '{}');
    expect(allopts).toEqual({
      'global.a': '1',
      'global.b': 'hello',
      'global.c': '5',
      'global.d': 'x,y',
    });
  });

  it('throws on ERROR response', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['ERROR', 'Invalid token (nope)']), { status: 200 }),
    );
    await expect(saveSettings(1, {})).rejects.toThrow('Invalid token');
  });
});

describe('resetSettings', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('posts allopts=RESET with the token', async () => {
    (globalThis.fetch as Mock).mockResolvedValue(
      new Response(JSON.stringify(['SUCCESS']), { status: 200 }),
    );
    await resetSettings(123);
    const [, init] = (globalThis.fetch as Mock).mock.calls[0];
    const body = new URLSearchParams(init.body);
    expect(body.get('allopts')).toBe('RESET');
    expect(body.get('token')).toBe('123');
  });
});

describe('parseConfigFile', () => {
  it('parses key=value lines into a flat dict', () => {
    const out = parseConfigFile(
      'global.a=1\nmodule.sfp_x.foo=hello world\n# comment\nempty_key=\n=nokey\n',
    );
    expect(out).toEqual({
      'global.a': '1',
      'module.sfp_x.foo': 'hello world',
      empty_key: '',
    });
  });
});

describe('coerceToOriginalType', () => {
  it('coerces to bool', () => {
    expect(coerceToOriginalType('1', false)).toBe(true);
    expect(coerceToOriginalType('true', false)).toBe(true);
    expect(coerceToOriginalType('0', true)).toBe(false);
  });
  it('coerces to number', () => {
    expect(coerceToOriginalType('42', 5)).toBe(42);
    expect(coerceToOriginalType('nope', 5)).toBe(5);  // fallback
  });
  it('coerces to string[]', () => {
    expect(coerceToOriginalType('a, b,c', ['x'])).toEqual(['a', 'b', 'c']);
    expect(coerceToOriginalType('', ['x'])).toEqual([]);
  });
  it('coerces to number[]', () => {
    expect(coerceToOriginalType('1,2,3', [0])).toEqual([1, 2, 3]);
  });
  it('passes strings through', () => {
    expect(coerceToOriginalType('hello', 'default')).toBe('hello');
  });
});
```

- [ ] **Step 4: Run Vitest — expect 30 + ~10 new = ~40 passing**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

Expected count: 30 existing + 10 new (1 fetchSettings + 2 saveSettings + 1 resetSettings + 1 parseConfigFile + 5 coerceToOriginalType) = 40 tests passing.

- [ ] **Step 5: Build — confirm TS compiles**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -6
```

- [ ] **Step 6: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/types.ts webui/src/api/settings.ts webui/src/api/settings.test.ts
git commit -m "$(cat <<'EOF'
webui: typed API for /optsraw and /savesettings

Adds SettingValue / ModuleMeta / SettingsGroup / SettingsPayload
types plus an api/settings.ts module:

- fetchSettings() unwraps /optsraw's ["SUCCESS", {...}] envelope
  and partitions the flat data/descs maps into Global-first +
  modules-sorted SettingsGroup[] so the OptsPage NavLink list is
  a trivial .map().
- saveSettings(token, allopts) posts form-urlencoded JSON with
  values stringified the way the server parses them (bool -> "1"/
  "0", list -> comma-join). Throws server message on ERROR.
- resetSettings(token) posts allopts=RESET.
- parseConfigFile(contents) parses the `foo=bar` files emitted by
  /optsexport for the Import flow.
- coerceToOriginalType(raw, original) type-dispatches on the
  original value so imported string values land in the right
  shape.

10 Vitest cases cover all five.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Frontend — SettingInput component

**Files:**
- Create: `webui/src/components/SettingInput.tsx`.

- [ ] **Step 1: Create `webui/src/components/SettingInput.tsx`**

```tsx
import { NumberInput, Switch, TextInput } from '@mantine/core';
import type { SettingValue } from '../types';

export function SettingInput({
  settingKey,
  value,
  onChange,
}: {
  settingKey: string;
  value: SettingValue;
  onChange: (next: SettingValue) => void;
}) {
  if (typeof value === 'boolean') {
    return (
      <Switch
        checked={value}
        onChange={(e) => onChange(e.currentTarget.checked)}
        aria-label={settingKey}
      />
    );
  }
  if (typeof value === 'number') {
    return (
      <NumberInput
        value={value}
        onChange={(v) => onChange(typeof v === 'number' ? v : Number(v) || 0)}
        aria-label={settingKey}
      />
    );
  }
  if (Array.isArray(value)) {
    const display = value.join(',');
    const isNumberList = value.length > 0 && typeof value[0] === 'number';
    return (
      <TextInput
        value={display}
        onChange={(e) => {
          const raw = e.currentTarget.value;
          const parts = raw.split(',').map((p) => p.trim()).filter((p) => p.length > 0);
          if (isNumberList) {
            onChange(parts.map(Number).filter((n) => Number.isFinite(n)));
          } else {
            onChange(parts);
          }
        }}
        description="Comma-separated"
        aria-label={settingKey}
      />
    );
  }
  // string
  return (
    <TextInput
      value={value}
      onChange={(e) => onChange(e.currentTarget.value)}
      aria-label={settingKey}
    />
  );
}
```

- [ ] **Step 2: Build — confirm TS compiles**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -4
```

- [ ] **Step 3: Vitest — 40 existing still pass (no new tests yet; covered transitively via OptsPage in Task 6)**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -4
```

- [ ] **Step 4: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/components/SettingInput.tsx
git commit -m "$(cat <<'EOF'
webui: SettingInput — type-dispatched form control

One component that dispatches on the runtime value's type:
bool -> Switch, number -> NumberInput, list -> comma-separated
TextInput (handles string[] and number[] via array-element-0
type sniff), string -> TextInput.

Keeps the type-driven rendering concern in one place so OptsPage
can map over settings without knowing their types.

Controlled-only API; state lives in the composing OptsPage (Task 6).
Tested transitively through OptsPage.test.tsx.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Frontend — OptsPage composition + router + Vitest

**Files:**
- Create: `webui/src/pages/OptsPage.tsx`, `webui/src/pages/OptsPage.test.tsx`.
- Modify: `webui/src/router.tsx` — add `/opts` route.

- [ ] **Step 1: Create `webui/src/pages/OptsPage.tsx`**

```tsx
import { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Grid,
  Group,
  Loader,
  Menu,
  NavLink,
  Popover,
  ScrollArea,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconDotsVertical, IconHelp, IconKey } from '@tabler/icons-react';
import {
  fetchSettings,
  saveSettings,
  resetSettings,
  parseConfigFile,
  coerceToOriginalType,
} from '../api/settings';
import { SettingInput } from '../components/SettingInput';
import type { SettingValue, SettingsGroup } from '../types';

function isEqualValue(a: SettingValue, b: SettingValue): boolean {
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((v, i) => v === b[i]);
  }
  return a === b;
}

export function OptsPage() {
  const queryClient = useQueryClient();
  const [activeGroup, setActiveGroup] = useState<string>('global');
  const [filter, setFilter] = useState('');
  const [current, setCurrent] = useState<Record<string, SettingValue>>({});
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const query = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
    staleTime: Infinity,
  });

  // Seed `current` once the query resolves (and on every subsequent refetch,
  // to pick up server-side coercions after a save).
  const lastSettingsRef = useRef<Record<string, SettingValue> | null>(null);
  if (query.data && query.data.settings !== lastSettingsRef.current) {
    lastSettingsRef.current = query.data.settings;
    setCurrent({ ...query.data.settings });
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!query.data) throw new Error('Settings not loaded');
      await saveSettings(query.data.token, current);
    },
    onSuccess: () => {
      notifications.show({
        color: 'green',
        title: 'Settings saved',
        message: 'Changes take effect on the next scan.',
      });
      void queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      if (!query.data) throw new Error('Settings not loaded');
      await resetSettings(query.data.token);
    },
    onSuccess: () => {
      notifications.show({
        color: 'green',
        title: 'Reset complete',
        message: 'Settings have been restored to factory defaults.',
      });
      void queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  const dirtyKeys = useMemo(() => {
    if (!query.data) return new Set<string>();
    const s = new Set<string>();
    for (const [k, v] of Object.entries(current)) {
      const orig = query.data.settings[k];
      if (orig === undefined || !isEqualValue(v, orig)) s.add(k);
    }
    return s;
  }, [current, query.data]);

  const isGroupDirty = (group: SettingsGroup): boolean =>
    Object.keys(group.settings).some((k) => dirtyKeys.has(k));

  if (query.isLoading) {
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    );
  }
  if (query.isError || !query.data) {
    return (
      <Alert color="red" title="Failed to load settings" mt="md">
        {(query.error as Error)?.message ?? 'Unknown error'}
        <Group mt="sm">
          <Button size="xs" onClick={() => void query.refetch()}>
            Retry
          </Button>
        </Group>
      </Alert>
    );
  }

  const groups = query.data.groups;
  const visibleGroups = groups.filter((g) =>
    g.key === 'global' ||
    g.label.toLowerCase().includes(filter.toLowerCase()) ||
    g.key.toLowerCase().includes(filter.toLowerCase()),
  );
  const selected = groups.find((g) => g.key === activeGroup) ?? groups[0];

  const openResetConfirm = () =>
    modals.openConfirmModal({
      title: 'Reset settings to factory default?',
      children: (
        <Text size="sm">
          This wipes every API key and every custom value and restores the
          defaults. Cannot be undone.
        </Text>
      ),
      labels: { confirm: 'Reset', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () => resetMutation.mutate(),
    });

  const handleImportClick = () => fileInputRef.current?.click();
  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';  // allow re-selecting the same file
    if (!file) return;
    const contents = await file.text();
    const parsed = parseConfigFile(contents);
    const next = { ...current };
    let skipped = 0;
    for (const [k, raw] of Object.entries(parsed)) {
      if (!(k in next)) {
        skipped += 1;
        continue;
      }
      next[k] = coerceToOriginalType(raw, next[k]);
    }
    setCurrent(next);
    notifications.show({
      color: 'blue',
      title: 'Config imported',
      message: `${Object.keys(parsed).length - skipped} applied, ${skipped} skipped. Review and click Save.`,
    });
  };

  const hasApiKeyDataForSelected = (s: typeof selected): boolean =>
    !!s.meta?.apiKeyInstructions && s.meta.apiKeyInstructions.length > 0;

  return (
    <Stack>
      <Group justify="space-between" align="center">
        <Title order={2}>Settings</Title>
        <Group>
          <Button
            color="red"
            disabled={dirtyKeys.size === 0 || saveMutation.isPending}
            loading={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            Save Changes {dirtyKeys.size > 0 ? `(${dirtyKeys.size})` : ''}
          </Button>
          <Menu shadow="md" width={220}>
            <Menu.Target>
              <ActionIcon variant="subtle" aria-label="Settings actions">
                <IconDotsVertical size={18} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item onClick={handleImportClick}>Import API Keys</Menu.Item>
              <Menu.Item component="a" href="/optsexport" download>
                Export API Keys
              </Menu.Item>
              <Menu.Divider />
              <Menu.Item color="red" onClick={openResetConfirm}>
                Reset to Factory Default
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </Group>

      <input
        ref={fileInputRef}
        type="file"
        style={{ display: 'none' }}
        accept=".cfg,.txt,text/plain"
        onChange={handleImportFile}
        aria-label="Import config file"
      />

      {saveMutation.isError && (
        <Alert color="red" title="Save failed">
          {(saveMutation.error as Error).message}
        </Alert>
      )}
      {resetMutation.isError && (
        <Alert color="red" title="Reset failed">
          {(resetMutation.error as Error).message}
        </Alert>
      )}

      <Grid>
        <Grid.Col span={3}>
          <Stack>
            <TextInput
              placeholder="Filter modules..."
              value={filter}
              onChange={(e) => setFilter(e.currentTarget.value)}
              aria-label="Filter settings groups"
            />
            <ScrollArea h={600}>
              <Stack gap={2}>
                {visibleGroups.map((g) => (
                  <NavLink
                    key={g.key}
                    active={g.key === activeGroup}
                    label={g.label}
                    rightSection={
                      isGroupDirty(g) ? (
                        <Badge size="xs" color="red" variant="dot" aria-label="Has unsaved changes" />
                      ) : null
                    }
                    leftSection={
                      g.meta?.apiKeyInstructions ? <IconKey size={12} /> : null
                    }
                    onClick={() => setActiveGroup(g.key)}
                  />
                ))}
              </Stack>
            </ScrollArea>
          </Stack>
        </Grid.Col>

        <Grid.Col span={9}>
          {selected && (
            <Stack>
              <Group align="baseline">
                <Title order={3}>{selected.label}</Title>
                {selected.meta?.dataSourceWebsite && (
                  <Anchor href={selected.meta.dataSourceWebsite} target="_blank" size="sm">
                    {selected.meta.dataSourceWebsite}
                  </Anchor>
                )}
              </Group>

              {selected.meta && (
                <Stack gap={4}>
                  {selected.meta.descr && <Text size="sm">{selected.meta.descr}</Text>}
                  {selected.meta.dataSourceDescription && (
                    <Text size="sm" c="dimmed">
                      {selected.meta.dataSourceDescription}
                    </Text>
                  )}
                  {selected.meta.cats.length > 0 && (
                    <Text size="xs" c="dimmed">Categories: {selected.meta.cats.join(', ')}</Text>
                  )}
                </Stack>
              )}

              <Table striped withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th style={{ width: '40%' }}>Option</Table.Th>
                    <Table.Th>Value</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {Object.keys(selected.settings)
                    .sort()
                    .map((k) => {
                      const desc = selected.descs[k] ?? 'No description available.';
                      const isApiKey = k.includes('api_key');
                      const showInstructions =
                        isApiKey && hasApiKeyDataForSelected(selected);
                      return (
                        <Table.Tr key={k}>
                          <Table.Td>
                            <Group gap="xs" align="center">
                              <Text size="sm">{desc}</Text>
                              {showInstructions && (
                                <Popover width={320} position="right" withArrow>
                                  <Popover.Target>
                                    <ActionIcon variant="subtle" size="sm" aria-label="API key instructions">
                                      <IconHelp size={14} />
                                    </ActionIcon>
                                  </Popover.Target>
                                  <Popover.Dropdown>
                                    <Stack gap={4}>
                                      {selected.meta!.apiKeyInstructions!.map((step, i) => (
                                        <Text key={i} size="xs">{i + 1}. {step}</Text>
                                      ))}
                                    </Stack>
                                  </Popover.Dropdown>
                                </Popover>
                              )}
                            </Group>
                          </Table.Td>
                          <Table.Td>
                            <SettingInput
                              settingKey={k}
                              value={current[k] ?? selected.settings[k]}
                              onChange={(v) =>
                                setCurrent((prev) => ({ ...prev, [k]: v }))
                              }
                            />
                          </Table.Td>
                        </Table.Tr>
                      );
                    })}
                </Table.Tbody>
              </Table>
            </Stack>
          )}
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
```

- [ ] **Step 2: Modify `webui/src/router.tsx`**

Replace contents:

```tsx
import { createBrowserRouter } from 'react-router-dom';
import { ScanListPage } from './pages/ScanListPage';
import { NewScanPage } from './pages/NewScanPage';
import { OptsPage } from './pages/OptsPage';

export const router = createBrowserRouter([
  { path: '/', element: <ScanListPage /> },
  { path: '/newscan', element: <NewScanPage /> },
  { path: '/opts', element: <OptsPage /> },
]);
```

- [ ] **Step 3: Create `webui/src/pages/OptsPage.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { Mock } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MantineProvider } from '@mantine/core';
import { ModalsProvider } from '@mantine/modals';
import { Notifications } from '@mantine/notifications';
import { OptsPage } from './OptsPage';

describe('OptsPage', () => {
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
            <Notifications />
            <OptsPage />
          </ModalsProvider>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  function mockApi(optsRaw: unknown, saveResult: unknown = ['SUCCESS']) {
    (globalThis.fetch as Mock).mockImplementation((url: string) => {
      if (url === '/optsraw') {
        return Promise.resolve(
          new Response(JSON.stringify(optsRaw), { status: 200 }),
        );
      }
      if (url === '/savesettings') {
        return Promise.resolve(
          new Response(JSON.stringify(saveResult), { status: 200 }),
        );
      }
      return Promise.reject(new Error(`Unexpected URL ${url}`));
    });
  }

  const OPTS_FIXTURE = [
    'SUCCESS',
    {
      token: 7,
      data: {
        'global.webroot': '/sf',
        'module.sfp_x.enabled': true,
      },
      descs: {
        'global.webroot': 'Web root path',
        'module.sfp_x.enabled': 'Enable X',
      },
      modules: {
        sfp_x: {
          name: 'X Module',
          descr: 'summary',
          cats: [],
          labels: [],
          meta: {},
        },
      },
    },
  ];

  it('renders Global first, then modules, with values populated', async () => {
    mockApi(OPTS_FIXTURE);
    renderPage();
    expect(await screen.findByText('Web root path')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /X Module/ }) || screen.getByText('X Module')).toBeTruthy();
  });

  it('Save button is disabled when clean and enables on edit', async () => {
    mockApi(OPTS_FIXTURE);
    renderPage();
    const save = await screen.findByRole('button', { name: /Save Changes/ });
    expect(save).toBeDisabled();

    const input = await screen.findByRole('textbox', { name: 'global.webroot' });
    await userEvent.clear(input);
    await userEvent.type(input, '/newroot');
    expect(save).not.toBeDisabled();
  });

  it('saves edits via POST /savesettings with the token', async () => {
    mockApi(OPTS_FIXTURE);
    renderPage();
    const input = await screen.findByRole('textbox', { name: 'global.webroot' });
    await userEvent.clear(input);
    await userEvent.type(input, '/newroot');
    const save = screen.getByRole('button', { name: /Save Changes/ });
    await userEvent.click(save);

    await waitFor(() => {
      const calls = (globalThis.fetch as Mock).mock.calls.filter(
        (c) => c[0] === '/savesettings',
      );
      expect(calls).toHaveLength(1);
    });
    const call = (globalThis.fetch as Mock).mock.calls.find((c) => c[0] === '/savesettings');
    const body = new URLSearchParams((call![1] as RequestInit).body as string);
    expect(body.get('token')).toBe('7');
    const allopts = JSON.parse(body.get('allopts') ?? '{}');
    expect(allopts['global.webroot']).toBe('/newroot');
  });
});
```

- [ ] **Step 4: Run Vitest — expect 40 + 3 = 43 passing**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm test -- --run 2>&1 | tail -6
```

- [ ] **Step 5: Build**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run build 2>&1 | tail -6
```

- [ ] **Step 6: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add webui/src/pages/OptsPage.tsx webui/src/pages/OptsPage.test.tsx webui/src/router.tsx
git commit -m "$(cat <<'EOF'
webui: OptsPage — React replacement for Mako opts.tmpl

Left-rail NavLink list of Global + 186 modules with a filter
TextInput and a red "dirty" dot on groups with unsaved changes.
Right pane: module meta header (description, website, cats,
API-key instructions Popover) + Table of editable settings, one
SettingInput per row dispatched by value type.

Single Save button enabled only when dirty. Save count in the
button label. Actions menu hosts Import API Keys (hidden file
input, client-parsed), Export API Keys (plain <a download>), and
Reset to Factory Default (confirm modal). Notifications surface
success/failure.

Router now has 3 routes: /, /newscan, /opts.

3 Vitest cases cover initial render, dirty-detection button
gating, and save posting the correct body + token.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Retirements + Playwright + Robot cleanup

**Files:**
- Delete: `spiderfoot/templates/opts.tmpl`, `spiderfoot/static/js/spiderfoot.opts.js`.
- Modify: `test/acceptance/scan.robot` — remove `Settings page should render` keyword + its reference.
- Create: `webui/tests/e2e/04-opts.spec.ts`.

- [ ] **Step 1: Delete Mako + JS**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git rm spiderfoot/templates/opts.tmpl spiderfoot/static/js/spiderfoot.opts.js
```

- [ ] **Step 2: Sanity-check no references**

```bash
grep -rnE "opts\.tmpl|spiderfoot\.opts\.js" --include="*.py" --include="*.tmpl" --include="*.robot" --include="*.html" /Users/olahjort/Projects/OhDeere/spiderfoot
```

Expected: zero matches.

- [ ] **Step 3: Remove `Settings page should render` keyword**

Edit `test/acceptance/scan.robot`. Find:

```
Settings page should render
    Element Should Be Visible            id:savesettingsform
    Element Should Be Visible            id:btn-save-changes
    Element Should Be Visible            id:btn-import-config
    Element Should Be Visible            id:btn-opt-export
    Element Should Be Visible            id:btn-reset-settings
```

Delete the entire keyword. Then search for references:

```bash
grep -n "Settings page should render" /Users/olahjort/Projects/OhDeere/spiderfoot/test/acceptance/scan.robot
```

In `Main navigation pages should render correctly` (rewritten in milestone 1 to start at `/newscan`), remove these lines if present:

```
Click Element                        id:nav-link-settings
Wait Until Page Contains             Settings    timeout=5s
Settings page should render
```

After the surgery the test may shrink to just verifying the newscan page opens; that's fine — Playwright now owns this coverage.

- [ ] **Step 4: Create `webui/tests/e2e/04-opts.spec.ts`**

```typescript
import { test, expect } from '@playwright/test';

// Runs after 03-new-scan.spec.ts. The empty-state spec (02) wipes
// tbl_scan_instance, the new-scan spec (03) re-adds one scan row.
// /opts doesn't depend on scan data so ordering doesn't affect this
// file, but we keep the numeric prefix convention for consistency.

test.describe('Settings page', () => {
  test('renders Global tab and filters modules', async ({ page }) => {
    await page.goto('/opts');
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    // At least one global option row should render.
    await expect(page.getByRole('button', { name: /Save Changes/ })).toBeVisible();

    // Filter the left rail to narrow modules.
    const filter = page.getByLabel('Filter settings groups');
    await filter.fill('country');
    // sfp_countryname should remain visible (matches 'country').
    await expect(page.getByText('sfp_countryname')).toBeVisible();
  });

  test('reset to factory default triggers confirm modal', async ({ page }) => {
    await page.goto('/opts');
    // Open actions menu
    await page.getByRole('button', { name: 'Settings actions' }).click();
    await page.getByRole('menuitem', { name: /Reset to Factory Default/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(
      page.getByText(/This wipes every API key/),
    ).toBeVisible();
    // Cancel — don't actually reset the fixture DB.
    await page.getByRole('button', { name: 'Cancel' }).click();
    await expect(page.getByRole('dialog')).not.toBeVisible();
  });
});
```

(Two tests is enough for the E2E layer — the save happy-path is covered by Vitest, and a live save would mutate the fixture state for subsequent specs. The reset-confirm test exercises the menu + modal flow without actually firing the mutation.)

- [ ] **Step 5: Run Playwright**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot/webui && npm run test:e2e 2>&1 | tail -15
```

Expected: **9 tests pass** (3 from 01-scan-list + 1 from 02-empty-state + 3 from 03-new-scan + 2 from 04-opts).

- [ ] **Step 6: Full `./test/run` sanity check**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + **43 Vitest** + **9 Playwright** + flake8 clean + **1464 pytest** / 34 skipped.

- [ ] **Step 7: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add test/acceptance/scan.robot webui/tests/e2e/04-opts.spec.ts
git rm spiderfoot/templates/opts.tmpl spiderfoot/static/js/spiderfoot.opts.js
git commit -m "$(cat <<'EOF'
webui: retire Mako opts; add Playwright E2E for /opts

Deletes spiderfoot/templates/opts.tmpl (199 lines) +
spiderfoot/static/js/spiderfoot.opts.js (43 lines) — both
replaced by webui/src/pages/OptsPage.tsx.

test/acceptance/scan.robot loses the "Settings page should render"
keyword and its reference in Main navigation pages;
04-opts.spec.ts replaces the coverage.

2 Playwright tests: renders and filters; reset-to-factory confirm
modal opens + cancels cleanly. Live-save happy path is covered by
Vitest to avoid mutating fixture state across specs.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Docs refresh + final verification

**Files:**
- Modify: `CLAUDE.md` — update Web UI section.
- Modify: `docs/superpowers/BACKLOG.md` — mark milestone 3 shipped.

- [ ] **Step 1: Update `CLAUDE.md` Web UI section**

Find the existing `## Web UI` top paragraph:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1 and 2 (2026-04-20) migrated `/` (scan list) and `/newscan` (scan creation). Remaining Mako pages (`/scaninfo`, `/opts`, `/error`) are unchanged and reachable.
```

Replace with:

```
SpiderFoot's classic UI (CherryPy + Mako + jQuery + Bootstrap 3) is being migrated **one page at a time** to a React SPA living in `webui/`. Milestones 1–3 (2026-04-20) migrated `/` (scan list), `/newscan` (scan creation), and `/opts` (settings). Remaining Mako pages (`/scaninfo`, shared chrome via `HEADER.tmpl`/`FOOTER.tmpl`/`error.tmpl`) are unchanged and reachable.
```

- [ ] **Step 2: Update `BACKLOG.md`**

Find `### UI modernization — page-by-page migration`. Update:

**Shipped block** — append a milestone 3 line:

```
- Milestone 3 (2026-04-20) — `/opts` settings page: left-rail navigation, filterable module list, dirty indicator, Import/Export/Reset flows. Extended `/optsraw` with per-option descriptions and per-module metadata; `/savesettings` gained JSON success/error branches.
```

**Remaining Mako pages** block — remove `/opts` from the list. Leave `/scaninfo` and the shared chrome. The updated list reads:

```
**Remaining Mako pages to migrate** (each its own spec + plan):
- `/scaninfo?id=<guid>` (`scaninfo.tmpl`, ~905 lines) — the big one. Tabs for events, correlations, graph, log. Likely needs sub-milestones by tab.
- Shared chrome (`HEADER.tmpl`, `FOOTER.tmpl`, `error.tmpl`) — dies with `/scaninfo` in a final sweep.
- Clone-scan UX: re-add a Clone action to the scan list menu, backed by a new JSON endpoint. Targeted for the milestone that touches `/scaninfo`.
```

- [ ] **Step 3: Final `./test/run`**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 43 Vitest + 9 Playwright + flake8 clean + 1464 pytest / 34 skipped. If anything fails, report and STOP.

- [ ] **Step 4: Commit**

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — milestone 3 Web UI

Updates the Web UI section to reflect milestone 3 (/opts) shipped.
BACKLOG.md reshuffles the remaining-pages list: /scaninfo is now
the last real page; the rest is shared chrome (HEADER/FOOTER/error.tmpl)
that dies with scaninfo in a final sweep.

Refs docs/superpowers/specs/2026-04-20-webui-spa-milestone-3-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: Milestone summary**

Report to the user:
- 8 commits across milestone 3.
- SPA now owns `/`, `/newscan`, and `/opts`.
- 43 Vitest + 9 Playwright + 1464 pytest — all green.
- Deletions: `opts.tmpl` (199 lines), `spiderfoot.opts.js` (43 lines).
- What's next: `/scaninfo` is the final big page; the final sweep retires shared chrome.
