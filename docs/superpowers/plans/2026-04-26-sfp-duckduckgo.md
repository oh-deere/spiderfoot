# `sfp_duckduckgo` HTML-Scrape Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing `sfp_duckduckgo` (Instant Answer API, 2015) with an HTML-scrape implementation that produces the same event types as `sfp_searxng`, giving SpiderFoot a zero-config general-web search backend for users without SearXNG or the OhDeere stack.

**Architecture:** Single Python module that POSTs `q=site:<target>&s=<offset>` to `https://html.duckduckgo.com/html/`, parses the response with BeautifulSoup, unwraps `uddg` redirect links when present, and emits LINKED_URL_INTERNAL/EXTERNAL/INTERNET_NAME/EMAILADDR/RAW_RIR_DATA mirroring `sfp_searxng`. Anti-scrape safety: detect DDG's `anomaly-modal` CAPTCHA wrapper in the response body and bail with `errorState`.

**Tech Stack:** Python 3.7+, `beautifulsoup4` (already pinned), `urllib.parse`, `re`. Uses `self.sf.fetchUrl` for HTTP. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-26-sfp-duckduckgo-design.md`

---

## File map

| Action | File |
|---|---|
| Delete | `modules/sfp_duckduckgo.py` (Instant Answer API, 2015) |
| Delete | `test/unit/modules/test_sfp_duckduckgo.py` |
| Delete | `test/integration/modules/test_sfp_duckduckgo.py` |
| Create (same name) | `modules/sfp_duckduckgo.py` (HTML scraper) |
| Create | `test/unit/modules/test_sfp_duckduckgo.py` (~10 tests) |
| Modify | `CLAUDE.md` (update FREE_NOAUTH_UNLIMITED entry + search-modules note) |
| Modify | `docs/superpowers/BACKLOG.md` (mark items shipped) |

---

## Task 1: Delete the old module + its tests

**Files:**
- Delete: `modules/sfp_duckduckgo.py`
- Delete: `test/unit/modules/test_sfp_duckduckgo.py`
- Delete: `test/integration/modules/test_sfp_duckduckgo.py`

- [ ] **Step 1: Confirm no module currently watches the old DDG outputs**

Run: `grep -rln "DESCRIPTION_ABSTRACT\|DESCRIPTION_CATEGORY\|AFFILIATE_DESCRIPTION" modules/ | grep -v __pycache__`
Expected: only producer modules listed (e.g. `sfp_ohdeere_wiki`, `sfp_ohdeere_llm_summary`, `sfp_hostio`). No consumer = safe to drop these outputs from `sfp_duckduckgo`.

If a consumer is found, STOP and surface to the user before deleting. (None expected per the design audit.)

- [ ] **Step 2: Delete the three files**

Run:

```bash
git rm modules/sfp_duckduckgo.py
git rm test/unit/modules/test_sfp_duckduckgo.py
git rm test/integration/modules/test_sfp_duckduckgo.py
```

Expected: `rm 'modules/sfp_duckduckgo.py'` etc. for each.

- [ ] **Step 3: Verify the loader no longer sees `sfp_duckduckgo`**

Run:

```bash
python3 -c "
from spiderfoot import SpiderFootHelpers
mods = SpiderFootHelpers.loadModulesAsDict('modules', ['sfp__stor_db.py', 'sfp__stor_stdout.py'])
print('present?', 'sfp_duckduckgo' in mods)
"
```
Expected: `present? False`.

- [ ] **Step 4: Commit the deletion**

```bash
git commit -m "sfp_duckduckgo: drop Instant Answer API module + tests (replaced next)"
```

---

## Task 2: Failing unit tests for the new HTML-scrape module

This task only writes the test file; no source yet, so collection fails — that's the red state.

**Files:**
- Create: `test/unit/modules/test_sfp_duckduckgo.py`

- [ ] **Step 1: Write the failing test file**

Create `test/unit/modules/test_sfp_duckduckgo.py`:

```python
# test_sfp_duckduckgo.py
import json
import unittest
from unittest import mock

import pytest

from modules.sfp_duckduckgo import sfp_duckduckgo
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget


def _html_with_results(results):
    """``results`` is a list of (href, snippet) tuples."""
    blocks = []
    for href, snippet in results:
        blocks.append(
            f'<div class="result results_links results_links_deep web-result">'
            f'<a class="result__a" href="{href}">title</a>'
            f'<a class="result__snippet" href="x">{snippet}</a>'
            f'</div>'
        )
    return "<html><body>" + "".join(blocks) + "</body></html>"


def _fetch_ok(body: str) -> dict:
    return {"code": "200", "content": body, "headers": {}}


@pytest.mark.usefixtures("default_options")
class TestModuleDuckDuckGo(unittest.TestCase):

    def _module(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_duckduckgo()
        module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _domain_event(self, value="example.com"):
        root = SpiderFootEvent("ROOT", value, "", "")
        return SpiderFootEvent("INTERNET_NAME", value, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_duckduckgo()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_duckduckgo()
        self.assertEqual(set(module.watchedEvents()),
                         {"INTERNET_NAME", "DOMAIN_NAME"})
        self.assertEqual(set(module.producedEvents()), {
            "LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL",
            "INTERNET_NAME", "EMAILADDR", "RAW_RIR_DATA",
        })

    def test_subdomain_hit_emits_internal_url_and_internet_name(self):
        body = _html_with_results([
            ("https://sub.example.com/path", "snippet"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        types = sorted(e.eventType for e in emitted)
        self.assertIn("LINKED_URL_INTERNAL", types)
        self.assertIn("INTERNET_NAME", types)
        names = [e for e in emitted if e.eventType == "INTERNET_NAME"]
        self.assertEqual(names[0].data, "sub.example.com")

    def test_external_url_emits_external_only(self):
        body = _html_with_results([
            ("https://other.org/x", "snippet"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        types = [e.eventType for e in emitted]
        self.assertIn("LINKED_URL_EXTERNAL", types)
        self.assertNotIn("INTERNET_NAME", types)

    def test_self_echo_emits_internal_but_no_internet_name(self):
        body = _html_with_results([
            ("https://example.com/", "snippet"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        types = [e.eventType for e in emitted]
        self.assertIn("LINKED_URL_INTERNAL", types)
        # The input domain itself shouldn't be re-emitted as a subdomain.
        self.assertNotIn("INTERNET_NAME", types)

    def test_email_extracted_from_snippet(self):
        body = _html_with_results([
            ("https://example.com/contact", "Reach us at dev@example.com today"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        emails = [e.data for e in emitted if e.eventType == "EMAILADDR"]
        self.assertEqual(emails, ["dev@example.com"])

    def test_uddg_redirect_unwrapped(self):
        # Wrapped href format (DDG occasionally still returns these).
        body = (
            '<html><body><div class="result results_links results_links_deep web-result">'
            '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">title</a>'
            '<a class="result__snippet" href="x">snippet</a>'
            '</div></body></html>'
        )
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        urls = [e.data for e in emitted if e.eventType == "LINKED_URL_INTERNAL"]
        self.assertEqual(urls, ["https://example.com/a"])

    def test_max_pages_one_means_one_fetch(self):
        body = _html_with_results([("https://example.com/", "x")])
        _, module = self._module()
        module.opts["max_pages"] = 1
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)) as m_fetch:
            module.handleEvent(self._domain_event())
        self.assertEqual(m_fetch.call_count, 1)

    def test_anomaly_response_trips_errorstate(self):
        body = '<html><body><div class="anomaly-modal">CAPTCHA!</div></body></html>'
        _, module = self._module()
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._domain_event())
        self.assertTrue(module.errorState)
        self.assertEqual(emitted, [])
        m_error.assert_called()

    def test_http_500_trips_errorstate(self):
        _, module = self._module()
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value={"code": "500",
                                              "content": "", "headers": {}}), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._domain_event())
        self.assertTrue(module.errorState)
        self.assertEqual(emitted, [])
        m_error.assert_called()

    def test_raw_rir_data_emitted_with_parsed_results(self):
        body = _html_with_results([
            ("https://sub.example.com/a", "snippet1"),
            ("https://other.org/b", "snippet2"),
        ])
        _, module = self._module()
        module.opts["max_pages"] = 1
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        with mock.patch.object(module.sf, "fetchUrl",
                               return_value=_fetch_ok(body)):
            module.handleEvent(self._domain_event())
        raws = [e.data for e in emitted if e.eventType == "RAW_RIR_DATA"]
        self.assertEqual(len(raws), 1)
        parsed = json.loads(raws[0])
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["url"], "https://sub.example.com/a")
        self.assertEqual(parsed[0]["snippet"], "snippet1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails (collection error)**

Run: `python3 -m pytest test/unit/modules/test_sfp_duckduckgo.py -v`
Expected: ImportError on `modules.sfp_duckduckgo`. Collection fails. Red state.

- [ ] **Step 3: Commit the failing tests**

```bash
git add test/unit/modules/test_sfp_duckduckgo.py
git commit -m "test: add failing tests for sfp_duckduckgo HTML scraper"
```

---

## Task 3: Implement the new module

**Files:**
- Create: `modules/sfp_duckduckgo.py`

- [ ] **Step 1: Write the module**

Create `modules/sfp_duckduckgo.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_duckduckgo
# Purpose:      Scrape DuckDuckGo's HTML search interface for site:<target>
#               dorks. Replaces the 2015-vintage Instant Answer wrapper.
#               Emits LINKED_URL_INTERNAL/EXTERNAL, INTERNET_NAME (subdomains),
#               EMAILADDR (from snippets), and RAW_RIR_DATA mirroring
#               sfp_searxng.
# Introduced:   2026-04-26 (replacement; original module dates to 2015).
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import re
import urllib.parse

from bs4 import BeautifulSoup

from spiderfoot import SpiderFootEvent, SpiderFootPlugin


_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_PAGE_SIZE = 30  # DDG returns ~30 results per HTML page; offset (s=) steps in 30s.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
_ANOMALY_SENTINEL = "anomaly-modal"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


class sfp_duckduckgo(SpiderFootPlugin):

    meta = {
        "name": "DuckDuckGo",
        "summary": "Scrape DuckDuckGo HTML search results for site:<target> "
                   "dorks. Harvests URLs, subdomains, and emails. Zero-config — "
                   "works without a self-hosted search backend.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Search Engines"],
        "dataSource": {
            "website": "https://duckduckgo.com/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://duckduckgo.com/",
                           "https://html.duckduckgo.com/html/"],
            "description": "Public HTML search interface at "
                           "html.duckduckgo.com/html/. No API key required. "
                           "DDG occasionally rate-limits scrapers via a CAPTCHA "
                           "modal; the module detects this and stops for the "
                           "rest of the scan.",
        },
    }

    opts = {
        "max_pages": 2,
        "fetch_timeout": 30,
    }

    optdescs = {
        "max_pages": "Number of result pages to fetch per input event "
                     "(DDG returns ~30 results per page; default 2 ≈ 60 URLs).",
        "fetch_timeout": "HTTP timeout in seconds for each call to DuckDuckGo.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._handled_events: set = set()
        self._emitted_hostnames: set = set()
        self._emitted_emails: set = set()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["INTERNET_NAME", "DOMAIN_NAME"]

    def producedEvents(self):
        return [
            "LINKED_URL_INTERNAL",
            "LINKED_URL_EXTERNAL",
            "INTERNET_NAME",
            "EMAILADDR",
            "RAW_RIR_DATA",
        ]

    def handleEvent(self, event):
        if self.errorState:
            return
        if event.data in self._handled_events:
            return
        self._handled_events.add(event.data)

        query = f"site:{event.data}"
        for pageno in range(int(self.opts["max_pages"])):
            offset = pageno * _PAGE_SIZE
            post_body = urllib.parse.urlencode({"q": query, "s": str(offset)})
            response = self.sf.fetchUrl(
                _DDG_HTML_URL,
                postData=post_body,
                timeout=int(self.opts["fetch_timeout"]),
                useragent=_USER_AGENT,
            )
            if not response or response.get("code") != "200":
                code = response.get("code") if response else "no-response"
                self.error(
                    f"DuckDuckGo HTTP {code} for {event.data} page {pageno + 1}"
                )
                self.errorState = True
                return

            body = response.get("content") or ""
            if _ANOMALY_SENTINEL in body:
                self.error(
                    "DuckDuckGo returned an anomaly page (CAPTCHA / "
                    "rate-limit); bailing for the rest of the scan"
                )
                self.errorState = True
                return

            results = self._parse(body)
            self._emit_event(
                "RAW_RIR_DATA",
                json.dumps(results, ensure_ascii=False),
                event,
            )
            for entry in results:
                self._process_result(entry, event)

    def _parse(self, body: str) -> list:
        try:
            soup = BeautifulSoup(body, "html.parser")
        except Exception as exc:
            self.debug(f"BeautifulSoup parse failed: {exc}")
            return []

        out = []
        for block in soup.select("div.result.results_links"):
            a = block.select_one("a.result__a")
            if a is None:
                continue
            href = a.get("href") or ""
            if not href:
                continue
            url = self._unwrap_uddg(href)
            snippet_el = block.select_one("a.result__snippet")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            out.append({"url": url, "snippet": snippet})
        return out

    def _unwrap_uddg(self, href: str) -> str:
        if href.startswith("//duckduckgo.com/l/?") or \
                href.startswith("https://duckduckgo.com/l/?") or \
                href.startswith("http://duckduckgo.com/l/?"):
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            uddg = params.get("uddg")
            if uddg:
                return uddg[0]
        return href

    def _process_result(self, entry, source_event):
        url = entry.get("url")
        if not url:
            return

        try:
            hostname = self.sf.urlFQDN(url)
        except (TypeError, AttributeError) as exc:
            self.debug(f"urlFQDN failed on {url}: {exc}")
            return

        is_self_echo = (hostname == source_event.data)
        is_internal = False
        target = self.getTarget()
        if target is not None and hostname:
            is_internal = target.matches(hostname, includeChildren=True)

        if is_internal:
            self._emit_event("LINKED_URL_INTERNAL", url, source_event)
            if (not is_self_echo and hostname
                    and hostname not in self._emitted_hostnames):
                self._emitted_hostnames.add(hostname)
                self._emit_event("INTERNET_NAME", hostname, source_event)
        else:
            self._emit_event("LINKED_URL_EXTERNAL", url, source_event)

        snippet = entry.get("snippet") or ""
        for email in _EMAIL_RE.findall(snippet):
            if email in self._emitted_emails:
                continue
            self._emitted_emails.add(email)
            self._emit_event("EMAILADDR", email, source_event)

    def _emit_event(self, event_type: str, data: str, source_event):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_duckduckgo class
```

- [ ] **Step 2: Run all 10 tests; expect green**

Run: `python3 -m pytest test/unit/modules/test_sfp_duckduckgo.py -v`
Expected: 10 passed.

- [ ] **Step 3: Lint**

Run: `python3 -m flake8 modules/sfp_duckduckgo.py test/unit/modules/test_sfp_duckduckgo.py`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add modules/sfp_duckduckgo.py
git commit -m "sfp_duckduckgo: HTML-scrape implementation (replaces Instant Answer)"
```

---

## Task 4: Loader smoke + repo-wide lint + neighbor tests

**Files:** none — verification only.

- [ ] **Step 1: Loader smoke**

Run:

```bash
python3 -c "
from spiderfoot import SpiderFootHelpers
mods = SpiderFootHelpers.loadModulesAsDict('modules', ['sfp__stor_db.py', 'sfp__stor_stdout.py'])
m = mods['sfp_duckduckgo']
print('name:', m['name'])
print('cats:', m['cats'])
print('produces:', m['provides'])
print('consumes:', m['consumes'])
print('opts:', sorted(m['opts'].keys()))
"
```

Expected output:

```
name: DuckDuckGo
cats: ['Search Engines']
produces: ['LINKED_URL_INTERNAL', 'LINKED_URL_EXTERNAL', 'INTERNET_NAME', 'EMAILADDR', 'RAW_RIR_DATA']
consumes: ['INTERNET_NAME', 'DOMAIN_NAME']
opts: ['fetch_timeout', 'max_pages']
```

- [ ] **Step 2: Repo-wide lint**

Run: `python3 -m flake8 . --count`
Expected: `0`.

- [ ] **Step 3: Run touched + neighboring tests**

Run:

```bash
python3 -m pytest \
  test/unit/modules/test_sfp_duckduckgo.py \
  test/unit/modules/test_sfp_searxng.py \
  test/unit/modules/test_sfp_ohdeere_search.py \
  -q --no-cov
```

Expected: all green. Approximately 30 tests total (10 ddg + ~12 searxng + ~10 ohdeere_search).

- [ ] **Step 4: No commit** — verification only.

---

## Task 5: Docs — CLAUDE.md + BACKLOG.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/BACKLOG.md`

- [ ] **Step 1: Update CLAUDE.md (find + edit)**

In `CLAUDE.md` the FREE_NOAUTH_UNLIMITED list contains `- sfp_duckduckgo`. The list-only entry needs no change (the module name is still there). What needs updating is any prose that describes what the module does. Run:

```bash
grep -n -B 1 -A 1 "sfp_duckduckgo\|DuckDuckGo" CLAUDE.md
```

Expected: a single bullet in the FREE_NOAUTH_UNLIMITED list. If there's any *prose* describing the old Instant Answer behavior (there isn't in the current file, but check), replace it with the new HTML-scrape behavior.

If the prose section does mention DDG, add or replace with this short note in the OhDeere/Search section (or wherever search backends are discussed):

```
`sfp_duckduckgo` (rewritten 2026-04-26) is now an HTML scraper of
html.duckduckgo.com/html/, not the dead Instant Answer API. Same
event outputs as `sfp_searxng`; serves as a zero-config fallback
for users without their own SearXNG instance or the OhDeere stack.
```

If no DDG-prose section exists, no change needed beyond the existing list entry.

- [ ] **Step 2: Update BACKLOG.md**

Find the `### sfp_duckduckgo — zero-config search fallback` section in `docs/superpowers/BACKLOG.md`. Replace it with:

```
### sfp_duckduckgo HTML scraper — shipped 2026-04-26
- Replaced the 2015-vintage Instant Answer wrapper with an HTML scrape of `html.duckduckgo.com/html/`. Same event outputs as `sfp_searxng`. Zero-config — no API key, no self-hosted backend required.
- Anti-scrape detection bails on DDG's `anomaly-modal` CAPTCHA wrapper; sets `errorState` for the rest of the scan.
- Spec: `docs/superpowers/specs/2026-04-26-sfp-duckduckgo-design.md`.
- Plan: `docs/superpowers/plans/2026-04-26-sfp-duckduckgo.md`.
```

Find the priority-table row `| Low | sfp_duckduckgo |` (search for `\| Low \| .*duckduckgo`). Replace with:

```
| ~~Low~~ Done | ~~sfp_duckduckgo~~ — shipped 2026-04-26 |
```

Find the `## Search alternatives` block (it lists `sfp_searxng`, `sfp_ohdeere_search`, `sfp_duckduckgo`). Update the `sfp_duckduckgo` line to:

```
- `sfp_duckduckgo` — zero-config HTML scrape of html.duckduckgo.com/html/ (shipped 2026-04-26).
```

- [ ] **Step 3: Verify**

Run: `grep -A 1 "sfp_duckduckgo HTML scraper" docs/superpowers/BACKLOG.md | head -3`
Expected: shows the "shipped 2026-04-26" line.

Run: `grep "Done.*sfp_duckduckgo" docs/superpowers/BACKLOG.md`
Expected: the `~~Low~~ Done | ~~sfp_duckduckgo~~` row.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "docs: BACKLOG.md (+ CLAUDE.md if needed) — sfp_duckduckgo scraper shipped"
```

(If `git status` shows no `CLAUDE.md` change because no DDG-prose existed to update, the commit will only include `BACKLOG.md`. That's expected.)

---

## Task 6: Final verify

**Files:** none — verification only.

- [ ] **Step 1: Show the commit chain**

Run: `git log --oneline -8`
Expected: ~5 new commits — delete, failing tests, impl, (no Task 4 commit), docs.

- [ ] **Step 2: Run focused tests one more time**

Run: `python3 -m pytest test/unit/modules/test_sfp_duckduckgo.py test/unit/modules/test_sfp_searxng.py -q --no-cov`
Expected: all green.

- [ ] **Step 3: Done.** Report the commit list and any notes.

---

## Self-review

**Spec coverage:**

- "Architecture" → Task 3 step 1 implements the full module shape per the spec.
- "Endpoint mechanics" — POST, form-encoded `q` + `s`, hardcoded UA — Task 3 step 1, lines using `self.sf.fetchUrl(_DDG_HTML_URL, postData=..., useragent=_USER_AGENT)`.
- "Result extraction" — `div.result.results_links` selector, `a.result__a[href]` URL, `a.result__snippet` snippet — Task 3 step 1's `_parse` method.
- "Redirect unwrap" — Task 3 step 1's `_unwrap_uddg` method; Task 2 test #7 locks it in.
- "Anti-scrape detection" — Task 3 step 1's anomaly check; Task 2 test #9 locks it in.
- "Module options" — `max_pages=2`, `fetch_timeout=30` — Task 3 step 1 opts block; Task 2 test #1 verifies key parity.
- "Watched / produced events" — Task 3 step 1; Task 2 test #2 verifies exact set.
- "Error contract" — HTTP non-200, anomaly, parse failure, empty set — Tasks 2 + 3 cover (parse failure is debug-logged inside `_parse`; tests #9 and #10 cover the errorState paths).
- "Module metadata" — Task 3 step 1 `meta` block.
- "Testing (~10 unit tests)" — all 10 spec'd tests appear in Task 2 step 1.
- "Distribution" — Task 1 covers no-deps; nothing else to add.
- "CLAUDE.md / BACKLOG.md updates" — Task 5.

**Placeholder scan:** No "TBD"/"TODO"/"add validation". Every code block is complete; every shell command has expected output.

**Type consistency:**
- `_unwrap_uddg(href: str) -> str` defined in Task 3, called identically inside `_parse`.
- `_parse(body: str) -> list` defined in Task 3, called identically in `handleEvent`.
- `_process_result(entry, source_event)` — `entry` is always a dict with `url`/`snippet` keys (returned from `_parse`); the tests' `_html_with_results` helper builds HTML that produces exactly those.
- `_DDG_HTML_URL`, `_PAGE_SIZE`, `_USER_AGENT`, `_ANOMALY_SENTINEL`, `_EMAIL_RE` — all module-level constants, referenced consistently.
- Opt names `max_pages`, `fetch_timeout` — match between source (Task 3), tests (Task 2), spec, and CLAUDE.md (Task 5).
