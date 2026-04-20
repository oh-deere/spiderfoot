# SearXNG Web-Search Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `modules/sfp_searxng.py`, a SpiderFoot plugin that queries a self-hosted SearXNG instance for `site:<target>` dorks and emits URL, subdomain, email, and raw-response events — replacing the web-search capability lost in the 2026-04-20 dead-module audit.

**Architecture:** One new module file + one new unit test file. No other source changes. Follows the same `SpiderFootPlugin` pattern as the other 185 surviving modules (e.g. `sfp_virustotal`): class-level `meta`/`opts`/`optdescs`, `setup`/`watchedEvents`/`producedEvents`/`handleEvent` methods, per-scan dedup via `self.results`, structured soft errors via `self.error(...)`, typed event emissions via the Phase 1 typed registry.

**Tech Stack:** Python 3.12+ stdlib (`json`, `re`, `urllib.parse`), existing `SpiderFoot` helpers (`fetchUrl`, `urlFQDN`), `SpiderFootEvent` typed dataclass. Tests use `unittest.TestCase` + `unittest.mock.patch`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-20-searxng-search-module-design.md`.

---

## File Structure

- **Create** `modules/sfp_searxng.py` — ~180 lines. The whole module: meta, opts, setup, watched/produced events, handleEvent, plus private helpers for URL classification, email extraction, and subdomain emission.
- **Create** `test/unit/modules/test_sfp_searxng.py` — ~170 lines. Nine unit tests covering silent-no-op, happy path, dedup, pagination, HTTP errors, malformed JSON, empty results, subdomain discovery, and email extraction.
- **Modify** `CLAUDE.md` — add `sfp_searxng` to the `FREE_NOAUTH_UNLIMITED` bucket; update the "Known gaps — Web search" note to record that the gap is addressed.

---

## Context for the implementer

- **No new event types.** All emitted types (`LINKED_URL_INTERNAL`, `LINKED_URL_EXTERNAL`, `INTERNET_NAME`, `EMAILADDR`, `RAW_RIR_DATA`) exist in `spiderfoot/event_types.py`.
- **Module discovery is automatic.** SpiderFoot loads every `modules/sfp_*.py` at startup. No registration anywhere.
- **Reference module for patterns**: `modules/sfp_virustotal.py` is a known-good example of an apikey-style module; `sfp_searxng` follows the same layout minus the apikey flag.
- **Reference test pattern**: `test/unit/modules/test_sfp_virustotal.py` shows how existing module tests use `self.default_options` (provided by `test/conftest.py`), `SpiderFootTarget`, and mocked `SpiderFoot.fetchUrl`.
- **SpiderFoot helpers available on `self.sf`** (from `sflib.py`):
  - `self.sf.fetchUrl(url, timeout=..., useragent=..., headers=...)` — returns `{"code": "200", "content": "...", "headers": {...}}` on success or with non-200 code on failure.
  - `self.sf.urlFQDN(url)` — returns the fully-qualified hostname from a URL.
- **`self.getTarget()`** — returns the current `SpiderFootTarget`; `target.matches(hostname, includeChildren=True)` is the method for "is this hostname within the scan's root domain."
- **Logger convention**: `self.error(msg)`, `self.info(msg)`, `self.debug(msg)` are inherited from `SpiderFootPlugin`. They attach `scanId` automatically; do not create module-local loggers.
- **Current test baseline**: `./test/run` reports `1375 passed, 35 skipped`. After Task 2 the count rises by 9 (the new tests in `test_sfp_searxng.py`) → `1384 passed, 35 skipped`.
- **SearXNG endpoint contract** (for the mock responses in tests):
  - URL: `<base_url>/search?q=<q>&format=json&safesearch=0&pageno=<N>`
  - Response shape (minimum relevant fields):
    ```json
    {
      "results": [
        {"url": "https://www.example.com/foo", "title": "...", "content": "Contact foo@example.com"},
        ...
      ]
    }
    ```
  - When SearXNG has no results, `results` is an empty list.

---

## Task 1: Write the failing test file (TDD red phase)

**Files:**
- Create: `test/unit/modules/test_sfp_searxng.py`

- [ ] **Step 1: Create the test file with all nine test cases**

Write this content to `test/unit/modules/test_sfp_searxng.py`:

```python
# test_sfp_searxng.py
import json
from unittest import mock

import pytest
import unittest

from modules.sfp_searxng import sfp_searxng
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget


def _fetch_ok(body: dict) -> dict:
    return {"code": "200", "content": json.dumps(body), "headers": {}}


def _fetch_status(code: str, body: str = "") -> dict:
    return {"code": code, "content": body, "headers": {}}


@pytest.mark.usefixtures("default_options")
class TestModuleSearxng(unittest.TestCase):

    def _module(self, url: str = "https://searxng.example.test"):
        sf = SpiderFoot(self.default_options)
        module = sfp_searxng()
        module.setup(sf, {"searxng_url": url})
        target = SpiderFootTarget("example.com", "INTERNET_NAME")
        module.setTarget(target)
        return sf, module, target

    def _root_event(self):
        return SpiderFootEvent("ROOT", "example.com", "", "")

    def _domain_event(self, parent):
        return SpiderFootEvent("INTERNET_NAME", "example.com", "test_mod", parent)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_searxng()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events_are_lists(self):
        module = sfp_searxng()
        self.assertIsInstance(module.watchedEvents(), list)
        self.assertIsInstance(module.producedEvents(), list)
        self.assertIn("INTERNET_NAME", module.watchedEvents())
        self.assertIn("DOMAIN_NAME", module.watchedEvents())
        for t in ("LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL",
                  "INTERNET_NAME", "EMAILADDR", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_empty_searxng_url_silently_no_ops(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_searxng()
        module.setup(sf, {"searxng_url": ""})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        evt = self._domain_event(self._root_event())

        with mock.patch.object(sf, "fetchUrl") as m_fetch, \
             mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(evt)

        m_fetch.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_internal_external_email_subdomain_raw(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        body = {
            "results": [
                {"url": "https://api.example.com/health", "title": "",
                 "content": "operator contact admin@example.com"},
                {"url": "https://other.org/mentions-example", "title": "",
                 "content": "example.com was mentioned"},
            ]
        }
        emissions = []
        with mock.patch.object(sf, "fetchUrl", return_value=_fetch_ok(body)), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)

        types_emitted = [e.eventType for e in emissions]
        self.assertEqual(types_emitted.count("LINKED_URL_INTERNAL"), 1)
        self.assertEqual(types_emitted.count("LINKED_URL_EXTERNAL"), 1)
        self.assertEqual(types_emitted.count("INTERNET_NAME"), 1)  # api.example.com
        self.assertEqual(types_emitted.count("EMAILADDR"), 1)
        self.assertEqual(types_emitted.count("RAW_RIR_DATA"), 1)

    def test_dedup_same_event_queried_only_once(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_ok({"results": []})) as m_fetch, \
             mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)  # same data → should dedup
        self.assertEqual(m_fetch.call_count, 1)

    def test_max_pages_triggers_multiple_fetches(self):
        sf = SpiderFoot(self.default_options)
        module = sfp_searxng()
        module.setup(sf, {"searxng_url": "https://searxng.example.test",
                          "max_pages": 3})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_ok({"results": []})) as m_fetch, \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)
        self.assertEqual(m_fetch.call_count, 3)
        # three RAW_RIR_DATA events (one per page) even with empty results
        self.assertEqual(sum(1 for e in emissions
                             if e.eventType == "RAW_RIR_DATA"), 3)

    def test_http_500_logs_error_and_emits_nothing(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_status("500")), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(evt)
        self.assertEqual(emissions, [])
        m_error.assert_called()

    def test_malformed_json_logs_error_and_emits_nothing(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value={"code": "200",
                                             "content": "not-json",
                                             "headers": {}}), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(evt)
        self.assertEqual(emissions, [])
        m_error.assert_called()

    def test_empty_results_emits_only_raw_rir_data(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        emissions = []
        with mock.patch.object(sf, "fetchUrl",
                               return_value=_fetch_ok({"results": []})), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)
        types_emitted = [e.eventType for e in emissions]
        self.assertEqual(types_emitted, ["RAW_RIR_DATA"])

    def test_email_regex_extracts_multiple_addresses_from_snippet(self):
        sf, module, _ = self._module()
        evt = self._domain_event(self._root_event())
        body = {
            "results": [
                {"url": "https://example.com/contact",
                 "title": "",
                 "content": "Reach foo@example.com or bar+baz@other.org today."},
            ]
        }
        emissions = []
        with mock.patch.object(sf, "fetchUrl", return_value=_fetch_ok(body)), \
             mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(evt)
        emails = sorted(e.data for e in emissions if e.eventType == "EMAILADDR")
        self.assertEqual(emails, ["bar+baz@other.org", "foo@example.com"])
```

- [ ] **Step 2: Run the tests and confirm they all fail with `ImportError`**

Run: `python3 -m pytest test/unit/modules/test_sfp_searxng.py -v`

Expected output contains:
```
ERROR test/unit/modules/test_sfp_searxng.py - ModuleNotFoundError: No module named 'modules.sfp_searxng'
```

The failure must be at collection time (the import fails), not at any test's runtime. If you see anything else — e.g. a test body failing mid-run — the module file partially exists or there's a typo; stop and investigate before continuing.

- [ ] **Step 3: Flake8**

Run: `python3 -m flake8 test/unit/modules/test_sfp_searxng.py`

Expected: no output. Fix any warning inline before committing.

- [ ] **Step 4: Commit**

```bash
git add test/unit/modules/test_sfp_searxng.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_searxng module

Drives Task 2: implement modules/sfp_searxng.py. Nine unit tests
cover: silent no-op on empty searxng_url, happy-path emission of
all five produced event types, dedup of repeated input events,
max_pages pagination, HTTP 500 error handling, malformed-JSON
error handling, empty results, subdomain discovery, and email
extraction from result snippets.

Refs docs/superpowers/specs/2026-04-20-searxng-search-module-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement `modules/sfp_searxng.py` to make the tests pass

**Files:**
- Create: `modules/sfp_searxng.py`

- [ ] **Step 1: Write the module**

Create `modules/sfp_searxng.py` with this exact content:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_searxng
# Purpose:      Query a user-operated SearXNG instance for site:<target>
#               dorks, emitting URL/subdomain/email/raw-response events.
#
# Introduced:   2026-04-20 — replaces sfp_bingsearch, sfp_bingsharedip,
#               sfp_googlesearch, and sfp_pastebin (all removed in the
#               dead-module audit).
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import re
import urllib.parse

from spiderfoot import SpiderFootEvent, SpiderFootPlugin

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")


class sfp_searxng(SpiderFootPlugin):

    meta = {
        "name": "SearXNG",
        "summary": "Query a self-hosted SearXNG instance for site:<target> dorks and harvest URLs, "
                   "subdomains, and emails from the aggregated result set.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Search Engines"],
        "dataSource": {
            "website": "https://github.com/searxng/searxng",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": [
                "https://docs.searxng.org/dev/search_api.html",
            ],
            "description": "SearXNG is a privacy-respecting metasearch engine that aggregates results "
                           "from DuckDuckGo, Brave, Qwant, Startpage, Mojeek, and others. This module "
                           "queries a user-operated SearXNG instance via its JSON API, so results depend "
                           "on the instance's configured backends.",
        },
    }

    opts = {
        "searxng_url": "",
        "max_pages": 1,
        "fetch_timeout": 30,
    }

    optdescs = {
        "searxng_url": "Base URL of your SearXNG instance (e.g. https://searxng.ohdeere.internal). "
                       "Leave empty to disable this module.",
        "max_pages": "Number of result pages to fetch per input event (SearXNG returns ~10-20 results per page).",
        "fetch_timeout": "HTTP timeout in seconds for each call to SearXNG.",
    }

    results = None
    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.results = self.tempStorage()
        self.errorState = False
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]
        # Normalise trailing slash on the URL so we can join safely.
        if self.opts.get("searxng_url"):
            self.opts["searxng_url"] = self.opts["searxng_url"].rstrip("/")

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
        if not self.opts.get("searxng_url"):
            return
        if self.errorState:
            return
        if event.data in self.results:
            return
        self.results[event.data] = True

        base = self.opts["searxng_url"]
        query = f"site:{event.data}"

        for pageno in range(1, int(self.opts["max_pages"]) + 1):
            params = urllib.parse.urlencode({
                "q": query,
                "format": "json",
                "safesearch": 0,
                "pageno": pageno,
            })
            url = f"{base}/search?{params}"
            response = self.sf.fetchUrl(
                url,
                timeout=int(self.opts["fetch_timeout"]),
                useragent=self.opts.get("_useragent", "SpiderFoot"),
            )
            if not response or response.get("code") != "200":
                code = response.get("code") if response else "no-response"
                self.error(f"SearXNG query failed (HTTP {code}) for {event.data} page {pageno}")
                return

            try:
                payload = json.loads(response.get("content") or "{}")
            except json.JSONDecodeError as exc:
                self.error(f"SearXNG returned non-JSON for {event.data} page {pageno}: {exc}")
                return

            self._emit_page(payload, event)

    def _emit_page(self, payload, source_event):
        self._emit_event("RAW_RIR_DATA", json.dumps(payload), source_event)
        for result in payload.get("results") or []:
            self._process_result(result, source_event)

    def _process_result(self, result, source_event):
        url = (result or {}).get("url")
        if not url:
            self.debug("SearXNG result missing url field; skipping")
            return

        try:
            hostname = self.sf.urlFQDN(url)
        except Exception as exc:
            self.debug(f"urlFQDN failed on {url}: {exc}")
            return

        is_internal = False
        target = self.getTarget()
        if target is not None and hostname:
            is_internal = target.matches(hostname, includeChildren=True)

        if is_internal:
            self._emit_event("LINKED_URL_INTERNAL", url, source_event)
            if hostname and hostname not in self.results:
                self.results[hostname] = True
                self._emit_event("INTERNET_NAME", hostname, source_event)
        else:
            self._emit_event("LINKED_URL_EXTERNAL", url, source_event)

        snippet = (result or {}).get("content") or ""
        for email in _EMAIL_RE.findall(snippet):
            if email in self.results:
                continue
            self.results[email] = True
            self._emit_event("EMAILADDR", email, source_event)

    def _emit_event(self, event_type, data, source_event):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_searxng class
```

- [ ] **Step 2: Run the new tests and confirm they all pass**

Run: `python3 -m pytest test/unit/modules/test_sfp_searxng.py -v`

Expected: **9 passed**. If any test fails:
- `test_watched_and_produced_events_are_lists` — check that `watchedEvents` and `producedEvents` return the exact lists shown.
- `test_empty_searxng_url_silently_no_ops` — check the `if not self.opts.get("searxng_url"): return` guard is the first line of `handleEvent`.
- `test_happy_path_emits_internal_external_email_subdomain_raw` — check `target.matches(hostname, includeChildren=True)` is called correctly; the test target is `example.com`, so `api.example.com` must classify as internal and `other.org` as external.
- `test_max_pages_triggers_multiple_fetches` — verify the `for pageno in range(1, max_pages + 1)` loop and that each iteration emits its own `RAW_RIR_DATA`.
- `test_http_500_logs_error_and_emits_nothing` / `test_malformed_json_logs_error_and_emits_nothing` — the error paths must return *before* any `notifyListeners` call.

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `./test/run`

Expected: `1384 passed, 35 skipped` (baseline was 1375; +9 from new tests). Flake8 clean. Any other test failing indicates an accidental collision with a shared helper — stop and investigate.

- [ ] **Step 4: Flake8 the new module**

Run: `python3 -m flake8 modules/sfp_searxng.py`

Expected: no output. If `E501` (line too long) fires on a specific line, wrap the long string literal; the repo enforces `max-line-length = 120`.

- [ ] **Step 5: Commit**

```bash
git add modules/sfp_searxng.py
git commit -m "$(cat <<'EOF'
modules: add sfp_searxng web-search module

Queries a user-operated SearXNG instance for site:<target> dorks.
Silent no-op when the searxng_url option is empty, so merging is
safe regardless of whether the SearXNG cluster deployment has
landed. When configured, the module watches INTERNET_NAME and
DOMAIN_NAME events and emits LINKED_URL_INTERNAL, LINKED_URL_
EXTERNAL, INTERNET_NAME (newly-discovered subdomains), EMAILADDR
(extracted from result snippets), and RAW_RIR_DATA (the full
SearXNG JSON response, one per page).

Classified FREE_NOAUTH_UNLIMITED in the module inventory — the
user controls the SearXNG instance and therefore its quota. Fills
the search gap left by the 2026-04-20 dead-module audit removal of
sfp_bingsearch, sfp_bingsharedip, sfp_googlesearch, and sfp_pastebin.

Refs docs/superpowers/specs/2026-04-20-searxng-search-module-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update `CLAUDE.md` module inventory

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Locate the FREE_NOAUTH_UNLIMITED bucket heading**

Run: `grep -n "### FREE_NOAUTH_UNLIMITED" CLAUDE.md`

You should get one match. The bucket list is alphabetical; locate the right insertion point for `sfp_searxng` (between `sfp_scylla` or similar and the next S-module, or wherever alphabetical ordering places it).

- [ ] **Step 2: Add `sfp_searxng` to the bucket**

Use the `Edit` tool on `CLAUDE.md` to insert `- sfp_searxng` in alphabetical order within the `### FREE_NOAUTH_UNLIMITED (N)` bulleted list. Also update the bucket's count `(N)` to `(N + 1)`.

- [ ] **Step 3: Update the "Web search" known-gap note**

Find the **Known gaps (backlog)** section in `CLAUDE.md`. Replace the "Web search" bullet with:

```markdown
- **Web search:** Addressed by `sfp_searxng` (2026-04-20) — queries a self-hosted SearXNG instance. Zero-config fallback (`sfp_duckduckgo`) remains on the backlog for users without a SearXNG deployment.
```

- [ ] **Step 4: Verify `CLAUDE.md` structure**

Run:
```bash
python3 -c "
text = open('CLAUDE.md').read()
assert '- sfp_searxng' in text, 'sfp_searxng missing from inventory'
assert 'Addressed by \`sfp_searxng\`' in text, 'Known-gap update missing'
print('CLAUDE.md structure OK')
"
```

Expected: `CLAUDE.md structure OK`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: record sfp_searxng in module inventory and close search gap

Adds sfp_searxng to the FREE_NOAUTH_UNLIMITED bucket of the Module
Inventory section and marks the "Web search" known gap as addressed
by the new module. A zero-config DuckDuckGo-scrape fallback remains
on the backlog for users not running SearXNG.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Final verification

- [ ] **Step 1: Run `./test/run`**

Run: `./test/run 2>&1 | tail -10`

Expected: flake8 clean, `1384 passed, 35 skipped`. No failures.

- [ ] **Step 2: Smoke scan with module unconfigured (default)**

Run:
```bash
rm -f /tmp/sf-searxng-smoke.log
SPIDERFOOT_LOG_FORMAT=json timeout 30 python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_searxng 2>/tmp/sf-searxng-smoke.log || true
echo "--- import errors ---"
grep -iE "ImportError|ModuleNotFoundError|Traceback" /tmp/sf-searxng-smoke.log || echo "(none)"
echo "--- searxng-related log lines ---"
grep -iE '"module": "sfp_searxng"' /tmp/sf-searxng-smoke.log | head -5 || echo "(none — module silent when searxng_url empty, expected)"
rm -f /tmp/sf-searxng-smoke.log
```

Expected:
- Import errors: `(none)`.
- SearXNG-related log lines: `(none — module silent when searxng_url empty, expected)`.

If import errors appear, `modules/sfp_searxng.py` has a syntax issue that `python3 -m pytest` didn't catch because it wasn't loaded during unit tests — investigate before proceeding.

- [ ] **Step 3: Smoke scan with module pointed at real SearXNG (if the cluster deployment is reachable)**

If the implementer has network access to the user's SearXNG deployment:

```bash
rm -f /tmp/sf-searxng-live.log
SPIDERFOOT_LOG_FORMAT=json timeout 45 python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_searxng \
    -C <<< '' 2>/tmp/sf-searxng-live.log || true
# note: -C requires a scan ID; the block above is a placeholder — in practice,
# run via the web UI with searxng_url configured, or via a scan config file
echo "--- searxng-related events ---"
grep -cE '"module": "sfp_searxng"' /tmp/sf-searxng-live.log || echo "0"
echo "--- error lines ---"
grep -iE "SearXNG query failed|returned non-JSON" /tmp/sf-searxng-live.log || echo "(none)"
rm -f /tmp/sf-searxng-live.log
```

If this step isn't feasible from the implementer's environment, skip and note in the completion report — the unit tests already cover the happy path with mocked responses, and the user will verify the live integration after merge.

- [ ] **Step 4: Report completion**

Summary: three commits landed — failing tests, module implementation, and CLAUDE.md inventory update. Total modules now 186 (was 185). Test suite at 1384 passed + 35 skipped. Module is a silent no-op by default; becomes active once `searxng_url` is set in the scan UI's module options pane.
