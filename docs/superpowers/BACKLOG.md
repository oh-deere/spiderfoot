# SpiderFoot fork — backlog

Consolidated list of deferred work as of **2026-04-20**. Each entry notes whether a spec already exists (parked, ready to implement), what blocks it, and its approximate size. Spec-free items need a brainstorm → spec → plan before implementation.

---

## Parked with spec ready

### Typed module metadata registry (Phase 1 item 2)
- **Spec:** `docs/superpowers/specs/2026-04-20-typed-module-metadata-design.md`
- **Blocker:** none; parked in favour of OhDeere module work.
- **Size:** medium — single new file (`spiderfoot/module_meta.py` ~150 lines), one validator hook in `SpiderFootHelpers.loadModulesAsDict`, ~12 unit tests. No module-source edits.
- **Value:** import-time validation of `meta` dicts. Catches flag/category typos at startup instead of at UI render. Codifies the audit's "no paid modules" policy as a code-enforced invariant (validator refuses `COMMERCIAL_ONLY` / `PRIVATE_ONLY`).
- **Status:** ready to pick up whenever focus returns to core-plumbing work.

---

## Ready for implementation (no spec yet)

### `sfp_duckduckgo` — zero-config search fallback
- **What:** HTML-scrape module against `html.duckduckgo.com/html/` for users who don't run SearXNG or the OhDeere stack. Same inputs/outputs as `sfp_searxng`.
- **Blocker:** none.
- **Size:** medium — one module, ~150 lines. Scrape-fragile (DDG may change markup). Would want a gentle fallback when DDG returns empty.
- **Value:** closes the last gap for deployments that don't control a search backend.

### Holehe account-existence module (`sfp_holehe`)
- **What:** wraps `github.com/megadose/holehe` (MIT, pip-installable, ~120 services, no API keys). Watches `EMAILADDR` events, probes against the built-in provider list, emits `ACCOUNT_EXTERNAL_OWNED` for confirmed matches. Uses password-reset/signup differential responses.
- **Blocker:** adds a new dependency (`holehe`) — should be flagged in `requirements.txt` and Docker build.
- **Size:** medium — one module (~180 lines), ~10 tests. Subprocess/library invocation pattern differs from HTTP modules.
- **Flag as `invasive`:** touches third-party auth endpoints.
- **Value:** fills the gap left by removing `sfp_haveibeenpwned` / `sfp_emailrep` / `sfp_dehashed` for "does this email have an active account anywhere" OSINT.

### `sfp_ohdeere_llm_adverse_media` (blocked on model upgrade)
- **What:** per-event adverse-media extractor. Watches `LEAKSITE_CONTENT`, `DARKNET_MENTION_CONTENT`, `RAW_RIR_DATA`. Buffers in the scan, in `finish()` sends each to the LLM with a prompt like "extract allegations, legal issues, sentiment, entities, label uncertainty." Emits structured `LLM_DERIVED_RISK_FLAG` (or reuses `VULNERABILITY_DISCLOSURE`).
- **Blocker:** `gemma3:4b` is too small for reliable allegation vs fact discrimination. Depends on the gateway running `qwen2.5:32b` (INT8) or similar.
- **Size:** medium — ~200 lines on the helper, ~10 tests. Shape matches `sfp_ohdeere_llm_translate`.
- **Value:** turns raw "found mentions" into "actual risk insight" — the highest-value LLM application after summarization.

### `sfp_ohdeere_llm_entities` — cross-scan entity normalization
- **What:** post-scan entity clustering. In `finish()`, reads all `COMPANY_NAME` / `HUMAN_NAME` events and sends to LLM: "which of these likely refer to the same entity?" Emits `LLM_DERIVED_ENTITY_CLUSTER`.
- **Blocker:** lower hit-rate value; wait to see if needed after adverse-media ships.
- **Size:** medium — ~180 lines, ~10 tests.
- **Value:** deduplicates "Acme Ltd" / "Acme Limited" / "ACME Group" in scan output. Mostly useful on scans with many entity-type events.

### Extend `sfp_ohdeere_maps` with `/nearby`, `/autocomplete`, `/lookup`
- **What:** new endpoints wrapped. `/nearby` (POI lookup from coordinates) is the valuable one: "what businesses are near this IP's geolocation?"
- **Blocker:** design decision — does POI output become `PHYSICAL_ADDRESS` or a new `NEARBY_POI` event type?
- **Size:** small — one module, ~80 new lines on top of existing `sfp_ohdeere_maps`.
- **Value:** high-value for geo-OSINT investigations.

### `sfp_ohdeere_celltower` (parked — no event fit)
- **What:** OpenCellID lookups. Takes MCC/MNC/LAC/CID tuples or lat/lon.
- **Blocker:** no existing SpiderFoot event type carries cell tower identifiers; no input events means no natural event-bus flow.
- **Size:** small if unblocked, but design question is: which event type would trigger this module?
- **Status:** parked until a specific use case emerges (e.g. correlation with leaked call-detail records).

### Notification module — richer scan-complete content
- **What:** extend `sfp_ohdeere_notification` to include event counts, duration, top-5 riskiest findings in the scan-complete Slack ping instead of just "Scan completed for X".
- **Blocker:** `finish()` doesn't receive scan-outcome context. Need to query SQLite (like `sfp_ohdeere_llm_summary` does) to get the stats.
- **Size:** small — adds ~30 lines.
- **Value:** replaces the current "dumb" completion ping with something actually informative.

### Registry-sweep spec — orphan event types
- **What:** prune event types in `spiderfoot/event_types.py` whose only producers were removed in the audit (e.g. `HASH_COMPROMISED`, `PHONE_NUMBER_COMPROMISED`). Also updates correlation rules that reference those types.
- **Blocker:** needs a spec — small scope but touches the typed event registry (Phase 1 item 1 invariants) and `correlations/*.yaml`.
- **Size:** small — remove entries from `EVENT_TYPES`, update invariant test counts, clean up correlation rules that reference orphans.
- **Value:** tightens the event registry. Currently these orphans are harmless (1-line entries, no runtime cost) but they mislead anyone reading the registry.

---

## UI modernization

### UI modernization — page-by-page migration

**Shipped:**
- Milestone 1 (2026-04-20) — `/` scan list + full toolchain (Vite + React + Mantine + Vitest + Playwright).
- Milestone 2 (2026-04-20) — `/newscan` scan creation form + three selection tabs + filterable module list. Retired `clonescan` handler (clone UI deferred).
- Milestone 3 (2026-04-20) — `/opts` settings page: left-rail navigation, filterable module list, dirty indicator, Import/Export/Reset flows. Extended `/optsraw` with per-option descriptions and per-module metadata; `/savesettings` gained JSON success/error branches.
- Milestone 4a (2026-04-20) — `/scaninfo` SPA shell + Status/Info/Log tabs. Browse/Correlations/Graph tabs render a placeholder linking to the temporarily-retained `/scaninfo-legacy` Mako handler. Zero new JSON endpoints — reuses `/scanstatus`, `/scansummary`, `/scanopts`, `/scanlog`, `/scanexportlogs`, `/stopscan`.
- Milestone 4b (2026-04-20) — `/scaninfo` Browse + Correlations tabs. Two-view drill-in (event-type list → events, correlations list → events) sharing an `EventList` component that hosts Full/Unique toggle, hide-FP switch, debounced value search, CSV+Excel export, and per-row FP-flip. Zero new JSON endpoints — reuses `/scaneventresults`, `/scaneventresultsunique`, `/search`, `/scancorrelations`, `/scaneventresultexport`, `/resultsetfp`.
- Milestone 4c (2026-04-20) — `/scaninfo` Graph tab. React renderer on `@visx/network` + `d3-force` with pan/zoom, PNG+GEXF export, and a >500-node fallback that points at the GEXF download for external graph tools. Retires `scaninfo_legacy` handler, `scaninfo.tmpl` (905 lines), `viz.js` (387 lines), and HEADER.tmpl's viz.js reference. `/scaninfo-legacy` now returns 404.
- Milestone 5 (2026-04-20) — final sweep. Retires HEADER.tmpl, FOOTER.tmpl, error.tmpl, spiderfoot.js, spiderfoot.css, dark.css, spiderfoot/static/node_modules/ (jquery, bootstrap3, d3, sigma, tablesorter, alertifyjs), spiderfoot/static/img/, and the legacy /static CherryPy mount. Converts self.error() + error_page_404() to inline HTML (no Mako). Adds Clone-scan UX: new GET /clonescan JSON endpoint, NewScanPage reads ?clone=<guid> and seeds form state, ScanListPage row menu gains a Clone action. Closes the UI retirement.

Specs: `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2,3,4a,4b,4c,5}-design.md`.

**UI modernization complete.** No Mako templates remain.

**Smaller follow-ups (no spec needed yet):**
- Pin Node base image to a specific patch version (`node:22.X.Y-slim`) for Docker build reproducibility. Currently floats on `node:22-slim` — matches the pattern of `python:3.12-slim-bookworm` but both are worth tightening.
- URL-bound filter state on the scan-list page (`useSearchParams`) so deep-linked filters work.
- **OptsPage save-refetch race:** between save completing and the refetch landing, concurrent user edits in `current` get clobbered by the re-seed `useEffect`. Low-likelihood but latent. Cheap fix: disable the form while `saveMutation.isPending`.
- **OptsPage test coverage gaps:** add Vitest cases for import flow, reset flow, error-alert rendering, and filter narrowing. Each is ~10-15 lines against the existing mockApi harness.

---

## Infrastructure / platform

**Shipped:**
- **pybreaker circuit breaker for OhDeere integrations (2026-04-20)** — per-scope `pybreaker.CircuitBreaker` wraps `OhDeereClient._request`. Trips after 5 consecutive `OhDeereServerError`s; 60s cooldown. Auth / 4xx pass through unchanged. Spec: `docs/superpowers/specs/2026-04-20-pybreaker-ohdeere-client-design.md`.

### Postgres storage migration
- **What:** replace SpiderFoot's SQLite at `$SPIDERFOOT_DATA/spiderfoot.db` with Postgres. OhDeere already runs CloudNativePG.
- **Blocker:** SpiderFoot's entire schema lives in `spiderfoot/db.py` as SQL strings; all queries are raw SQL. `SpiderFootSqliteLogHandler` is sqlite-specific. Scan concurrency model assumes per-scan SQLite file semantics.
- **Migration options:** adapter pattern with sqlite/postgres backends, or hard cut with migration tooling (Flyway fits here — already used elsewhere in OhDeere; run migrations in an init-container before `sf.py` starts).
- **Size:** large — own spec + plan + multi-step implementation cycle.
- **Unlocks:** concurrent scans, cross-scan JOINs for analytics, JSONB on `RAW_RIR_DATA` (typed queries on the raw dumps), proper backup/restore, integration with other OhDeere services.

### Live-scan OhDeere smoke / CLAUDE.md refresh
- **What:** operational task — run one real scan with `OHDEERE_CLIENT_ID` / `OHDEERE_CLIENT_SECRET` set against a benign target; verify every sfp_ohdeere_* module produces real events against the live services. Report cluster readiness.
- **Blocker:** requires operator cluster access.
- **Size:** manual, ~30 minutes.
- **Value:** sanity check before relying on the integration in production scans.

---

## Search alternatives
- `sfp_searxng` — self-hosted SearXNG (shipped 2026-04-20).
- `sfp_ohdeere_search` — auth-gated OhDeere wrapper around SearXNG (shipped 2026-04-20).
- `sfp_duckduckgo` — zero-config scrape fallback (see "Ready for implementation").

---

## Summary by urgency

| Urgency | Item |
|---|---|
| ~~High~~ Done | ~~Cull 4 redundant external IP modules~~ — shipped after live-scan parity confirmed |
| ~~High~~ Done | ~~Live-scan OhDeere smoke~~ — passed 2026-04-20 |
| Medium | Typed module metadata registry (spec ready) |
| Medium | `sfp_ohdeere_llm_adverse_media` (blocked on Qwen 32B) |
| ~~Medium~~ Done | ~~`pybreaker` circuit breaker~~ — shipped 2026-04-20 |
| Medium | Richer `sfp_ohdeere_notification` completion payload |
| Medium | UI lift remaining pages — newscan / scaninfo / opts / error |
| Low | `sfp_ohdeere_maps` /nearby extension |
| Low | `sfp_ohdeere_llm_entities` |
| Low | `sfp_holehe` |
| Low | `sfp_duckduckgo` |
| Low | Registry orphan-sweep |
| Large | Postgres storage migration |
| Parked | `sfp_ohdeere_celltower` (no event fit) |
