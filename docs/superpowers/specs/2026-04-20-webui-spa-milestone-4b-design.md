# Web UI SPA — Milestone 4b (`/scaninfo` Browse + Correlations) Design

**Date:** 2026-04-20
**Builds on:** `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2,3,4a}-design.md`
**Scope:** Second of three `/scaninfo` sub-milestones. Replaces the Browse + Correlations placeholder panels with working React implementations. Graph tab remains a placeholder until M4c.

---

## Goal

Migrate two tabs without touching the backend. Every endpoint the new UI needs already exists and returns JSON. Scope is deliberately generous on the drill-in interactions (false-positive toggle, full/unique view, value search, export) to avoid users needing the `/scaninfo-legacy` escape hatch for day-to-day Browse work.

---

## Architecture

### Backend — `sfwebui.py`

**Zero changes.** Endpoints already in place, already JSON:

| Endpoint | Shape | M4b use |
|---|---|---|
| `GET /scaneventresults?id=X&eventType=Y&filterfp=true\|false&correlationId=Z` | 11-field rows | Browse events, correlation drill-in |
| `GET /scaneventresultsunique?id=X&eventType=Y&filterfp=true\|false` | unique-value rows | Full/Unique toggle |
| `GET /scancorrelations?id=X` | 8-field rows | Correlations list |
| `GET /search?id=X&eventType=Y&value=Z` | same shape as `/scaneventresults` | Value search on Browse |
| `GET /scaneventresultexport?id=X&type=Y&filetype=csv\|excel` | streamed file | Export current view |
| `GET /resultsetfp?id=X&fp=0\|1&resultids=<json-array>` | tuple (`["SUCCESS", …]` / `["WARNING", msg]` / `["ERROR", msg]`) | Per-row FP toggle |

Row shape reference:

- `/scaneventresults` row: `[lastseen, data, source_data, source_module, source_event_hash, hash, _lastseen_raw, source_module_hash, fp, risk, event_type]` (11 fields, hence positional indices matter — the SPA hides them inside one mapper).
- `/scancorrelations` row: `[id, headline, collection, rule_id, rule_name, rule_descr, rule_risk, events_count]` (8 fields; `rule_risk` ∈ `HIGH | MEDIUM | LOW | INFO`).

### Frontend — `webui/`

**Extended API** (`webui/src/api/scaninfo.ts`):

```typescript
export type ScanEventRow = {
  hash: string;             // event row hash (used by FP toggle)
  lastSeen: string;         // formatted date
  data: string;             // the event's data
  sourceData: string;       // parent event's data
  sourceModule: string;     // module that produced this event
  sourceEventHash: string;
  sourceModuleHash: string;
  fp: boolean;              // false-positive flag
  risk: string;             // 'NONE' | 'LOW' | 'MEDIUM' | 'HIGH' | 'INFO'
  eventType: string;
};

export async function fetchScanEvents(args: {
  id: string;
  eventType?: string;
  correlationId?: string;
  filterFp?: boolean;
}): Promise<ScanEventRow[]>;

export async function fetchScanEventsUnique(args: {
  id: string;
  eventType: string;
  filterFp?: boolean;
}): Promise<ScanEventRow[]>;

export async function searchScanEvents(args: {
  id: string;
  eventType: string;  // 'ALL' when cross-type
  value: string;
}): Promise<ScanEventRow[]>;

export async function fetchCorrelations(id: string): Promise<CorrelationRow[]>;

export async function toggleFalsePositive(args: {
  id: string;
  resultIds: string[];  // event row hashes
  fp: boolean;
}): Promise<void>;
```

**New types** (`webui/src/types.ts`):

```typescript
export type EventRisk = 'NONE' | 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH';

export type CorrelationRisk = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH';

export type CorrelationRow = {
  id: string;
  headline: string;
  collection: string;
  ruleId: string;
  ruleName: string;
  ruleDescr: string;
  ruleRisk: CorrelationRisk;
  eventsCount: number;
};

export type EventViewMode = 'full' | 'unique';
```

**New components** (`webui/src/pages/scaninfo/`):

- `BrowseTab.tsx` — state machine: `{ view: 'type-list' | 'events'; selectedType: string | null; ... }`.
- `CorrelationsTab.tsx` — state machine: `{ view: 'list' | 'events'; selectedCorrelation: CorrelationRow | null }`.
- `EventList.tsx` — shared drill-in table used by both Browse and Correlations. Props:
  ```typescript
  type EventListProps = {
    id: string;
    eventType?: string;       // Browse path
    correlationId?: string;   // Correlation path
    onBack: () => void;       // breadcrumb action
    backLabel: string;        // "All event types" / "All correlations"
    headerTitle: string;      // the event-type label or correlation headline
  };
  ```
  Encapsulates view-mode toggle (full/unique), filter-FP switch, search textbox, export menu (CSV/Excel), and the events table with per-row FP action.
- `EventTypeList.tsx` — clickable event-type summary. Reuses the `fetchScanSummary` query (same queryKey as Status tab — no extra fetch). Each row's type label is an `Anchor` that calls `onSelect(typeId, typeLabel)`.
- `CorrelationsList.tsx` — Mantine Table of correlations; rows clickable; risk column uses `CorrelationRiskBadge`.
- `CorrelationRiskBadge.tsx` — small `Badge` with color map `HIGH → red / MEDIUM → orange / LOW → yellow / INFO → blue`.

**Modified:** `ScanInfoPage.tsx` — replace the two remaining PlaceholderTab usages (Browse, Correlations) with the new tab components. Graph stays on PlaceholderTab.

### State & navigation

- All within-tab navigation is **local `useState`**. Switching away from a tab and back resets its sub-state — matches the default Mantine Tabs unmount behavior. Not worth the complexity of URL query params until final-sweep milestone revisits sub-state deep-linking.
- `ScanInfoPage.tsx`'s existing `refreshAll` callback invalidates all scaninfo query keys; Browse + Correlations queries will follow the same `['scaneventresults', id, …]` / `['scancorrelations', id]` keying so `Refresh` Just Works.

### UX details

**BrowseTab, view = `'type-list'`:**

- Title: "Browse by event type"
- Table: same 4-column layout as Status tab (`Event type | Count | Unique | Last seen`), clickable rows. When user clicks a row, `setView('events')` + `setSelectedType(...)`. Query reuses `['scansummary', id]`.

**BrowseTab, view = `'events'` (delegates to `EventList`):**

- Breadcrumb button: `← All event types` → sets `view='type-list'`.
- Title: the event-type label.
- Toolbar (left to right): `SegmentedControl` (Full / Unique), `Switch` (Hide false positives, default ON), `TextInput` (value search — plain substring), Export `Menu` (CSV / Excel).
- Table columns: `Last seen | Data | Source data | Source module | Risk | FP | Actions`.
  - `Risk`: small colored Badge (`HIGH/MEDIUM/LOW` or dimmed "—" for `NONE`).
  - `FP`: ✓ if `fp: true`, empty cell otherwise.
  - `Actions`: Mantine `Menu` with one item, "Mark FP" or "Unmark FP" depending on current state.
- Search: empty string → normal `/scaneventresults` query; non-empty string → `/search` query. `useQuery` queryKey flips so the cache doesn't collide.

**CorrelationsTab, view = `'list'`:**

- Title: "Triggered correlations"
- Table columns: `Risk | Headline | Rule | Events`. Rows clickable → drill in.
- Empty state: Mantine Alert "No correlations triggered for this scan."

**CorrelationsTab, view = `'events'` (delegates to `EventList`):**

- Breadcrumb: `← All correlations` → sets `view='list'`.
- Title: the correlation's headline + CorrelationRiskBadge.
- Subtitle line: the correlation's `ruleDescr`.
- Same `EventList` component as Browse, but props populate `correlationId` (not `eventType`), and the Full/Unique toggle is hidden (no unique-variant endpoint for correlation-filtered events).

### FP-toggle flow

1. User clicks the row action Menu → "Mark FP" (or "Unmark FP").
2. `useMutation` → `toggleFalsePositive({ id, resultIds: [row.hash], fp: !row.fp })`.
3. On success: invalidate the active event-list query and show a Mantine notification ("Event marked as false positive." / "False-positive flag removed.").
4. On error: inline Alert above the table with the server's message.

Bulk multi-select is explicitly out of scope (users can do one-at-a-time). Legacy-checkbox support lives at `/scaninfo-legacy` until the final-sweep milestone decides whether to build bulk UI in the SPA or retire the capability.

### Export flow

Plain anchor with `download` attribute:

```tsx
<Menu.Item component="a" href={`/scaneventresultexport?id=${id}&type=${eventType}&filetype=csv`} download>
  Export CSV
</Menu.Item>
```

CherryPy already sets `Content-Disposition: attachment` on that endpoint. Browser handles the download without SPA glue. Export always reflects the currently-selected event type / correlation scope — it uses the same `eventType` value the table is showing.

### Search behavior

- `TextInput` debounced at 300 ms via `useDebouncedValue` from `@mantine/hooks` (already installed).
- Plain substring match. No regex, no wildcards — that's explicitly deferred.
- When the debounced value is non-empty, the component switches its `useQuery` from `fetchScanEvents` (or `fetchScanEventsUnique`) to `searchScanEvents`. Different queryKey; cache separation keeps normal and search views independent.

---

## Testing

### Vitest — ~10 new cases

**`api/scaninfo.test.ts` extensions:**

1. `fetchScanEvents` maps the 11-tuple to typed `ScanEventRow[]` (positional index → named fields).
2. `fetchScanEvents` with `filterFp: true` passes `filterfp=true` on the URL.
3. `fetchScanEvents` with `correlationId` passes `correlationId=Y` on the URL.
4. `fetchScanEventsUnique` uses the `/scaneventresultsunique` path.
5. `fetchCorrelations` maps the 8-tuple to `CorrelationRow`.
6. `searchScanEvents` uses the `/search` path with URL-encoded value.
7. `toggleFalsePositive` posts `fp=1|0` + JSON-encoded resultIds to `/resultsetfp`.

**`pages/scaninfo/BrowseTab.test.tsx`:**

8. Initial render shows event-type summary table; clicking a type row transitions to event list view.
9. Clicking "Mark FP" on a row invokes `/resultsetfp` with the row's hash.
10. Changing the Full/Unique `SegmentedControl` swaps the data source (assert URL on subsequent fetch).

**`pages/scaninfo/CorrelationsTab.test.tsx`:**

11. Initial render shows correlations list with risk badges; empty response renders the empty-state Alert.
12. Clicking a correlation row transitions to the events view with the correlation's headline in the title.

### Playwright — 2 new cases in `06-scaninfo-browse.spec.ts`

1. **Browse drill-in**: from `/scaninfo?id=<finished-scan-guid>`, click Browse tab → event-type table renders → click the first type → events table renders with at least one row.
2. **Correlations tab**: from `/scaninfo?id=<finished-scan-guid>`, click Correlations tab → either the correlations list renders OR the empty-state Alert appears (seeded scan may have no correlations; assert the union).

Fixture DB: `seed_db.py` already seeds a FINISHED `monthly-recon` scan. M4a added `--reseed` for the inter-test state issue. No fixture changes needed in M4b.

### Sanity

- `./test/run` stays green.
- The integration test `test_scaninfo_returns_spa_shell` is unchanged.
- pytest counts unchanged — no new Python tests in M4b.

---

## Retirements

None. `/scaninfo-legacy`, `scaninfo.tmpl`, `viz.js`, shared chrome all live until the final sweep.

---

## Rollout

Single milestone, single PR-equivalent (pushed directly to master). Users hitting `/scaninfo?id=X` and clicking Browse or Correlations get the new UI without needing to click through to the legacy route; that path stays alive for Graph only.

---

## Risks

- **Large scan → large events list.** A scan with 50k events of the same type renders 50k Mantine Table rows. Mitigation: default the view to Unique (already implemented), cap `/scaneventresults` at a pragmatic limit (maybe 2000) with a "fetch more" button deferred to a post-retirement polish pass. Document the pagination cap in the spec's non-goals rather than fighting it in M4b.
  - Practical impact: low — the seeded fixture scan has a handful of events; real-world scans that saturate are rare in our OhDeere usage.
- **Correlation with zero events.** `fetchCorrelations` might list a correlation whose `eventsCount` is already 0 (rare but possible if FPs wiped it). Drill-in should show "No events for this correlation." gracefully via the existing empty-state Alert.
- **FP-toggle race:** user marks FP, mutation in flight, user clicks another row's toggle — both succeed sequentially thanks to TanStack Query's default mutation serialization per scope. No fanciness required.
- **`/search` case sensitivity:** The backend's `dbh.search` is case-insensitive for substring match (confirmed via `LOWER(...)` in the SQL). Document the behavior in the search textbox's placeholder ("Find events containing…").

---

## Non-goals for M4b

- Bubble / dendro / bar visualizations (Mako's `viz-bubble-*` / `viz-dendro` buttons).
- `/scanelementtypediscovery` drill-down (modules that produce/consume a type).
- Bulk multi-select + bulk FP flip + bulk export.
- Regex (`/pattern/`) and wildcard (`*text*`) search syntax — plain substring only.
- Cross-type `/search?eventType=ALL` (use the per-type drill-in).
- Pagination / virtualization of large event tables.
- URL-deep-linkable sub-tab state.
- Graph tab (→ M4c).

---

## Open items — none

All three brainstorming questions settled:
1. Scope: type-list → events drill-in on Browse, list → events drill-in on Correlations, with FP toggle, full/unique, search, export. Drop visualizations + producer/consumer + bulk-select.
2. Sub-tab state: local `useState`, not URL-deep-linkable. Revisit in final-sweep milestone.
3. Library for Graph tab (M4c): **@visx/network + d3-force** — consistent with nightscout-java's @visx/* stack (`BgChart.tsx`) and the ohdeere-react conventions. Not implemented here; noted for M4c.
