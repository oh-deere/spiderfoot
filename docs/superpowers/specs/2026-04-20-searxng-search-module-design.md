# SearXNG web-search module (`sfp_searxng`)

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Re-introduce general-purpose web-search capability to the SpiderFoot fork, lost in the 2026-04-20 dead-module audit when `sfp_bingsearch`, `sfp_bingsharedip`, `sfp_googlesearch`, and `sfp_pastebin` were removed. The replacement is a single module, `sfp_searxng`, that queries a user-operated SearXNG instance (deployed alongside SpiderFoot in the OhDeere k3s cluster) via its JSON API. SearXNG aggregates multiple upstream engines (DuckDuckGo, Brave, Qwant, Startpage, Mojeek, Bing read-only scrape, etc.), so a single module call transparently benefits from multi-engine coverage.

## Non-goals

- **Not** deploying SearXNG itself. That's a separate cluster-level task handled by the infrastructure side; this spec assumes SearXNG is reachable at a URL the module receives via config.
- **Not** building a pluggable-backend abstraction. A future `sfp_duckduckgo` or `sfp_bravesearch` (should Brave ever drop the credit-card gate) can reuse this module's URL/email extraction helpers, but sharing them is deferred to the second module's spec.
- **Not** replicating `sfp_pastebin` or `sfp_socialprofiles` behavior as separate wrapper modules. Users can issue `site:pastebin.com` or social-site dorks by configuring different SearXNG query templates in follow-up modules later.
- **Not** adding new event types. Everything emitted already exists in the Phase 1 item 1 typed registry.
- **Not** touching the typed event registry, correlation rules, or existing modules.

## Design

### Module shape

One new module: `modules/sfp_searxng.py`, inheriting `SpiderFootPlugin`, ~180 lines. Standard plugin structure:

- `meta` block with `name: "SearXNG"`, `flags: []` (no apikey), `useCases: ["Footprint", "Investigate", "Passive"]`, `categories: ["Search Engines"]`, `dataSource.model: "FREE_NOAUTH_UNLIMITED"`, `dataSource.website: "https://github.com/searxng/searxng"`.
- `opts`:
  - `searxng_url` (default `""`) — base URL of the user's SearXNG instance, e.g. `https://searxng.ohdeere.internal`. When empty, module is a silent no-op.
  - `max_pages` (default `1`) — number of pages of results to fetch per input event. SearXNG returns ~10–20 results per page depending on its own config. Exposed as a per-scan tunable via the standard SpiderFoot UI options pane.
  - `fetch_timeout` (default `30`) — HTTP timeout in seconds for each call to SearXNG.

### Watched and produced events

**Watched:** `INTERNET_NAME`, `DOMAIN_NAME`.

**Produced:**
- `LINKED_URL_INTERNAL` — URL whose hostname matches the target's TLD+1.
- `LINKED_URL_EXTERNAL` — URL whose hostname doesn't match.
- `INTERNET_NAME` — hostname component of any internal URL that hasn't been seen this scan (this is what delivers subdomain discovery — the primary reason OSINT tools include search modules).
- `EMAILADDR` — any RFC-shaped address found in the search result's text snippet.
- `RAW_RIR_DATA` — the raw SearXNG JSON response, one per fetched page.

### API call

Endpoint: `GET <searxng_url>/search?q=<query>&format=json&safesearch=0&pageno=<N>`
- No auth header. No API key. SearXNG is user-operated.
- `q` parameter: `site:<target>` — matches the dorking pattern of the removed Google/Bing modules.
- `pageno`: 1-indexed (per SearXNG convention), iterated up to `max_pages`.
- Response: JSON object with a `results` array. Each element has `url`, `title`, `content` (snippet), and engine-specific metadata.

### Per-event flow (pseudocode)

```
def handleEvent(event: SpiderFootEvent):
    if not self.opts["searxng_url"]:
        return                                           # silent no-op when unconfigured
    if event.data in self.results:
        return                                           # dedup: same target, same scan
    self.results[event.data] = True

    base_url = self.opts["searxng_url"].rstrip("/")
    for page in range(1, self.opts["max_pages"] + 1):
        url = f"{base_url}/search?q=site:{event.data}&format=json&safesearch=0&pageno={page}"
        response = self.sf.fetchUrl(url, timeout=self.opts["fetch_timeout"],
                                    useragent=self.opts.get("_useragent", ""))
        if not response or response["code"] != "200":
            self.error(f"SearXNG query failed ({response.get('code')}): {url}")
            return                                       # bail entire event on first failure

        try:
            payload = json.loads(response["content"])
        except json.JSONDecodeError as exc:
            self.error(f"SearXNG returned non-JSON: {exc}")
            return

        self._emit_results(payload, event)               # emits LINKED_URL_*, EMAILADDR, INTERNET_NAME
        self._emit_raw(payload, event)                   # emits RAW_RIR_DATA
```

### URL classification

- Parse `result["url"]` hostname via `urllib.parse.urlparse`.
- Extract TLD+1 via the existing `SpiderFoot` helper (`self.sf.urlFQDN` + a public-suffix lookup — same mechanism `sfp_googlesearch` used pre-removal).
- If hostname's TLD+1 matches the scan target's root domain → `LINKED_URL_INTERNAL`; otherwise → `LINKED_URL_EXTERNAL`.
- If `LINKED_URL_INTERNAL` hostname is not yet in the per-scan `self.results` seen-set, emit an additional `INTERNET_NAME` event (this is the subdomain-discovery path).

### Email extraction

- Regex `r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+"` applied to each result's `content` snippet.
- Each match becomes an `EMAILADDR` event, deduped per scan in `self.results`.

### Error handling summary

| Condition | Behaviour |
|---|---|
| `searxng_url` empty | Module silently no-ops. No error state. |
| HTTP non-200, connection error, timeout | Log `self.error(...)`, bail current event, continue with future events. |
| JSON parse failure | Log `self.error(...)`, bail current event. |
| Empty `results[]` | Emit only `RAW_RIR_DATA` for the page; continue to next page or finish. |
| Missing `url` key on a result | Skip with `self.debug(...)` and continue. |
| Result URL hostname unparseable | Skip with `self.debug(...)`. |

No `errorState` circuit-breaker is needed — since the user operates the SearXNG instance, quota/rate-limit issues don't apply. If the instance is briefly unreachable we retry on the next incoming event.

## Testing

Unit tests at `test/unit/modules/test_sfp_searxng.py`, mocking `SpiderFoot.fetchUrl`. Cases:

1. Empty `searxng_url` — no fetches, no emitted events.
2. Successful response with mixed internal/external URLs and an email in the snippet — asserts correct counts of each emitted event type.
3. Dedup — same input event twice emits the query only once; same URL appearing in two different queries emits only one `LINKED_URL_*` event.
4. `max_pages = 3` — asserts three fetch calls and three `RAW_RIR_DATA` emissions.
5. HTTP 500 — asserts `self.error(...)` logged, zero emissions for that event.
6. Malformed JSON — asserts `self.error(...)` logged, zero emissions.
7. Empty `results` array — asserts exactly one `RAW_RIR_DATA`, no URL/email events.
8. Subdomain discovery — response with a new hostname under the target TLD+1 produces one `INTERNET_NAME` event on top of the `LINKED_URL_INTERNAL`.
9. Email regex against a snippet containing two distinct addresses — asserts two `EMAILADDR` events.

**Integration test:** deliberately skipped for v1. Adding one later requires either a publicly reachable SearXNG instance or a test-only fixture. Deferred to a follow-up if needed.

**Full-suite verification post-merge:** `./test/run` must still pass at the post-cull baseline (1375 passing + 35 skipped) plus the ~9 new `test_sfp_searxng.py` tests.

## Rollout

Single commit. Module has no effect until a user sets `searxng_url` in the scan config or in the SpiderFoot web UI settings, so merging is safe even before the SearXNG instance is deployed.

Follow-up (not part of this spec): update `CLAUDE.md`'s "Module inventory" section to add `sfp_searxng` to the `FREE_NOAUTH_UNLIMITED` bucket and update the "Known gaps — Web search" note to record that the gap is now addressed.

## Non-spec items captured as backlog

- **`sfp_duckduckgo`** — zero-config fallback for users who don't run SearXNG. HTML-scrape against `html.duckduckgo.com/html/`. Use the URL/email-extraction helpers that `sfp_searxng` introduces.
- **Paste- and social-site wrapper modules** — small modules that issue `site:pastebin.com`, `site:github.com`, etc. dorks through the same SearXNG backend. Each emits more specific event types (e.g. `LEAKSITE_URL`) than the general search module.
- **Factor the URL/email-extraction logic** into a helper in `spiderfoot/` when the second search backend lands, to avoid duplication. Not worth doing with only one consumer.
