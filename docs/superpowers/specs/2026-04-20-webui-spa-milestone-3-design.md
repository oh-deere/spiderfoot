# Web UI SPA — Milestone 3 (`/opts`) Design

**Date:** 2026-04-20
**Builds on:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2}-design.md`
**Scope:** migrate the `/opts` settings page from Mako + jQuery + Bootstrap 3 to the React SPA. Retire `opts.tmpl` and `spiderfoot.opts.js`. `error.tmpl` stays until the scaninfo milestone (shared chrome dies with the last Mako page).

---

## Goal

Replace the left-rail settings UI with the same behavioral surface: Global tab + one tab per module, editable options, one global Save, Import/Export API keys, Reset to Factory Default. Use the existing `/optsraw` JSON endpoint for reads and add a JSON success branch to `/savesettings` for writes.

---

## Architecture

### Backend — `sfwebui.py`

1. **Replace the `opts()` handler body** with `return self._serve_spa_shell()` (same pattern as milestone 2's `newscan`). Drop the Mako import/render. Keep the `@cherrypy.expose` decorator.
2. **Add `/opts` to `_SPA_ROUTES`** — now `{"/", "/newscan", "/opts"}`. Documentation for human readers; CherryPy continues to dispatch by method name.
3. **Extend `savesettings()` with JSON branches.** Current flow:
   - On error (token mismatch / parse failure / save failure) → `return self.error("<msg>")` (HTML).
   - On reset success → `raise HTTPRedirect('/opts?updated=1')`.
   - On save success → `raise HTTPRedirect('/opts?updated=1')`.
   
   After this milestone, when the request sets `Accept: application/json`:
   - Error paths return `["ERROR", "<message>"]` as JSON with 200 (matches `/startscan` convention).
   - Success paths return `["SUCCESS"]` as JSON with 200.
   
   Legacy form-post callers (no `Accept` header, e.g. the old Mako upload-form path) still get HTML + redirect, so nothing else in the codebase breaks. Small `_wants_json()` helper keeps the branching readable.
4. **Extend `/optsraw`** to also return per-option descriptions and per-module metadata. The Mako template consults `opts['__globaloptdescs__']`, `opts['__modules__'][mod]['descr']`, `optdescs`, `meta.dataSource.*`, `cats`, `labels` — the SPA needs the same data. After extension the payload becomes:

   ```json
   ["SUCCESS", {
     "token": 12345678,
     "data": {                               // unchanged — flat key:value
       "global.webroot": "/sf",
       "module.sfp_x.foo": true,
       ...
     },
     "descs": {                              // NEW — flat key:description
       "global.webroot": "Web server root path",
       "module.sfp_x.foo": "Enable foo mode",
       ...
     },
     "modules": {                            // NEW — per-module metadata
       "sfp_x": {
         "name": "X Module",
         "descr": "Summary sentence.",
         "cats": ["Content Analysis"],
         "labels": ["tool"],
         "meta": {                            // from self.config['__modules__'][m]['meta']
           "dataSource": {
             "website": "https://example.com",
             "description": "...",
             "apiKeyInstructions": ["Step 1...", "Step 2..."]
           }
         }
       }
     }
   }]
   ```

   The `data` shape is unchanged — additive. Existing `/optsraw` callers (sfcli? none found; a couple of tests) ignore the new keys.
5. **`/optsexport` unchanged** — `text/plain` download; SPA triggers via `<a download>`.
6. **`self.error()` unchanged** — still renders `error.tmpl`. Other Mako-era callers (scaninfo) continue to use it until the scaninfo milestone.

### Frontend — `webui/`

**New files:**
- `webui/src/api/settings.ts` — `fetchSettings()`, `saveSettings(token, allopts)`, `resetSettings(token)`, `parseConfigFile(contents)` (for import).
- `webui/src/api/settings.test.ts`.
- `webui/src/pages/OptsPage.tsx` — top-level form.
- `webui/src/pages/OptsPage.test.tsx`.
- `webui/src/components/SettingInput.tsx` — one component that dispatches on the runtime value type (`int` → `NumberInput`, `string` → `TextInput`, `bool` → `Switch`, `list` → comma-separated `TextInput`).
- `webui/tests/e2e/04-opts.spec.ts`.

**Modified files:**
- `webui/src/types.ts` — add `SettingValue`, `SettingsPayload`, `SettingsGroup`.
- `webui/src/router.tsx` — add `/opts` route.

**Data shape from `/optsraw`** — see the backend section for the full envelope. The SPA consumes `data`, `descs`, and `modules` and normalizes into:

```typescript
type SettingValue = number | string | boolean | string[] | number[];

type ModuleMeta = {
  name: string;
  descr: string;
  cats: string[];
  labels: string[];
  dataSourceWebsite?: string;
  dataSourceDescription?: string;
  apiKeyInstructions?: string[];
};

type SettingsGroup = {
  key: string;                            // "global" or "module.sfp_foo"
  label: string;                          // "Global" or ModuleMeta.name
  settings: Record<string, SettingValue>; // flat key → current value
  descs: Record<string, string>;          // flat key → description
  meta?: ModuleMeta;                      // present only for module groups
};

type SettingsPayload = {
  token: number;
  groups: SettingsGroup[];                // Global first, then modules sorted by name
};
```

**Page layout:**

- Top bar: `Title`, `Button: Save Changes` (red/disabled when clean), `Menu: actions` (Import / Export / Reset).
- Body: `Grid`:
  - Left col 3: `TextInput` filter above a `ScrollArea` of `NavLink` items. "Global" pinned first.
  - Right col 9: selected group's pane — module meta header (description, website, API-key instructions as Popover) for module groups; Table of `Option | Value` pairs.

**Form state:**

```typescript
const [token, setToken] = useState<number | null>(null);
const [original, setOriginal] = useState<Record<string, SettingValue>>({});
const [current, setCurrent] = useState<Record<string, SettingValue>>({});
const [activeGroup, setActiveGroup] = useState<string>('global');
const [filter, setFilter] = useState('');
```

Dirty detection: `const dirty = useMemo(() => Object.keys(current).filter(k => !isEqual(current[k], original[k])), [current, original]);`.

Save button disabled when `dirty.length === 0 || savingMutation.isPending`.

Navigation between groups is stateful — user's in-progress edits in one group persist while they switch to another.

**Import API Keys flow:**
1. User clicks Import in the actions Menu.
2. Hidden `input[type=file]` triggers.
3. On file select, SPA reads the file as text, parses `foo=bar\n` lines into a `Record<string, string>` (keys are already in the `global.foo` / `module.mod.opt` shape the server expects).
4. Values coerce to match the original types (e.g. `"1"` → `true` for a bool, `"5"` → `5` for int) — use the type of `original[key]` as the coercion target. Unknown keys skip with a console warning (don't block the import).
5. Merged values go into `current` state. User sees the dirty badge, reviews, clicks Save.

**Export API Keys:** `<Anchor component="a" href="/optsexport" download>Export API Keys</Anchor>` inside the actions Menu. Browser handles the download.

**Reset to Factory Default:** Mantine `openConfirmModal` → `resetSettings(token)` → on success, refetch `/optsraw`, reset `original` + `current` + `dirty`, notify.

**Save serialization:**

The flat `current` map is already in the `global.foo` / `module.mod.opt` shape the server expects. `saveSettings()` posts it as `application/x-www-form-urlencoded` with `allopts=<JSON>&token=<token>` (matching current Mako form behavior) plus `Accept: application/json`.

Bool values serialize to `"1"` / `"0"` to match the server's existing parsing (the Mako select currently emits `value=1` / `value=0`). Lists serialize to comma-joined strings. Strings and numbers pass through.

### UX details

- **NavLink color state:** pinned groups use Mantine's `active` style. Dirty groups (those with at least one unsaved change) get a small red dot via `rightSection={<Badge size="xs" color="red" variant="dot" />}`. Helps the user find where the unsaved edits live.
- **Per-field revert?** Out of scope. Reset to Factory is the only revert; per-field revert is a future enhancement.
- **Scroll behavior:** selected group scrolls its pane independently of the left rail. Mantine `ScrollArea` on both.
- **Bool values:** Mantine `Switch`. The Mako used a select; Switch is cleaner and the data round-trip is identical.
- **List values:** `TextInput` with a small `description="Comma-separated"` under it. The underlying form value is the raw string; coerce to `string[]` / `number[]` only on serialize.
- **API-key instructions Popover:** when a module's `meta.dataSource.apiKeyInstructions` is non-empty, render a `Popover` trigger next to the `api_key` row showing a numbered list with clickable URLs.

---

## Testing

### Vitest — ~6 new cases

`api/settings.test.ts`:
1. `fetchSettings()` unwraps `["SUCCESS", {token, data, descs, modules}]` into a typed `SettingsPayload` with groups ordered Global-first.
2. `saveSettings()` posts form-encoded `allopts=<json>&token=<num>` with `Accept: application/json`.
3. `resetSettings()` posts `allopts=RESET&token=<num>`.
4. `parseConfigFile("global.a=1\nmodule.sfp.b=hello\n")` → `{ "global.a": "1", "module.sfp.b": "hello" }`.

`pages/OptsPage.test.tsx`:
5. Initial render: shows Global tab active, modules in NavLink list, values populate inputs.
6. Editing an input flips dirty → Save button enables; clicking Save posts the dirty map; success notification shown.

### Playwright — 3 new tests in `04-opts.spec.ts`

1. `/opts` loads with the Global tab visible; filter narrows modules.
2. Edit a Global option (e.g. `_socks1type`), click Save, navigate away + back, see the new value persist.
3. Reset to Factory Default: actions menu → Reset → confirm → settings revert.

### Sanity
- `./test/run` still green: baseline + new counts.
- `/opts` renders the SPA shell when hit with no `Accept: application/json` (existing integration test continues to pass — body assertion needs updating like milestone 2 did for `/newscan`).

---

## Retirements

- `spiderfoot/templates/opts.tmpl` (199 lines).
- `spiderfoot/static/js/spiderfoot.opts.js` (43 lines).
- Robot `Settings page should render` keyword (if present at `test/acceptance/scan.robot`) + its usage in the "Main navigation pages" test.
- Python unit/integration tests that asserted Mako-specific content in `/opts` — update like milestone 2 did for `/newscan`.

---

## Retained

- `self.error()` helper + `error.tmpl` — used by other Mako handlers (scaninfo). Retires with milestone 4+ (scaninfo) or the final sweep.
- `/savesettings` legacy form-post path with `HTTPRedirect` — kept for backwards compatibility; no other caller exists but the branch is cheap.

---

## Data flow

```
Browser GET /opts
  → CherryPy opts() → _serve_spa_shell() → webui/dist/index.html
  → React Router mounts OptsPage
  → GET /optsraw → [SUCCESS, {token, data}]
  → SPA builds per-group map; user edits → dirty tracking
  → User clicks Save
  → POST /savesettings with form-urlencoded allopts=<json> + token, Accept: application/json
  → CherryPy savesettings() → ["SUCCESS"]
  → SPA refetches /optsraw to pick up the new token + any server-side coercions
```

---

## Risks

- **Type coercion on import.** Config files encode booleans as `"1"`/`"0"`, ints as strings, lists as comma-joined strings. The SPA coerces per the original value's type. Edge case: if a field's original value is `""` and the file supplies `"5"`, we keep it as `"5"` (string). Pure type-of-original dispatch — documented in `settings.ts`'s parse helper.
- **186 `NavLink` items.** Mantine handles this fine; measured no scroll jank in milestone 2's ModuleTab under Playwright. Defensible without virtualization.
- **CSRF token rotation.** Server rotates the token on every `/optsraw` fetch. SPA always uses the most recent token from the last fetch. If save fails with "Invalid token", the error surfaces as an inline Alert; a refetch on Save-error (automatic or via Retry button) fixes it.
- **List-of-int round trip.** `[1,2,3]` → `"1,2,3"` → split/map(Number) → `[1,2,3]`. Empty string → `[]`. Leading/trailing whitespace trimmed. Covered by unit tests.

---

## Non-goals

- Per-module save button, per-field revert, or batched tab-level save.
- Rich form for list-of-string values (TagsInput) — kept as comma-separated TextInput for parity.
- Search across options (only left-rail module name filtering).
- Nav chrome / top navbar between Scans/NewScan/Settings — deferred to final-sweep milestone.
- `self.error()` conversion (depends on scaninfo migration).

---

## Explicit open items — none

Q1-Q3 settled during brainstorming (left-rail NavLink + filter; global Save button with dirty indicator; `/savesettings` JSON extension mirroring `/startscan`). No TBDs.
