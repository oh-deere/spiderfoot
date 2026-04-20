# `sfp_ohdeere_wiki` + `sfp_ohdeere_search` (Batch 1)

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Ship two more consumers of `spiderfoot/ohdeere_client.py` in one cycle, following the established pattern (OhDeereClient → HTTP call → emit events, silent no-op when client disabled, errorState on failure).

- **`sfp_ohdeere_wiki`** — self-hosted Kiwix ZIM search. Entity enrichment: given a `COMPANY_NAME` or `HUMAN_NAME`, fetch a short Wikipedia-style description.
- **`sfp_ohdeere_search`** — the OhDeere `ohdeere-search-service` SearXNG wrapper. Same inputs/outputs as existing `sfp_searxng`, but OAuth2-gated via the client helper. For users who route search through their auth gateway.

Both modules are independent — no shared code beyond the already-shared `OhDeereClient` helper. Implemented in parallel.

## Non-goals

- **Not** deleting or refactoring `sfp_searxng`. The existing module stays for users who run raw SearXNG without OhDeere auth.
- **Not** building `sfp_ohdeere_celltower`. Parked to backlog — no SpiderFoot event type carries cell-tower identifiers, so the module has no natural event-bus flow.
- **Not** wrapping `/api/v1/suggest` or `/api/v1/books` on the wiki service. Typeahead and catalog-discovery aren't scan-useful.
- **Not** using wiki's raw article passthrough (`GET /**`). HTML parsing for a multi-KB article body is a different scope; the search snippet is enough for OSINT enrichment.
- **Not** supporting wrapper-specific features like `categories` / `time_range` / `language` on `sfp_ohdeere_search` v1. One hardcoded query form matching what `sfp_searxng` does: `q=site:<target>`. Optional filters can come in a follow-up.
- **Not** adding new event types.

## Design — `sfp_ohdeere_wiki`

### Endpoint

`GET /api/v1/search?q=<query>&limit=1` on the wiki service, scope `wiki:read`.

Response shape:
```json
{
  "results": [
    {"title": "Acme Corporation", "path": "...", "bookName": "wikipedia_en_all_maxi",
     "snippet": "Acme Corporation is a fictional company used as an archetype..."}
  ]
}
```

Empty `results` array is valid (query didn't match any article) — not an error.

### Module shape

- Watched events: `["COMPANY_NAME", "HUMAN_NAME"]`.
- Produced events: `["DESCRIPTION_ABSTRACT", "RAW_RIR_DATA"]`.
- Opts: `wiki_base_url` (default `https://wiki.ohdeere.internal`).
- Meta: `flags=[]`, `useCases=["Investigate", "Passive"]`, `categories=["Content Analysis"]`, `dataSource.model="FREE_NOAUTH_UNLIMITED"`.

### Event flow

```python
def handleEvent(event):
    if client.disabled: return
    if errorState: return
    if event.data in _seen: return
    _seen.add(event.data)
    params = urllib.parse.urlencode({"q": event.data, "limit": 1})
    payload = _call(f"/api/v1/search?{params}")        # wraps try/except
    if payload is None: return
    _emit(event, "RAW_RIR_DATA", json.dumps(payload))
    results = payload.get("results") or []
    if not results:
        self.debug(f"no wiki match for: {event.data}")
        return
    snippet = results[0].get("snippet")
    if snippet:
        _emit(event, "DESCRIPTION_ABSTRACT", snippet)
```

### Error handling

Same contract as other OhDeere modules: `_call()` helper catches `OhDeereAuthError` / `OhDeereServerError` / `OhDeereClientError`, logs `self.error(...)`, sets `self.errorState = True`, returns `None`.

## Design — `sfp_ohdeere_search`

### Endpoint

`GET /api/v1/search?q=<query>` on the search service, scope `search:read`.

Response shape:
```json
{
  "query": "site:example.com",
  "results": [
    {"title": "Example", "url": "https://api.example.com/foo",
     "content": "snippet...", "engine": "duckduckgo"}
  ],
  "answers": [], "suggestions": [], "infoboxes": [],
  "number_of_results": 42
}
```

### Module shape

- Watched events: `["INTERNET_NAME", "DOMAIN_NAME"]`.
- Produced events: `["LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL", "INTERNET_NAME", "EMAILADDR", "RAW_RIR_DATA"]`.
- Opts: `search_base_url` (default `https://search.ohdeere.internal`).
- Meta: `flags=[]`, `useCases=["Footprint", "Investigate", "Passive"]`, `categories=["Search Engines"]`, `dataSource.model="FREE_NOAUTH_UNLIMITED"`.

### Event flow

Identical to `sfp_searxng`, just a different endpoint + auth. Dork: `site:<target>` to stay consistent with the existing search module's behaviour.

```python
def handleEvent(event):
    if client.disabled: return
    if errorState: return
    if event.data in _seen: return
    _seen.add(event.data)
    params = urllib.parse.urlencode({"q": f"site:{event.data}"})
    payload = _call(f"/api/v1/search?{params}")
    if payload is None: return
    _emit(event, "RAW_RIR_DATA", json.dumps(payload))
    results = payload.get("results") or []
    for result in results:
        url = result.get("url")
        if not url: continue
        # TLD+1 match via self.getTarget().matches(hostname, includeChildren=True)
        # Same internal/external + subdomain discovery + email regex as sfp_searxng.
        ...
```

The URL-classification logic (internal vs external via `target.matches`), subdomain discovery (emit `INTERNET_NAME` for new hostnames under target TLD), and email-snippet regex extraction are **verbatim copies** of the `sfp_searxng` implementation. Zero design delta from the existing module — only the endpoint and auth change.

### Why not refactor `sfp_searxng` to share this logic?

The shared-helper refactor would touch two modules, add indirection, and save ~80 lines. For a solo-maintainer fork, the cost of the abstraction outweighs the deduplication benefit. Keep both modules self-contained; if a third search-type module ever shows up, that's when the common extractor moves to `spiderfoot/search_extract.py`.

## Testing

### `test/unit/modules/test_sfp_ohdeere_wiki.py` (~130 lines)

7 tests:

1. `opts`/`optdescs` key parity.
2. `watchedEvents` = `["COMPANY_NAME", "HUMAN_NAME"]`; `producedEvents` includes `DESCRIPTION_ABSTRACT` and `RAW_RIR_DATA`.
3. Silent no-op when client disabled.
4. Happy path — response with a single result → emits `DESCRIPTION_ABSTRACT` + `RAW_RIR_DATA`.
5. Empty results array → emits only `RAW_RIR_DATA`, logs `self.debug(...)`.
6. Result without snippet → emits only `RAW_RIR_DATA`.
7. `OhDeereAuthError` → `errorState`, no emissions, `self.error(...)`.

### `test/unit/modules/test_sfp_ohdeere_search.py` (~180 lines)

10 tests (same shape as `test_sfp_searxng.py` but with OhDeereClient stub instead of `fetchUrl` mock):

1. `opts`/`optdescs` key parity.
2. `watchedEvents` / `producedEvents` shape.
3. Silent no-op when client disabled.
4. Happy path — mixed internal/external URLs + email in snippet → correct counts.
5. Dedup — same input twice → one client call.
6. Empty results → only `RAW_RIR_DATA`.
7. `OhDeereAuthError` → `errorState`.
8. `OhDeereServerError` → `errorState`.
9. `errorState` short-circuits next event.
10. Subdomain discovery — internal URL with new hostname emits both `LINKED_URL_INTERNAL` AND `INTERNET_NAME`.

### Full-suite verification

Baseline 1424 + 35. After the batch: **1441 passed + 35 skipped** (+7 wiki + +10 search).

Flake8 clean on both modules.

## Rollout

Two commits per module (failing tests, then implementation). Total 4 commits from this spec. Modules don't touch each other's files; implementation can dispatch in parallel.

Follow-up (deferred, not in this spec):
- `CLAUDE.md` Module Inventory add both modules to `FREE_NOAUTH_UNLIMITED`.
- Live smoke scan with credentials set.
- `sfp_ohdeere_celltower` stays parked.

## Follow-ups enabled

- With `sfp_ohdeere_wiki` shipped, the scan chain `COMPANY_NAME` → `DESCRIPTION_ABSTRACT` adds immediate human-readable context to target companies.
- With `sfp_ohdeere_search`, users on the OhDeere stack have an auth-gated search path; `sfp_searxng` remains the fallback for non-gated deployments.
- Both modules reuse the OhDeereClient helper unchanged. Fifth and sixth total consumers (after searxng, geoip, maps). Pattern maturity is now clear; future modules can go straight to compressed spec.
