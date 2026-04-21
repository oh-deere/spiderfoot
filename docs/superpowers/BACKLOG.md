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

Specs: `docs/superpowers/specs/2026-04-20-webui-spa-milestone-{1,2}-design.md`.

**Remaining Mako pages to migrate** (each its own spec + plan):
- `/scaninfo?id=<guid>` (`scaninfo.tmpl`, ~905 lines) — the big one. Tabs for events, correlations, graph, log. Likely needs sub-milestones by tab.
- `/opts` (`opts.tmpl`, ~199 lines) — settings / API keys / global config.
- `/error` — tiny error page; can ride with the next migration.
- Clone-scan UX: re-add a Clone action to the scan list menu, backed by a new JSON endpoint that returns the cloned scan's pre-fill payload. Targeted for the milestone that touches `/scaninfo` (natural entry point).

**Retirements triggered by each migration:**
- Delete the Mako template + its CherryPy handler.
- Remove the corresponding Robot Framework acceptance test if any (`test/acceptance/scan.robot`).
- Add the path to `_SPA_ROUTES` in `sfwebui.py`.
- Add Playwright coverage for the new page under `webui/tests/e2e/`.

**Smaller follow-ups (no spec needed yet):**
- Pin Node base image to a specific patch version (`node:22.X.Y-slim`) for Docker build reproducibility. Currently floats on `node:22-slim` — matches the pattern of `python:3.12-slim-bookworm` but both are worth tightening.
- URL-bound filter state on the scan-list page (`useSearchParams`) so deep-linked filters work.

---

## Infrastructure / platform

### Postgres storage migration
- **What:** replace SpiderFoot's SQLite at `$SPIDERFOOT_DATA/spiderfoot.db` with Postgres. OhDeere already runs CloudNativePG.
- **Blocker:** SpiderFoot's entire schema lives in `spiderfoot/db.py` as SQL strings; all queries are raw SQL. `SpiderFootSqliteLogHandler` is sqlite-specific. Scan concurrency model assumes per-scan SQLite file semantics.
- **Migration options:** adapter pattern with sqlite/postgres backends, or hard cut with migration tooling (Flyway fits here — already used elsewhere in OhDeere; run migrations in an init-container before `sf.py` starts).
- **Size:** large — own spec + plan + multi-step implementation cycle.
- **Unlocks:** concurrent scans, cross-scan JOINs for analytics, JSONB on `RAW_RIR_DATA` (typed queries on the raw dumps), proper backup/restore, integration with other OhDeere services.

### `pybreaker` circuit breaker for OhDeere integrations
- **What:** add `pybreaker.CircuitBreaker` to `spiderfoot/ohdeere_client.py`, per-scope keyed. A dead scope (e.g. llm:query gateway down) stops module attempts for a cooldown window instead of letting per-scan `errorState` reset every scan.
- **Blocker:** earns its keep once 2+ `sfp_ohdeere_*` modules share the helper. We're at 7 consumers now — ready to implement.
- **Size:** small — ~30 lines in `ohdeere_client`, ~5 tests. Plus the `pybreaker` dependency.
- **Value:** protects the OhDeere auth server and downstream services from repeated failed scan attempts during outages.

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
| Medium | `pybreaker` circuit breaker |
| Medium | Richer `sfp_ohdeere_notification` completion payload |
| Medium | UI lift remaining pages — newscan / scaninfo / opts / error |
| Low | `sfp_ohdeere_maps` /nearby extension |
| Low | `sfp_ohdeere_llm_entities` |
| Low | `sfp_holehe` |
| Low | `sfp_duckduckgo` |
| Low | Registry orphan-sweep |
| Large | Postgres storage migration |
| Parked | `sfp_ohdeere_celltower` (no event fit) |
