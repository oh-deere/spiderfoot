# Web UI SPA — Milestone 4a (`/scaninfo` shell + Status / Info / Log) Design

**Date:** 2026-04-20
**Builds on:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2,3}-design.md`
**Scope:** First of three sub-milestones for `/scaninfo`. SPA takes ownership of `/scaninfo`, ships the **Status**, **Info**, and **Log** tabs, and stubs out **Browse**, **Correlations**, and **Graph** with a placeholder panel that links to a temporarily-retained legacy route `/scaninfo-legacy?id=<guid>`. Milestone 4b fills Browse + Correlations; 4c fills Graph and retires the legacy route + `viz.js`.

---

## Goal

Give the SPA end-to-end ownership of the scan-detail URL users land on from the scan list, while preserving functional access to the not-yet-migrated tabs through an obvious escape hatch. One milestone; three tabs deeply migrated; the other three tabs discoverable but temporarily delegated.

---

## Architecture

### Backend — `sfwebui.py`

1. **Rename the current Mako `scaninfo()` handler to `scaninfo_legacy()`** at a new CherryPy route `/scaninfo-legacy`. The method body is unchanged — it still renders `scaninfo.tmpl` via Mako — only the method name, URL, and docstring change. `scaninfo.tmpl` and `HEADER.tmpl` / `FOOTER.tmpl` remain in place for now.
2. **Add a new `scaninfo()` handler** that returns `self._serve_spa_shell()` (same one-liner pattern as `index()` / `newscan()` / `opts()`).
3. **Add `/scaninfo` to `_SPA_ROUTES`** — now `{"/", "/newscan", "/opts", "/scaninfo"}`.
4. **No changes to JSON endpoints** (`/scanstatus`, `/scansummary`, `/scanopts`, `/scanlog`, `/scanerrors`, `/scanexportlogs`, `/stopscan`) — they already produce the shapes the SPA needs.
5. **No changes to `self.error()`** — still Mako; still used by the legacy handler and other code paths.

The `scaninfo_legacy()` handler is deliberately temporary. Milestone 4c deletes it (along with `scaninfo.tmpl`, `viz.js`, `spiderfoot.js`, HEADER/FOOTER/error.tmpl in the final sweep).

### Frontend — `webui/`

**New files:**
- `webui/src/api/scaninfo.ts` — `fetchScanStatus(id)`, `fetchScanSummary(id)`, `fetchScanOpts(id)`, `fetchScanLog(id, limit?)`, `stopScan(id)` (reuses existing `/stopscan` JSON endpoint).
- `webui/src/api/scaninfo.test.ts` — Vitest for the API layer.
- `webui/src/pages/ScanInfoPage.tsx` — top-level wrapper. Reads `?id=` from URL. Renders the page header + tab shell. Delegates each tab's body to a component.
- `webui/src/pages/ScanInfoPage.test.tsx` — render smoke + tab-switch + abort-button tests.
- `webui/src/pages/scaninfo/StatusTab.tsx` — Status tab.
- `webui/src/pages/scaninfo/InfoTab.tsx` — Info tab.
- `webui/src/pages/scaninfo/LogTab.tsx` — Log tab.
- `webui/src/pages/scaninfo/PlaceholderTab.tsx` — reusable "migrating" panel for Browse/Correlations/Graph.

**Modified files:**
- `webui/src/types.ts` — add `ScanStatusPayload`, `ScanSummaryRow`, `ScanOptsPayload`, `ScanLogEntry`.
- `webui/src/router.tsx` — add `/scaninfo` route pointing at `ScanInfoPage`.
- `webui/src/pages/ScanListPage.tsx` — (unchanged) the "View" action already links to `/scaninfo?id=<guid>`; the browser loads the new SPA shell transparently.

**State model:**

`ScanInfoPage` owns:
- `id` from `useSearchParams()` — if absent or `scanstatus` returns `[]`, render an Alert with "Scan not found" + a button to go back to `/`.
- `activeTab` (Mantine `Tabs` value) — `'status' | 'correlations' | 'browse' | 'graph' | 'info' | 'log'`. Local state; default `'status'`. Tab is not URL-deep-linkable in 4a — follow-up item.
- A root `useQuery(['scanstatus', id])` powers the header and drives the polling cadence via `refetchInterval`.

**Polling cadence:**

```typescript
const isRunning = (s: ScanStatus) =>
  s === 'CREATED' || s === 'STARTING' || s === 'STARTED' || s === 'RUNNING';

useQuery({
  queryKey: ['scanstatus', id],
  queryFn: () => fetchScanStatus(id),
  refetchInterval: (query) => (isRunning(query.state.data?.status) ? 5000 : false),
});
```

Each tab adds its own `useQuery` with the same polling predicate, enabled only when that tab is `activeTab` (avoids background refetches for inactive tabs — TanStack Query's `enabled` option).

### Data contracts (read from existing Python handlers)

- `GET /scanstatus?id=<guid>` → `[name, target, created, started, ended, status, riskmatrix]`.
  - `created/started/ended` are formatted date strings ("Not yet" sentinel on unstarted).
- `GET /scansummary?id=<guid>&by=type` → `[[type_id, type_label, last_seen_str, count, unique_count, scan_status], ...]`.
  - The trailing `scan_status` duplicates the header status; ignore it here.
- `GET /scanopts?id=<guid>` → `{"meta": [...], "config": {...}, "configdesc": {...}}` — scan's frozen config at kick-off time.
- `GET /scanlog?id=<guid>&limit=100` → `[[generated_ms, component, level, message, hash], ...]`. Limit unspecified returns all; we start with a cap of 500 in the UI.
- `GET /scanexportlogs?id=<guid>` → Excel file (existing handler). SPA triggers via `<Button component="a" href="/scanexportlogs?id=X" download>`.
- `GET /stopscan?id=<guid>` → JSON; `""` on success, `jsonify_error` tuple on failure.

**Typed UI shapes** (what `scaninfo.ts` exports — hides the tuple shapes):

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
  meta: string[];             // raw [name, target, created, started, ended, status]
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

### Page layout

```
┌─────────────────────────────────────────────────────┐
│ Scans ›                                             │
│                                                     │
│  <Scan Name> [ScanStatusBadge]  [Abort] [Refresh]   │
│                                                     │
│ ┌─────────────────────────────────────────────────┐ │
│ │ Status │ Correlations │ Browse │ Graph │ Info │ Log │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ ┌─── Active tab panel ────────────────────────────┐ │
│ │                                                 │ │
│ │                                                 │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

- **Back link:** "Scans ›" anchor to `/`. Plain anchor = full reload, matches milestone 1's unmigrated-link convention.
- **Header:** `Title order={2}` scan name, `ScanStatusBadge` (already built in M1), Abort button (only visible when `isRunning(status)`), Refresh button (manual refetch button that invalidates all tab queries).
- **Tabs:** Mantine `Tabs` with 6 `Tabs.Tab` entries. Placeholder tabs still render their header (clickable, switches to their panel) but the panel body is a single `PlaceholderTab` alert.

### Status tab

Summary card at the top: Mantine `SimpleGrid` of labelled stats: target, duration (if finished), module count, total event count.

Below: Mantine `Table` of event-type rows.

| Event Type | Count | Unique | Last Seen |
|---|---:|---:|---|
| INTERNET_NAME | 42 | 8 | 2026-04-20 14:23:01 |
| ... | | | |

Sorted by `count desc`. Click-to-sort disabled in 4a. Polling 5s while running.

### Info tab

Stack of read-only content:
- Scan target (as code)
- Target type
- Created / Started / Ended timestamps
- Modules used (comma-separated list; wraps)
- Mantine `Accordion` labelled "Global settings used" — inside is a `Table` of `[opt | value]` rendered from `config` (filtered to keys starting with `global.`)
- Mantine `Accordion` labelled "Module settings used" — similar filter for `module.*` keys

No edit controls; all display. No polling — this data is frozen at scan kickoff.

### Log tab

Mantine `Table` with columns `[Timestamp | Component | Level | Message]`. Latest first. `Table.Tr` color-hint by level (`ERROR` red, `WARN` orange, `INFO` dim). Mantine `Badge` for the level column.

Above the table: a `Download Logs` button (anchor to `/scanexportlogs?id=X`). Polling 5s while running; stops on terminal states.

Hard cap of 500 visible log entries to keep the DOM small — bottom of list shows "`Showing 500 of N lines. Download logs for the full list.`" if truncated. We're not building virtualized scrolling in 4a.

### Placeholder tabs

`PlaceholderTab` component renders a centered Mantine `Alert` with `color="blue"`:

> **This view is being migrated.**
> The updated Browse/Correlations/Graph views arrive in a follow-up milestone. Use the [legacy view](`/scaninfo-legacy?id=<guid>`) for now.

Single prop: `tab: string` (used in the message). Link opens in the same tab; the Mako page still handles clicking between tabs after the user's over there. Once the user returns to the SPA scan list and clicks View again, they're back in the new UI.

### Abort / Refresh behavior

- **Abort button** hits `/stopscan?id=<guid>` via `stopScan(id)` helper. `useMutation` — on success, invalidate `['scanstatus', id]` to pick up the state transition. Button color red; confirm modal with "Abort scan?" text.
- **Refresh button** invalidates all queries for the current scan (`['scanstatus', id]`, `['scansummary', id]`, `['scanopts', id]`, `['scanlog', id]`) — useful while debugging polling behavior or after the user knows something changed.

---

## Testing

### Vitest — ~7 new cases

`api/scaninfo.test.ts`:
1. `fetchScanStatus` maps the 7-tuple response to `ScanStatusPayload`.
2. `fetchScanSummary` maps rows to `ScanSummaryRow[]`.
3. `fetchScanLog` maps rows to `ScanLogEntry[]` and applies the 500-row cap.
4. `stopScan` returns on success, throws on error.

`pages/ScanInfoPage.test.tsx`:
5. Initial render fetches scan status, shows name + badge + 6 tab labels.
6. Abort button hidden when status is terminal; visible when running. Clicking triggers confirm modal.
7. Switching to a placeholder tab renders the migrating alert with the legacy URL.

### Playwright — 3 new cases in `05-scaninfo.spec.ts`

1. Navigate to `/scaninfo?id=<finished-scan-guid>`, Status tab renders with at least one event-type row.
2. Switch to Info tab, see target + modules list.
3. Switch to Log tab, see at least one log entry row. Download button has correct `href`.

(No test for Abort — the fixture's one finished scan isn't abortable. A running-scan fixture would require race-y teardown logic; defer.)

### Sanity
- Playwright's fixture DB already seeds a FINISHED `monthly-recon` scan; that's the target for `/scaninfo?id=<guid>` E2E tests.
- `./test/run` stays green.
- One new integration test asserts `/scaninfo` returns the SPA shell.
- The existing Mako integration test at `test/integration/test_sfwebui.py` `test_scaninfo_unknown_scan_id_returns_error` moves to `/scaninfo-legacy` OR gets retired. Decide during implementation: if the test still works against the legacy handler, keep it there; otherwise remove.

---

## Retirements

None in 4a. Scope:
- Rename (not delete) the Mako scaninfo handler to `scaninfo_legacy()` at `/scaninfo-legacy`.
- `scaninfo.tmpl`, `HEADER.tmpl`, `FOOTER.tmpl`, `error.tmpl`, `spiderfoot.js`, `viz.js` all stay.
- M4c retires the legacy route + template + JS + shared chrome.

---

## Rollout

- Single PR, single milestone. `/scaninfo` URL keeps working throughout (serves the SPA after the handler swap; the legacy URL `/scaninfo-legacy?id=X` becomes the documented escape hatch).
- Scan-list "View" action already points at `/scaninfo?id=X` — no change needed.
- The `/newscan` success flow lands at `/scaninfo?id=<new-guid>` — which now renders the SPA. Confirm the Status tab's auto-poll covers "scan just kicked off, status is STARTING → RUNNING → FINISHED" smoothly. The tab body will update on each 5s poll.

---

## Risks

- **Polling storm.** Running scans trigger 4 concurrent `useQuery` refetches every 5s (scanstatus + active tab). TanStack Query deduplicates within a query-key; the active-tab gating keeps inactive tabs silent. Per-scan overhead ≈ 2 requests/5s on the Status tab; Pages fine.
- **Scan not found.** `fetchScanStatus` returns `[]` when the scan ID is bogus. The typed wrapper throws a sentinel `ApiError(404, ...)` when it sees the empty tuple so the page renders a "Scan not found" Alert with a back-to-scans link.
- **`/scanlog` pagination.** Endpoint has a `limit` param we can thread through; 4a sends `limit=500` and surfaces a "download for more" hint. Polling drop-in fine.
- **Legacy link churn.** If the user bookmarks `/scaninfo-legacy` it works for 4a+4b+part of 4c, then 410s. We'll mention this in the placeholder-tab message ("temporary link").
- **Header JSON contract drift.** `/scanstatus` returns a positional tuple; brittle. Wrapper is one file, so any backend change (e.g. adding a field) surfaces as a typed error rather than a silent mis-render.

---

## Non-goals for M4a

- Browse / Correlations / Graph tab content (→ M4b / M4c).
- URL-deep-linkable tab state (follow-up).
- Virtualized log scrolling.
- Bar charts on Status tab.
- Search/filter/export on Status or Log tabs.
- Abort-confirm for running scans in E2E (fixture complexity).
- `/scaninfo.tmpl` or `viz.js` or `spiderfoot.js` retirement (→ M4c / final sweep).
- Nav bar linking the SPA pages together (→ final sweep).

---

## Open items — none

All three brainstorming questions settled:
1. SPA takes `/scaninfo`, legacy handler at `/scaninfo-legacy` for 4b-era fallback.
2. Polling cadence: 5s while running, off on terminal (matches Mako).
3. Tab scope: table-driven summaries, no charts, read-only Info, log table + download.
