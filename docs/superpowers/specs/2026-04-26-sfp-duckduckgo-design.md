# `sfp_duckduckgo` — Replace Instant Answer module with HTML-scrape backend

**Status:** Design (2026-04-26)
**Backlog item:** "Find search module alternatives" / "DuckDuckGo zero-config search fallback" (BACKLOG.md).
**Author:** Claude (with Ola)

## Goal

Replace the existing `sfp_duckduckgo` (a 2015-vintage wrapper around DuckDuckGo's mostly-deprecated Instant Answer API that produces `DESCRIPTION_*` events) with an HTML-scrape implementation that produces the same event types as `sfp_searxng`. Closes the search-coverage gap for users without their own SearXNG instance or the OhDeere stack.

The module name (`sfp_duckduckgo`) and on-disk path stay identical so existing scan configs that have it enabled keep loading; the produced event set changes completely.

## Non-goals

- No image extraction. Discovering image URLs requires a new event type (currently SpiderFoot has none — `sfp_spider` actively filters image MIME types out) plus producer + consumer changes. Tracked as a separate spec for the future vision-pipeline workflow.
- No DDG image-search endpoint (different URL surface; deferred with images).
- No polite-scraper features (UA rotation, inter-page sleep, anomaly retry-with-backoff). YAGNI; backwards-compatible enhancement later.
- No migration of opts from the old module — `affiliatedomains` etc. drop silently. The old opts produced descriptions; the new module's opts (`max_pages`, `fetch_timeout`) describe scraping cadence. There's no semantically equivalent setting to migrate.
- No new dependencies. `beautifulsoup4` is already in `requirements.txt`.

## Architecture

Single module file replaced in place. Pure-Python HTML fetch + parse, no async. Mirrors `sfp_searxng`'s structure intentionally so a future user reading both modules can see they're parallel:

- `setup` — read opts, init dedup sets (`_handled_events`, `_emitted_hostnames`, `_emitted_emails`).
- `handleEvent` — for each new `INTERNET_NAME` / `DOMAIN_NAME`, fetch up to `max_pages` pages and parse.
- Per-page parse — extract result `<div class="result results_links results_links_deep web-result">` blocks via BeautifulSoup, unwrap `uddg` redirects, classify each URL as internal/external, harvest emails from snippets.
- Module-level constants for the endpoint URL, the User-Agent, the page-size offset, the anomaly-detection sentinel string, and the email regex.

## Endpoint mechanics

- **URL:** `https://html.duckduckgo.com/html/`
- **Method:** POST (DDG accepts GET too, but POST is what their `/html/` form uses; matches what real browsers send and is less likely to trip the anomaly heuristic).
- **Body:** form-encoded `q=site:<target>&s=<offset>` where `s` is the result offset. First page omits `s`; second page sends `s=30`; third `s=60`.
- **User-Agent:** hardcoded modern Chrome UA constant. SpiderFoot's default UA `SpiderFoot` gets routinely 200-with-anomaly'd by DDG.
- **Headers:** `Accept`, `Accept-Language`, `Content-Type` set explicitly. Mirrors a real form post.
- **Response:** HTML. No JSON option for `/html/`.

## Result extraction

Each web result in DDG's HTML output looks (abbreviated) like:

```html
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath&...">Title</a>
  </h2>
  <a class="result__url" href="https://example.com/path">example.com/path</a>
  <a class="result__snippet" href="...">Snippet text containing matched terms.</a>
</div>
```

Parsing:

1. `soup.select("div.result")` → list of result blocks (skip ads via the `result--ad` class — covered by selecting only blocks that *also* contain `web-result`).
2. Per block:
   - URL: take `a.result__a[href]`. If the href starts with `//duckduckgo.com/l/?` or `https://duckduckgo.com/l/?`, parse the `uddg` query parameter and percent-decode it. That's the real URL. Otherwise use the href as-is.
   - Snippet: `a.result__snippet`'s `.get_text()`.
3. URL classification — same as `sfp_searxng`:
   - Compute hostname via `self.sf.urlFQDN(url)`.
   - If `self.getTarget().matches(hostname, includeChildren=True)` → emit `LINKED_URL_INTERNAL`. Plus `INTERNET_NAME` for the hostname iff it's a *new* subdomain (not already emitted, not the input event's own domain).
   - Else → emit `LINKED_URL_EXTERNAL`.
4. Email extraction — apply the same email regex that `sfp_searxng` uses (defined as a module-level constant in this file too; tiny duplication, not worth a shared helper). Dedup via `_emitted_emails`.

`RAW_RIR_DATA` per page: a JSON dump of the parsed result list (each entry `{url, snippet}`). Same shape spirit as `sfp_searxng` — gives downstream consumers structured data without making them re-parse HTML.

## Anti-scrape detection

DDG's "you're scraping us" page returns HTTP 200 with the body containing `anomaly-modal` (the CSS class on its CAPTCHA modal). Detect by simple substring match. On hit:

```python
self.error("DuckDuckGo returned an anomaly page (rate-limited / CAPTCHA); bailing for the rest of the scan")
self.errorState = True
return
```

No retry, no backoff. If users hit this often we'll revisit (the option-B "polite scraper" path). Until then, simpler is better.

## Module options

```python
opts = {
    "max_pages": 2,         # ≈60 results per input domain
    "fetch_timeout": 30,    # per-page HTTP timeout in seconds
}

optdescs = {
    "max_pages": "Number of result pages to fetch per input event (DDG returns ~30 results per page; "
                 "default 2 ≈ 60 URLs).",
    "fetch_timeout": "HTTP timeout in seconds for each call to DuckDuckGo.",
}
```

No `enabled` opt. SpiderFoot's UI handles module enable/disable.

## Watched / produced events

- **Watches:** `INTERNET_NAME`, `DOMAIN_NAME` — same as `sfp_searxng`.
- **Produces:** `LINKED_URL_INTERNAL`, `LINKED_URL_EXTERNAL`, `INTERNET_NAME`, `EMAILADDR`, `RAW_RIR_DATA` — same as `sfp_searxng`.

The producedEvents set is a *complete* change from the old module (`DESCRIPTION_ABSTRACT`, `DESCRIPTION_CATEGORY`, `AFFILIATE_DESCRIPTION_*`). Audit confirmed no module in the tree currently *watches* `DESCRIPTION_*`, so dropping those outputs has no consumer impact.

## Error contract

| Failure | Behavior |
|---|---|
| HTTP non-200 | `self.error(...)` + `errorState = True` + bail for the scan |
| Body contains `anomaly-modal` (CAPTCHA) | Same — explicit error message naming the cause |
| BeautifulSoup parse error / unexpected DOM | debug-log per result, skip that result, keep parsing the rest of the page |
| Empty result set | No emissions, no errorState — DDG legitimately returns nothing for some queries |
| Module disabled (none — runs whenever selected) | n/a |

## Module metadata

```python
meta = {
    "name": "DuckDuckGo",
    "summary": "Scrape DuckDuckGo HTML search results for site:<target> dorks. Harvests URLs, "
               "subdomains, and emails. Zero-config — works without a self-hosted search backend.",
    "flags": [],
    "useCases": ["Footprint", "Investigate", "Passive"],
    "categories": ["Search Engines"],
    "dataSource": {
        "website": "https://duckduckgo.com/",
        "model": "FREE_NOAUTH_UNLIMITED",
        "references": ["https://duckduckgo.com/", "https://html.duckduckgo.com/html/"],
        "description": "Public HTML search interface at html.duckduckgo.com/html/. No API key. "
                       "DDG occasionally rate-limits scrapers via a CAPTCHA modal; the module "
                       "detects this and stops for the rest of the scan.",
    },
}
```

## Testing (~10 unit tests)

1. **opts/optdescs key parity** — set comparison.
2. **watchedEvents / producedEvents** — exact-list comparison.
3. **Happy path with subdomain hit** — fixture HTML containing one result on `sub.example.com`; emits `LINKED_URL_INTERNAL` + `INTERNET_NAME` (sub) + `RAW_RIR_DATA`.
4. **External URL** — fixture with `https://other.org/x`; emits `LINKED_URL_EXTERNAL` only (no `INTERNET_NAME`).
5. **Self-echo of the input domain** — result on `example.com` itself; emits `LINKED_URL_INTERNAL` but no duplicate `INTERNET_NAME`.
6. **Email harvested from snippet** — fixture with `contact: dev@example.com` in the snippet → `EMAILADDR` emitted once.
7. **`uddg` redirect unwrap** — fixture has `href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa"`; the emitted URL is `https://example.com/a`, not the wrapper.
8. **`max_pages=1` honored** — verify only one HTTP call.
9. **Anomaly response → errorState** — body containing `anomaly-modal` → `errorState=True`, no emissions, subsequent events short-circuit.
10. **HTTP 500 → errorState** — non-200 trips errorState.

The integration test (`test/integration/modules/test_sfp_duckduckgo.py`) currently exercises the live Instant Answer API. Delete it — the new module's integration story is "scrape the live HTML page", which is the kind of test that becomes flaky immediately. Skip and rely on unit fixtures + the module loader smoke test.

## Distribution

- No new Python deps. `beautifulsoup4` already pinned.
- No Dockerfile change.
- No new env vars.
- No new event types in `spiderfoot/db.py`.

## CLAUDE.md / BACKLOG.md updates

After landing:

- CLAUDE.md: update the "Search alternatives" / module inventory text to describe the new behavior. Update the FREE_NOAUTH_UNLIMITED list entry.
- BACKLOG.md: mark "DuckDuckGo zero-config search fallback" as shipped 2026-04-26. Mark "find search module alternatives" as resolved with a one-line summary noting that `sfp_duckduckgo` (replaced) is the third search backend.
