# Web UI SPA — Milestone 2 (`/newscan`) Design

**Date:** 2026-04-20
**Builds on:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-1-design.md`
**Scope:** migrate the `/newscan` page from Mako + jQuery + Bootstrap 3 to the React SPA. Retire `newscan.tmpl`, its companion JS, and the orphaned `clonescan` handler. Add JSON-friendly endpoints so the SPA can submit scans cleanly.

---

## Goal

One sentence: give the SPA full page ownership of scan creation — same behavioral surface as the old Mako form (3 selection tabs), better UX on the module list (filter textbox), and no backend churn beyond two small, non-breaking JSON additions.

---

## Architecture

### Backend — `sfwebui.py`

1. **Factor SPA-shell serving** out of `index()` into a private helper:

   ```python
   def _serve_spa_shell(self) -> str:
       """Read and return webui/dist/index.html, or a fallback HTML
       page if the bundle is missing."""
   ```

   Both `index()` and the new `newscan()` call it. This keeps the fallback logic in one place and makes future SPA-owned pages a one-line handler.

2. **Add `/newscan` to `_SPA_ROUTES`** (the set is currently unused outside the comment — milestone 2 starts consulting it nowhere either, because CherryPy routes by method name; the set remains documentation for human readers who scan the file). Replace the existing `@cherrypy.expose def newscan()` body with `return self._serve_spa_shell()`.

3. **Remove `@cherrypy.expose def clonescan()`** — no SPA consumer in milestone 2 (clone functionality is deferred). The current Mako-rendering implementation has no reachable callers once `scanlist.tmpl` is gone. Safer to remove than to leave a partial handler that half-works.

4. **Extend `GET /modules`** JSON endpoint. Current shape: `[{name, descr}]`. New shape: `[{name, descr, api_key}]` where `api_key` is `True` if any option key on the module contains the substring `"api_key"`. Derivation is one line:

   ```python
   has_api_key = any("api_key" in k for k in self.config['__modules__'][m]['opts'])
   ```

   **Non-breaking for `sfcli.py`** — it only reads `name` / `descr`; extra fields are ignored.

5. **Extend `POST /startscan`** with JSON success path. Current handler returns `HTTPRedirect` on success; errors already branch on `Accept: application/json` and return a JSON array `["ERROR", "<message>"]`. Add a symmetric success branch — when `Accept: application/json` and the scan has been kicked off:

   ```python
   cherrypy.response.headers['Content-Type'] = "application/json; charset=utf-8"
   return json.dumps(["SUCCESS", scanId]).encode('utf-8')
   ```

   (Matches the existing tuple-shaped error response so the SPA parser has one shape to handle.)

### Frontend — `webui/`

New files:

- `webui/src/pages/NewScanPage.tsx` — top-level form.
- `webui/src/pages/NewScanPage.test.tsx` — Vitest render/behaviour tests.
- `webui/src/components/UseCaseTab.tsx` — use-case radio group.
- `webui/src/components/ModuleTab.tsx` — module picker with filter.
- `webui/src/components/TypeTab.tsx` — event-type picker with filter.
- `webui/src/api/modules.ts` — `listModules()`, `listEventTypes()`.
- `webui/tests/e2e/03-new-scan.spec.ts` — Playwright E2E.

Modified files:

- `webui/src/types.ts` — add `Module`, `EventType`.
- `webui/src/api/scans.ts` — add `startScan(params)` returning the new scan's `guid` as `string`.
- `webui/src/router.tsx` — add `/newscan` route → `NewScanPage`.

**State shape:**

```typescript
type SelectionMode = 'usecase' | 'type' | 'module';

// At the NewScanPage level:
const [scanName, setScanName] = useState('');
const [scanTarget, setScanTarget] = useState('');
const [mode, setMode] = useState<SelectionMode>('usecase');
const [usecase, setUsecase] = useState<'all' | 'Footprint' | 'Investigate' | 'Passive'>('all');
const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set());  // all by default
const [selectedModules, setSelectedModules] = useState<Set<string>>(new Set());  // all by default
```

`selectedTypes` / `selectedModules` start as "all" once the respective lists load — set in a `useEffect` on `listModules()` / `listEventTypes()` success. The `mode` enum drives which field the `startScan` call populates — exclusive selection, matching current backend semantics.

**Submit flow:**

1. Validate inputs client-side — disable Run Scan when any of:
   - `scanName.trim()` is empty.
   - `scanTarget.trim()` is empty.
   - `mode === 'module'` and `selectedModules.size === 0`.
   - `mode === 'type'` and `selectedTypes.size === 0`.
   - (`mode === 'usecase'` is always valid — a radio is always selected, default `all`.)
2. `useMutation` calls `startScan({ scanName, scanTarget, mode, usecase, moduleList, typeList })`.
3. On success: `window.location.href = '/scaninfo?id=' + scanId`. The SPA doesn't own `/scaninfo`; full page reload into the Mako page is intentional.
4. On error: render a Mantine `Alert` with the server's error string. Common errors: invalid target type, empty inputs (shouldn't hit — guarded client-side).

**`startScan` wire format:**

`POST /startscan` with `Content-Type: application/x-www-form-urlencoded` and `Accept: application/json`. Body fields: `scanname`, `scantarget`, `modulelist`, `typelist`, `usecase`. Only one of `modulelist` / `typelist` / `usecase` is populated based on `mode` — the others are empty strings (matches current Mako form behavior).

### UX details

- **By Use Case tab** — Mantine `Radio.Group` with the 4 options; description text from the current template rendered under each option. Default: `all`.
- **By Required Data tab** — filter `TextInput` at top; two-column `Table` below with checkbox + label per event type. Client-side filter is case-insensitive substring match on the label. Preserve "Select All / De-Select All" buttons. Start fully checked.
- **By Module tab** — filter `TextInput` at top; Select All / De-Select All buttons; `Table` of checkboxes with module name + descr + lock icon (`@tabler/icons-react`'s `IconKey`) when `api_key: true`. Client-side filter is case-insensitive substring match on module name. Start fully checked.
- **Target type hint box** — preserve the current Mako help text ("Your scan target may be one of the following...") as a collapsible `Alert` or `Accordion` section. Information-dense but useful for first-time users.

### Loading & error states

- Initial load fetches `/modules` + `/eventtypes` in parallel via TanStack Query. While loading → Mantine `Loader` in the `AppShell.Main`.
- Either query fails → Mantine `Alert` with retry.
- Submit fails → inline `Alert` above the form; form stays interactive.

---

## Routing integration

Before this milestone, `webui/src/router.tsx` has one route: `/` → `ScanListPage`. After:

```tsx
createBrowserRouter([
  { path: '/', element: <ScanListPage /> },
  { path: '/newscan', element: <NewScanPage /> },
]);
```

CherryPy's `_SPA_ROUTES` currently contains only `/`; the `newscan()` method (now SPA-shell-serving) takes over the `/newscan` path via CherryPy's method-name routing. The `_SPA_ROUTES` set stays as documentation; no code consults it in milestone 2 (consistent with milestone 1).

---

## Testing

### Vitest — ~5 new cases

`NewScanPage.test.tsx`:

1. **Renders form, modules, event types.** Mock `/modules` returning 2 modules (one with `api_key: true`) and `/eventtypes` returning 2 event types. Assert: scan-name input present, 2 modules listed, lock icon rendered next to the `api_key: true` one, 2 event types listed.
2. **Submit disabled on empty name.** Fill target only, assert Run Scan button is disabled.
3. **Submit posts correct form-encoded body.** Fill name + target, switch to module mode, uncheck one module, click Run Scan. Assert `fetch` called with path `/startscan`, method `POST`, body includes `scanname=...&scantarget=...&modulelist=<checked modules>&typelist=&usecase=`.
4. **Success navigates to scaninfo.** Mock response `["SUCCESS", "abc-guid"]`. Assert `window.location.href` set to `/scaninfo?id=abc-guid`.
5. **Error surfaces Alert.** Mock response `["ERROR", "Unrecognised target type."]`. Assert Alert with the error text visible.

### Playwright — 3 new tests in `webui/tests/e2e/03-new-scan.spec.ts`

1. **Form loads with module and type tabs populated.** Navigate to `/newscan`, switch to Module tab, assert `sfp_countryname` present.
2. **Filter narrows module list.** Switch to Module tab, type "country" in the filter, assert `sfp_countryname` visible and `sfp_dnsresolve` not visible.
3. **Submit kicks off a scan and redirects.** Fill name + target (`example.com`), switch to Module tab, De-Select All, check only `sfp_countryname`, click Run Scan. Assert URL becomes `/scaninfo?id=<some-guid>`. Accept any guid format; don't scrape DB state.

Fixture DB: seed_db already wipes + reseeds per run; nothing new needed.

### Sanity

- `./test/run` still reports all green (existing Vitest + old Playwright + pytest).
- pytest count may shift slightly if any existing test renders `newscan.tmpl` directly — check `test/unit/test_spiderfootwebui.py` for `test_newscan_*` before starting and either keep them passing against the new handler or retire them if they only assert Mako-specific behavior.

### Robot Framework cleanup

- Delete `New scan page should render` keyword (test/acceptance/scan.robot, `~lines 91-96`) — asserts DOM ids only in the deleted Mako template.
- Update `Main navigation pages should render correctly` if it still references the retired keyword (milestone 1 already rewrote its start point; likely nothing further to do).
- Leave other Robot tests untouched — they still test Mako pages (`/opts`, `/scaninfo`).

---

## Data flow

```
Browser GET /newscan
  → CherryPy newscan() → _serve_spa_shell() → webui/dist/index.html
  → React Router mounts NewScanPage
  → parallel GET /modules + GET /eventtypes
  → user fills form, picks mode, clicks Run Scan
  → POST /startscan with form-encoded body + Accept: application/json
  → CherryPy startscan() returns ["SUCCESS", <guid>]
  → SPA: window.location.href = /scaninfo?id=<guid>
  → Browser GET /scaninfo?id=<guid>
  → CherryPy scaninfo() renders Mako (unchanged until milestone 3)
```

---

## Retirements

- `spiderfoot/templates/newscan.tmpl` (116 lines) — deleted.
- `spiderfoot/static/js/spiderfoot.newscan.js` — deleted.
- `@cherrypy.expose def clonescan(self, id)` in `sfwebui.py` — removed entirely.
- Robot `New scan page should render` keyword — removed.

---

## Rollout

Single PR, single milestone. No feature flag. The SPA's scan-creation form replaces the Mako form in one atomic change; the `startscan` backend handler continues to accept both SPA-flavored JSON and legacy form-posted requests until a future sweep removes the legacy branches (not in this milestone — someone might be running `curl` against it).

---

## Risks

- **Module count (186) in a table with 186 checkboxes** — filter mitigates UX, but initial render can feel slow. Mantine's `Table` is fine up to several hundred rows; if measurable latency shows up on the Playwright run, we'll add virtualization later. Milestone 2 doesn't virtualize.
- **Form semantics drift.** The current `/startscan` logic prefers `modulelist` if present, then `typelist`, then `usecase`. The SPA preserves this by only populating the field matching the selected mode. Unit test #3 pins this.
- **Clone path broken in the interim.** Nobody can reach `clonescan` once milestone 1 removed the Mako scanlist, and the scan-list Playwright specs don't reference it. Removing the handler is cleaner than leaving a half-working endpoint. Clone lands as a separate backlog item (UI for clone + JSON endpoint + scan-list menu item).
- **Static Mako target-type hint box.** Long list of target-type examples; preserved in the SPA as a collapsible `Accordion`. Easier to ignore than to reformat into structured data, and the text doesn't change year to year.

---

## Non-goals

- No multi-target batch scan creation.
- No module-group filter on the Module tab (e.g. "show only Passive modules").
- No saved scan templates / presets.
- No diff view against a cloned scan.
- No nav bar / sidebar beyond the `AppShell.Header` inherited from milestone 1.

---

## Explicit open items — none

The brainstorming round settled the five judgment calls (keep 3 tabs; defer clone; extend `/modules` not add new; JSON success from `/startscan`; add filter). No TBDs remain at design time.
