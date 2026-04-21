# Web UI SPA — Milestone 5 (final sweep) Design

**Date:** 2026-04-20
**Builds on:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2,3,4a,4b,4c}-design.md`
**Scope:** Retire every remaining Mako template, legacy JS/CSS bundle, and vendored `node_modules/` dependency. Convert `self.error()` + `error_page_404` to inline HTML strings (no Mako, no HEADER/FOOTER/error.tmpl). Remove the legacy `/static` CherryPy mount (only `/static/webui/` remains). Add the Clone-scan UX that was deferred from M2: a `Clone` action on ScanListPage's row menu, a new JSON `/clonescan` endpoint, and `/newscan?clone=<guid>` prefill handling.

---

## Goal

Close out the UI retirement: **no Mako, no jQuery, no Bootstrap 3, no vendored legacy `node_modules/`, no unused CSS or JS files.** A handful of inline HTML strings remain inside Python helpers as fallback paths (identical to Spring Boot's default error surface). After this milestone the only HTML rendered by the app comes from the built SPA bundle or those stub helpers.

---

## Architecture

### Backend — `sfwebui.py`

1. **Delete Mako imports**:
   ```python
   from mako.lookup import TemplateLookup
   from mako.template import Template
   ```
   Remove both lines.
2. **Delete `self.lookup = TemplateLookup(directories=[''])`** in `__init__`.
3. **Rewrite `self.error(message)` body** — no Mako lookup, no HEADER/FOOTER. Return an inline HTML string:
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
           "<body style=\"font-family: sans-serif; padding: 2rem; max-width: 48rem; margin: 0 auto;\">"
           "<h1>Something went wrong</h1>"
           f"<p>{safe_message}</p>"
           f"<p><a href=\"{self.docroot}/\">← Back to scan list</a></p>"
           "</body></html>"
       )
   ```
   All 23 existing callers (`return self.error("...")`) remain unchanged — the signature is `(message: str) -> str`.
4. **Rewrite `error_page_404()`** identically:
   ```python
   def error_page_404(self, status, message, traceback, version) -> str:
       return (
           "<!DOCTYPE html>"
           "<html lang=\"en\"><head><meta charset=\"utf-8\">"
           "<title>SpiderFoot — Not Found</title></head>"
           "<body style=\"font-family: sans-serif; padding: 2rem; max-width: 48rem; margin: 0 auto;\">"
           "<h1>Page not found</h1>"
           f"<p>{html.escape(status)}: {html.escape(message)}</p>"
           f"<p><a href=\"{self.docroot}/\">← Back to scan list</a></p>"
           "</body></html>"
       )
   ```
   Drop the unused `traceback`, `version` params from the body (CherryPy's `error_page_404` hook still passes them; the method accepts them in signature but ignores).
5. **Add `GET /clonescan` JSON endpoint**:
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
       return {
           'scanName': info[0],
           'scanTarget': info[1],
           'modulelist': [m for m in module_list if m and m != 'sfp__stor_stdout'],
           'typelist': [],   # not preserved in scanConfigGet
           'usecase': '',    # module-list prefill takes priority
       }
   ```
6. **Retirements in `sfwebui.py`**: After the above, there should be zero references to `Template`, `TemplateLookup`, `self.lookup`, or any `spiderfoot/templates/*.tmpl` file. Verify with grep before closing the milestone.

### Backend — `sf.py`

Remove the `/static` entry from the `conf` dict used for `cherrypy.quickstart`. Only `/static/webui` remains:

```python
conf = {
    '/static/webui': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': _SPA_DIST,
        'tools.staticdir.index': 'index.html',
    }
}
```

No other consumers reference `/static/...` after this milestone — HEADER.tmpl / FOOTER.tmpl / scaninfo.tmpl were the only sources of `/static/node_modules/` and `/static/js/` references, and they're all retired.

### Frontend — `webui/`

#### 1. Clone-scan fetch + types

`webui/src/api/scans.ts` — add:

```typescript
type CloneScanResponse = {
  scanName: string;
  scanTarget: string;
  modulelist: string[];
  typelist: string[];
  usecase: string;
};

export async function fetchScanClone(id: string): Promise<{
  scanName: string;
  scanTarget: string;
  moduleList: string[];
  typeList: string[];
  usecase: UseCase;
}> {
  const raw = await fetchJson<CloneScanResponse>(
    `/clonescan?id=${encodeURIComponent(id)}`,
  );
  // Backend serves camelCase `scanName`/`scanTarget` but snake_case
  // `modulelist`/`typelist` (matches the /startscan form-post contract).
  // Normalize to the camelCase we use elsewhere in the SPA.
  return {
    scanName: raw.scanName,
    scanTarget: raw.scanTarget,
    moduleList: raw.modulelist ?? [],
    typeList: raw.typelist ?? [],
    usecase: (raw.usecase || 'all') as UseCase,
  };
}
```

#### 2. NewScanPage prefill

`webui/src/pages/NewScanPage.tsx` — extend:

- Read `?clone=<guid>` via `useSearchParams`.
- If present, run `useQuery(['clonescan', cloneId])` to fetch the prefill data.
- Seed form state once both `/modules` (already fetched) and the clone fetch resolve. Use a one-shot `useEffect` guarded by a ref so the user's post-prefill edits aren't clobbered by a refetch.
- Append " (clone)" to the scan name to make accidental duplicate scans obvious.
- Mode inference: if `moduleList.length > 0` → `mode='module'`; else if `typeList.length > 0` → `mode='type'`; else `mode='usecase'`.

#### 3. ScanListPage Clone action

`webui/src/pages/ScanListPage.tsx` — inside each row's action menu, add a new Menu.Item above the existing "Delete":

```tsx
<Menu.Item
  component="a"
  href={`/newscan?clone=${encodeURIComponent(scan.guid)}`}
>
  Clone
</Menu.Item>
```

Plain `<a>` — triggers a full reload into `/newscan`, which is another SPA route so React Router picks it up after the Vite shell is re-served. Matches the existing pattern for `/scaninfo` links (full-page navigation between SPA routes).

### Retirements — file-system deletions

One commit at the end of the milestone deletes:

- `spiderfoot/templates/HEADER.tmpl`
- `spiderfoot/templates/FOOTER.tmpl`
- `spiderfoot/templates/error.tmpl`
- `spiderfoot/static/js/spiderfoot.js`
- `spiderfoot/static/css/spiderfoot.css`
- `spiderfoot/static/css/dark.css`
- `spiderfoot/static/package.json` + `package-lock.json` if present
- `spiderfoot/static/node_modules/` (entire directory — jquery, bootstrap3, d3, sigma, tablesorter, alertifyjs)

Also remove (if the `spiderfoot/templates/` directory would be empty after the three .tmpl deletions):
- The `spiderfoot/templates/` directory itself (`git rm -r` handles this if all files are gone).

Keep:
- `spiderfoot/static/img/` — contains spiderfoot favicon PNGs. Not referenced by the SPA (Vite ships its own favicon.svg), but worth auditing before deletion. If nothing references them, delete in this milestone; otherwise defer.

Audit:

```bash
grep -rn "/static/img/" spiderfoot/ webui/ sfwebui.py sf.py
```

Expected after the Mako purge: zero matches. If confirmed, delete `spiderfoot/static/img/` too; otherwise keep and document.

### Python test cleanup

`self.error()` return value changes from rendered Mako to inline HTML. Any pytest integration test that asserted specific Mako-era strings (e.g. `"SpiderFoot v${version}"` from HEADER.tmpl, footer spam text, class names like `alert-danger`) will break. Locate and update:

```bash
grep -rn "alert-danger\|navbar-default\|spiderfoot-header\|aboutmodal" test/
```

Update the assertions to match the new minimal HTML body (look for "Something went wrong" / "Back to scan list" / "Page not found"). A rough count from `test/integration/test_sfwebui.py` + `test/unit/test_spiderfootwebui.py`: probably 5-10 assertions to fix.

New integration test for `/clonescan`:

```python
def test_clonescan_unknown_scan_returns_404(self):
    self.getPage("/clonescan?id=doesnotexist")
    self.assertStatus('404 Not Found')
    body = json.loads(self.body)
    self.assertEqual(body['error']['http_status'], '404')
```

Happy-path test would require a seeded scan via fixtures — skip for now (Playwright covers it end-to-end).

---

## Testing

### Vitest — ~2 new cases

1. `fetchScanClone` unwraps the `/clonescan` response into camelCase with default empty arrays and `usecase='all'` fallback.
2. NewScanPage seeds form state from a `?clone=<guid>` URL — mock `/modules` + `/eventtypes` + `/clonescan`, render NewScanPage at `/newscan?clone=abc`, assert Scan Name input has the cloned name + " (clone)" suffix and the Module tab is active.

### Playwright — 1 new case in `08-clone-scan.spec.ts`

1. From scan list, open the monthly-recon row's action menu → click Clone → navigate to `/newscan?clone=<guid>` → assert Scan Name input contains `"monthly-recon (clone)"`.

Actual scan kickoff from the cloned prefill isn't tested (too slow/flaky); the NewScanPage submit path is already covered by M2's 03-new-scan.spec.ts.

### Python — 1 new + N updates

- 1 new: `test_clonescan_unknown_scan_returns_404` (structure above).
- N updates: any integration/unit test that asserted specific Mako-era HTML strings. Fix by searching for the common tokens listed above.

### Sanity

- `./test/run` stays green.
- `grep -rn "mako" sfwebui.py sf.py` → zero matches.
- `grep -rn "TemplateLookup\|Template(" sfwebui.py sf.py` → zero matches.
- `grep -rn "/static/node_modules\|/static/js\|/static/css" .` (excluding `docs/` and `webui/`) → zero matches.
- `python3 -c "from sfwebui import SpiderFootWebUi"` doesn't `ImportError`.

---

## Risks

- **`self.error()` still expects kwargs like `docroot`.** The old Mako called it with `self.docroot`. In the rewrite we reference `self.docroot` directly from the method. No caller change needed, but double-check during implementation — the attribute is set in `__init__` from the app config.
- **`error_page_404` signature.** CherryPy invokes it with `(status, message, traceback, version)` kwargs. The inline-HTML rewrite accepts all four and ignores the `traceback` + `version`. Don't remove the parameters from the signature or CherryPy will crash with a TypeError when a 404 fires.
- **sfcli.py doesn't use `/clonescan`.** The old Mako `clonescan` handler pre-filled an HTML form; sfcli never consumed it. Adding the new JSON endpoint doesn't break sfcli.
- **Module lists stored in `scanConfigGet`.** After M5 the only consumer of `_modulesenabled` in scan config is the new `/clonescan` endpoint. The existing `rerunscan` / `rerunscanmulti` handlers use the same DB call — just verify the field name hasn't drifted in recent db.py changes.
- **Old Mako error pages that referenced specific HTTP status codes**. CherryPy's `cherrypy.HTTPError(400, "…")` still works; our new HTML error just drops the status prominence. Acceptable.
- **Image/favicon orphans.** `spiderfoot/static/img/spiderfoot-icon.png` + `spiderfoot-header.png` + `spiderfoot-header-dark.png` are all HEADER.tmpl-only references. After the grep audit confirms nothing else points at them, delete the directory.

---

## Non-goals for M5

- Error-page styling beyond basic inline CSS (padding + readable font). `curl` / sfcli are the only expected consumers.
- Removing `jsonify_error()` — still used by every API error path.
- Adding a "recently cloned scans" history to NewScanPage.
- Multi-scan clone UX.
- Prefilling the typelist from a clone (backend doesn't preserve it; would require a schema change that's out of scope).
- Dark-mode CSS — the Mantine theme handles that; `dark.css` just goes away.
- Migrating `sfcli.py` to use new endpoints — out of scope; it already works against the JSON API.

---

## Explicit open items — none

Brainstorming settled the two architectural choices:
1. `self.error()` strategy: **plain inline HTML string** (option A). 23 call sites untouched.
2. Clone contract: **dedicated `GET /clonescan` JSON endpoint** (option A). User edits before submitting.
3. Fallback HTML stays as stubs (matches Spring Boot default error behavior).

After M5: the only HTML in the Python codebase is ~35 lines of fallback inside three helpers (`self.error()`, `error_page_404()`, `_serve_spa_shell()`). All runtime SPA rendering comes from `webui/dist/`.
