# `sfp_ohdeere_wiki` + `sfp_ohdeere_search` Implementation Plan (Batch 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Parallel dispatch is key to this plan's efficiency.

**Goal:** Ship two independent OhDeereClient consumer modules in one cycle. Modules share no code beyond the already-deployed helper; tasks can dispatch in parallel.

**Architecture:** Same pattern as `sfp_ohdeere_geoip` / `sfp_ohdeere_maps`. Each module: silent no-op when `client.disabled`, per-scan dedup via `_seen`, errorState on auth/server failure, all three OhDeere exception classes mapped to `self.error(...)` + `errorState=True`.

**Tech Stack:** Python 3.12+ stdlib (`json`, `urllib.parse`). Tests use `unittest.TestCase` + `unittest.mock`. No new deps.

**Spec:** `docs/superpowers/specs/2026-04-20-ohdeere-wiki-and-search-design.md`.

---

## Execution strategy

Two parallel tracks, each owned by one subagent, each covering its module's full TDD cycle (failing tests → module → both commits):

- **Track A** (subagent A): `sfp_ohdeere_wiki` + its tests.
- **Track B** (subagent B): `sfp_ohdeere_search` + its tests.

After both tracks commit, a **final-verification task** runs `./test/run` + smoke scan + module discovery.

Modules touch disjoint files, so the tracks cannot conflict. Dispatch them in a single message with two `Agent` tool calls.

---

## File Structure

### Track A (wiki)
- **Create** `modules/sfp_ohdeere_wiki.py` — ~160 lines.
- **Create** `test/unit/modules/test_sfp_ohdeere_wiki.py` — ~170 lines, 7 tests.

### Track B (search)
- **Create** `modules/sfp_ohdeere_search.py` — ~190 lines.
- **Create** `test/unit/modules/test_sfp_ohdeere_search.py` — ~230 lines, 10 tests.

No other file modifications. `CLAUDE.md` inventory update is a separate follow-up.

---

## Context for the implementer

- **Current baseline:** `./test/run` reports 1424 passed + 35 skipped. After both tracks: **1441 passed + 35 skipped** (+7 wiki + +10 search).
- **Reference module:** `modules/sfp_ohdeere_geoip.py` — canonical OhDeereClient consumer shape. Copy its structure.
- **Reference tests:** `test/unit/modules/test_sfp_ohdeere_geoip.py` — same mock pattern (`mock.patch("modules.<name>.get_client", return_value=stub_client)`).
- **`sfp_searxng`** is the URL-classification reference for Track B. The wrapper response has the same `results[].url`/`content` shape as raw SearXNG, so URL internal/external classification + subdomain discovery + email regex extraction are copied verbatim.
- **No new event types** needed. All used types exist in `spiderfoot/event_types.py`.
- **Running tests:** `python3 -m pytest test/<path>/test_<name>.py -v`.
- **Flake8:** max-line-length 120, config in `setup.cfg`.

---

## Track A: `sfp_ohdeere_wiki`

### Task A1: failing tests

**Files:**
- Create: `test/unit/modules/test_sfp_ohdeere_wiki.py`

- [ ] **Step 1: Create the test file**

Write EXACTLY this content:

```python
# test_sfp_ohdeere_wiki.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_wiki import sfp_ohdeere_wiki
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereAuthError


_WIKI_RESPONSE = {
    "results": [
        {
            "title": "Acme Corporation",
            "path": "A/Acme_Corporation",
            "bookName": "wikipedia_en_all_maxi",
            "snippet": "Acme Corporation is a fictional company used as an archetype.",
        }
    ]
}


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereWiki(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_wiki()
        with mock.patch("modules.sfp_ohdeere_wiki.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype="COMPANY_NAME"):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_wiki()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_wiki()
        self.assertEqual(set(module.watchedEvents()),
                         {"COMPANY_NAME", "HUMAN_NAME"})
        for t in ("DESCRIPTION_ABSTRACT", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(self._event("Acme Corporation"))
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_description_abstract_and_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _WIKI_RESPONSE
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event("Acme Corporation"))
        types = [e.eventType for e in emissions]
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(types.count("DESCRIPTOR_ABSTRACT".replace("DESCRIPTOR_", "DESCRIPTION_")), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        self.assertEqual(
            data_by_type["DESCRIPTION_ABSTRACT"],
            "Acme Corporation is a fictional company used as an archetype.",
        )

    def test_empty_results_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = {"results": []}
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "debug") as m_debug:
            module.handleEvent(self._event("Unknown Entity"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("DESCRIPTION_ABSTRACT", types)
        self.assertIn("RAW_RIR_DATA", types)
        m_debug.assert_called()

    def test_result_without_snippet_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = {
            "results": [{"title": "Acme", "path": "A/Acme", "bookName": "w"}]
        }
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event("Acme"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("DESCRIPTION_ABSTRACT", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._event("Acme"))
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()
```

(Note the `DESCRIPTOR_ABSTRACT".replace(...)` oddity is a no-op to work around a linter — do NOT copy that bizarre line literally; use the clean form `types.count("DESCRIPTION_ABSTRACT")` throughout. The assertion tests the string `"DESCRIPTION_ABSTRACT"`.)

Corrected happy-path test body:

```python
def test_happy_path_emits_description_abstract_and_raw(self):
    client = mock.MagicMock()
    client.disabled = False
    client.get.return_value = _WIKI_RESPONSE
    _, module = self._module(client)
    emissions = []
    with mock.patch.object(module, "notifyListeners",
                           side_effect=lambda e: emissions.append(e)):
        module.handleEvent(self._event("Acme Corporation"))
    types = [e.eventType for e in emissions]
    data_by_type = {e.eventType: e.data for e in emissions}
    self.assertEqual(types.count("DESCRIPTION_ABSTRACT"), 1)
    self.assertEqual(types.count("RAW_RIR_DATA"), 1)
    self.assertEqual(
        data_by_type["DESCRIPTION_ABSTRACT"],
        "Acme Corporation is a fictional company used as an archetype.",
    )
```

- [ ] **Step 2: Run the tests and confirm collection failure**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_wiki.py -v`
Expected: `ModuleNotFoundError: No module named 'modules.sfp_ohdeere_wiki'`.

- [ ] **Step 3: Flake8 + commit**

```bash
python3 -m flake8 test/unit/modules/test_sfp_ohdeere_wiki.py
git add test/unit/modules/test_sfp_ohdeere_wiki.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_ohdeere_wiki

Seven unit tests driving Track A implementation: opts/optdescs parity,
watched (COMPANY_NAME + HUMAN_NAME) + produced event shape, silent
no-op when helper disabled, happy-path DESCRIPTION_ABSTRACT + RAW_RIR_DATA
emission, empty results, result missing snippet, OhDeereAuthError
path.

Refs docs/superpowers/specs/2026-04-20-ohdeere-wiki-and-search-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task A2: implement `modules/sfp_ohdeere_wiki.py`

- [ ] **Step 1: Create the module**

Write this to `modules/sfp_ohdeere_wiki.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_wiki
# Purpose:      Entity enrichment via the self-hosted ohdeere-wiki-service
#               (Kiwix ZIM full-text search). Third consumer of
#               spiderfoot/ohdeere_client.py.
# Introduced:   2026-04-20
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import urllib.parse

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
    OhDeereServerError,
    get_client,
)


class sfp_ohdeere_wiki(SpiderFootPlugin):

    meta = {
        "name": "OhDeere Wiki",
        "summary": "Look up companies or human names in the self-hosted "
                   "ohdeere-wiki-service (Kiwix ZIM full-text search) and "
                   "emit a DESCRIPTION_ABSTRACT snippet for the best match.",
        "flags": [],
        "useCases": ["Investigate", "Passive"],
        "categories": ["Content Analysis"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/wiki-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/wiki-service/"],
            "description": "Self-hosted Kiwix proxy (Wikipedia, Stack Exchange, "
                           "LibreTexts ZIMs). Requires the OhDeere client-credentials "
                           "token (OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET env "
                           "vars) with wiki:read scope.",
        },
    }

    opts = {"wiki_base_url": "https://wiki.ohdeere.internal"}
    optdescs = {"wiki_base_url": "Base URL of the ohdeere-wiki-service. Defaults to "
                                 "the cluster-internal hostname; override for local "
                                 "testing."}

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._seen: set[str] = set()
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["COMPANY_NAME", "HUMAN_NAME"]

    def producedEvents(self):
        return ["DESCRIPTION_ABSTRACT", "RAW_RIR_DATA"]

    def handleEvent(self, event):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if event.data in self._seen:
            return
        self._seen.add(event.data)

        params = urllib.parse.urlencode({"q": event.data, "limit": 1})
        payload = self._call(f"/api/v1/search?{params}")
        if payload is None:
            return
        self._emit(event, "RAW_RIR_DATA", json.dumps(payload))

        results = payload.get("results") or []
        if not results:
            self.debug(f"no wiki match for: {event.data}")
            return
        snippet = results[0].get("snippet")
        if snippet:
            self._emit(event, "DESCRIPTION_ABSTRACT", snippet)

    def _call(self, path_with_query):
        base = self.opts["wiki_base_url"].rstrip("/")
        try:
            return self._client.get(path_with_query, base_url=base,
                                    scope="wiki:read")
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
            return None
        except OhDeereServerError as exc:
            self.error(f"OhDeere wiki server error: {exc}")
            self.errorState = True
            return None
        except OhDeereClientError as exc:
            self.error(f"OhDeere wiki request failed: {exc}")
            self.errorState = True
            return None

    def _emit(self, source_event, event_type, data):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_wiki class
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_wiki.py -v`
Expected: **7 passed**.

- [ ] **Step 3: Flake8 + commit**

```bash
python3 -m flake8 modules/sfp_ohdeere_wiki.py
git add modules/sfp_ohdeere_wiki.py
git commit -m "$(cat <<'EOF'
modules: add sfp_ohdeere_wiki — entity enrichment via Kiwix search

Third consumer of spiderfoot/ohdeere_client.py. Watches COMPANY_NAME
and HUMAN_NAME events; for each new name (per-scan dedup), calls
ohdeere-wiki-service /api/v1/search?q=<name>&limit=1 with wiki:read
scope. Emits DESCRIPTION_ABSTRACT (from the top result's snippet) and
RAW_RIR_DATA. No snippet → only RAW_RIR_DATA emitted.

Silent no-op when helper is disabled. Auth / server errors raise
errorState.

Refs docs/superpowers/specs/2026-04-20-ohdeere-wiki-and-search-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Track B: `sfp_ohdeere_search`

### Task B1: failing tests

**Files:**
- Create: `test/unit/modules/test_sfp_ohdeere_search.py`

- [ ] **Step 1: Create the test file**

Write EXACTLY this:

```python
# test_sfp_ohdeere_search.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_search import sfp_ohdeere_search
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereAuthError, OhDeereServerError


def _search_response(results):
    return {
        "query": "site:example.com",
        "results": results,
        "answers": [],
        "suggestions": [],
        "infoboxes": [],
        "number_of_results": len(results),
    }


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereSearch(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_search()
        with mock.patch("modules.sfp_ohdeere_search.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data="example.com", etype="INTERNET_NAME"):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_search()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_search()
        self.assertEqual(set(module.watchedEvents()),
                         {"INTERNET_NAME", "DOMAIN_NAME"})
        for t in ("LINKED_URL_INTERNAL", "LINKED_URL_EXTERNAL",
                  "INTERNET_NAME", "EMAILADDR", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(self._event())
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_all_event_types(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([
            {"url": "https://api.example.com/health", "title": "",
             "content": "contact admin@example.com"},
            {"url": "https://other.org/example-ref", "title": "",
             "content": "example.com was mentioned here"},
        ])
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event())
        types = [e.eventType for e in emissions]
        self.assertEqual(types.count("LINKED_URL_INTERNAL"), 1)
        self.assertEqual(types.count("LINKED_URL_EXTERNAL"), 1)
        self.assertEqual(types.count("INTERNET_NAME"), 1)
        self.assertEqual(types.count("EMAILADDR"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)

    def test_dedup_same_input_single_helper_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([])
        _, module = self._module(client)
        evt = self._event()
        with mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)
        self.assertEqual(client.get.call_count, 1)

    def test_empty_results_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([])
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event())
        types = [e.eventType for e in emissions]
        self.assertEqual(types, ["RAW_RIR_DATA"])

    def test_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_server_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("503")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_errorstate_short_circuits_next_event(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("down")
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(self._event(data="example.com"))
            module.handleEvent(self._event(data="other.example.com"))
        self.assertEqual(client.get.call_count, 1)

    def test_subdomain_discovery_emits_new_internet_name(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _search_response([
            {"url": "https://newhost.example.com/page", "title": "",
             "content": ""},
        ])
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._event())
        types = [e.eventType for e in emissions]
        hosts = [e.data for e in emissions if e.eventType == "INTERNET_NAME"]
        self.assertIn("LINKED_URL_INTERNAL", types)
        self.assertEqual(hosts, ["newhost.example.com"])
```

- [ ] **Step 2: Run the tests and confirm collection failure**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_search.py -v`
Expected: `ModuleNotFoundError: No module named 'modules.sfp_ohdeere_search'`.

- [ ] **Step 3: Flake8 + commit**

```bash
python3 -m flake8 test/unit/modules/test_sfp_ohdeere_search.py
git add test/unit/modules/test_sfp_ohdeere_search.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_ohdeere_search

Ten unit tests driving Track B implementation: opts/optdescs parity,
watched (INTERNET_NAME + DOMAIN_NAME) + produced event shape, silent
no-op, happy-path emission of all five event types (internal/external
URLs, subdomain INTERNET_NAME, EMAILADDR, RAW_RIR_DATA), dedup, empty
results, OhDeereAuthError/OhDeereServerError errorstate, short-circuit,
and subdomain-discovery path.

Refs docs/superpowers/specs/2026-04-20-ohdeere-wiki-and-search-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Task B2: implement `modules/sfp_ohdeere_search.py`

- [ ] **Step 1: Create the module**

Write this to `modules/sfp_ohdeere_search.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_search
# Purpose:      OAuth2-gated SearXNG meta-search via the self-hosted
#               ohdeere-search-service. Fourth consumer of
#               spiderfoot/ohdeere_client.py. Functionally equivalent to
#               sfp_searxng but routed through the cluster's auth
#               gateway.
# Introduced:   2026-04-20
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import re
import urllib.parse

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
    OhDeereServerError,
    get_client,
)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")


class sfp_ohdeere_search(SpiderFootPlugin):

    meta = {
        "name": "OhDeere Search",
        "summary": "Query the self-hosted ohdeere-search-service (SearXNG "
                   "wrapper) with OAuth2 authentication for site:<target> "
                   "dorks. Harvests URLs, subdomains, and emails.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Search Engines"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/search-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/search-service/"],
            "description": "OAuth2-gated SearXNG meta-search. Aggregates "
                           "DuckDuckGo, Brave, Qwant, Startpage, Mojeek, and "
                           "others behind a single endpoint. Requires OHDEERE_CLIENT_ID "
                           "/ OHDEERE_CLIENT_SECRET env vars with search:read scope.",
        },
    }

    opts = {"search_base_url": "https://search.ohdeere.internal"}
    optdescs = {"search_base_url": "Base URL of the ohdeere-search-service. Defaults "
                                   "to the cluster-internal hostname; override for "
                                   "local testing."}

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._handled_events: set[str] = set()
        self._emitted_hostnames: set[str] = set()
        self._emitted_emails: set[str] = set()
        self._client = get_client()
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
        if self._client.disabled:
            return
        if self.errorState:
            return
        if event.data in self._handled_events:
            return
        self._handled_events.add(event.data)

        params = urllib.parse.urlencode({"q": f"site:{event.data}"})
        payload = self._call(f"/api/v1/search?{params}")
        if payload is None:
            return
        self._emit(event, "RAW_RIR_DATA", json.dumps(payload))

        for result in payload.get("results") or []:
            self._process_result(result, event)

    def _process_result(self, result, source_event):
        url = (result or {}).get("url")
        if not url:
            return
        try:
            hostname = self.sf.urlFQDN(url)
        except (TypeError, AttributeError):
            return

        is_internal = False
        target = self.getTarget()
        if target is not None and hostname:
            is_internal = target.matches(hostname, includeChildren=True)

        is_self_echo = (hostname == source_event.data)

        if is_internal:
            self._emit(source_event, "LINKED_URL_INTERNAL", url)
            if (not is_self_echo
                    and hostname
                    and hostname not in self._emitted_hostnames):
                self._emitted_hostnames.add(hostname)
                self._emit(source_event, "INTERNET_NAME", hostname)
        else:
            self._emit(source_event, "LINKED_URL_EXTERNAL", url)

        snippet = (result or {}).get("content") or ""
        for email in _EMAIL_RE.findall(snippet):
            if email in self._emitted_emails:
                continue
            self._emitted_emails.add(email)
            self._emit(source_event, "EMAILADDR", email)

    def _call(self, path_with_query):
        base = self.opts["search_base_url"].rstrip("/")
        try:
            return self._client.get(path_with_query, base_url=base,
                                    scope="search:read")
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
            return None
        except OhDeereServerError as exc:
            self.error(f"OhDeere search server error: {exc}")
            self.errorState = True
            return None
        except OhDeereClientError as exc:
            self.error(f"OhDeere search request failed: {exc}")
            self.errorState = True
            return None

    def _emit(self, source_event, event_type, data):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_search class
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_search.py -v`
Expected: **10 passed**.

- [ ] **Step 3: Flake8 + commit**

```bash
python3 -m flake8 modules/sfp_ohdeere_search.py
git add modules/sfp_ohdeere_search.py
git commit -m "$(cat <<'EOF'
modules: add sfp_ohdeere_search — OAuth2-gated SearXNG wrapper

Fourth consumer of spiderfoot/ohdeere_client.py. Watches INTERNET_NAME
and DOMAIN_NAME events; for each new target (per-scan dedup), calls
ohdeere-search-service /api/v1/search?q=site:<target> with search:read
scope. Emits LINKED_URL_INTERNAL, LINKED_URL_EXTERNAL, INTERNET_NAME
(newly-discovered subdomains under the target TLD), EMAILADDR (regex-
extracted from result snippets), and RAW_RIR_DATA.

URL classification, subdomain discovery with self-echo guard, email
regex, and three-set dedup (handled-events / emitted-hostnames /
emitted-emails) match the sfp_searxng pattern verbatim — only the
endpoint and auth change.

Complements rather than replaces sfp_searxng: the existing module
stays for deployments without the OhDeere auth gateway.

Refs docs/superpowers/specs/2026-04-20-ohdeere-wiki-and-search-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task C: final verification

After both tracks commit (four new commits total), a single verification subagent runs:

- [ ] **Step 1: Full suite**

```bash
./test/run 2>&1 | tail -5
```
Expected: `1441 passed, 35 skipped`, zero failures, flake8 clean.

- [ ] **Step 2: Smoke scan with client disabled (no env vars)**

```bash
rm -f /tmp/sf-batch1-smoke.log
unset OHDEERE_CLIENT_ID OHDEERE_CLIENT_SECRET OHDEERE_AUTH_URL
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_wiki,sfp_ohdeere_search 2>/tmp/sf-batch1-smoke.log &
SF_PID=$!
sleep 25
kill $SF_PID 2>/dev/null; wait $SF_PID 2>/dev/null

echo "--- import errors ---"
grep -iE "ImportError|ModuleNotFoundError|Traceback" /tmp/sf-batch1-smoke.log || echo "(none)"
rm -f /tmp/sf-batch1-smoke.log
```

Expected: `(none)`.

- [ ] **Step 3: Module discovery**

```bash
python3 ./sf.py -M 2>&1 | grep -E "sfp_ohdeere_(wiki|search)"
```

Expected: two lines, one per new module.

- [ ] **Step 4: Targeted test runs**

```bash
python3 -m pytest \
    test/unit/spiderfoot/test_ohdeere_client.py \
    test/unit/modules/test_sfp_ohdeere_geoip.py \
    test/unit/modules/test_sfp_ohdeere_maps.py \
    test/unit/modules/test_sfp_ohdeere_wiki.py \
    test/unit/modules/test_sfp_ohdeere_search.py -v 2>&1 | tail -5
```
Expected: 11 + 12 + 14 + 7 + 10 = 54 passed.

- [ ] **Step 5: Module count**

```bash
echo "Module count: $(ls modules/sfp_*.py | wc -l)"
```
Expected: 190 (was 188 before this batch).

- [ ] **Step 6: Report**

Summary: four commits (tests + module per track × 2), module count 188 → 190, test count 1424 → 1441. Fifth and sixth OhDeereClient consumers land cleanly.
