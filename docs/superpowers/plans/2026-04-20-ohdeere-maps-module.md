# `sfp_ohdeere_maps` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `modules/sfp_ohdeere_maps.py` — the second consumer of `spiderfoot/ohdeere_client.py`. Watches `PHYSICAL_COORDINATES` → reverse-geocodes via `/api/v1/reverse`; watches `PHYSICAL_ADDRESS` → forward-geocodes via `/api/v1/geocode`. Emits `PHYSICAL_ADDRESS`, `PHYSICAL_COORDINATES`, `COUNTRY_NAME`, `GEOINFO`, `RAW_RIR_DATA`.

**Architecture:** Standard `SpiderFootPlugin`. Two endpoint wrappers (`_reverse_geocode`, `_forward_geocode`) share a common `_call` helper for error handling. Uses the shared `get_client()` singleton with scope `maps:read`. Silent no-op when the OhDeere client is disabled (env vars unset); `errorState` on auth / server errors. No changes to the shared helper.

**Tech Stack:** Python 3.12+ stdlib only (`json`, `urllib.parse`). Tests use `unittest.TestCase` + `unittest.mock`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-20-ohdeere-maps-module-design.md`.

---

## File Structure

- **Create** `modules/sfp_ohdeere_maps.py` — ~200 lines. Full module.
- **Create** `test/unit/modules/test_sfp_ohdeere_maps.py` — ~280 lines. 14 unit tests.

No other file modifications. `CLAUDE.md` update is a separate follow-up task after the cluster's `maps:read` scope is verified end-to-end.

---

## Context for the implementer

- **Current baseline:** `./test/run` reports 1410 passed + 35 skipped. After this plan: 1424 passed + 35 skipped.
- **Reference module:** `modules/sfp_ohdeere_geoip.py` — same OhDeereClient consumer pattern (dedup, silent no-op, errorState, get_client() import). Copy the structure; the differences are (a) two watched event types, (b) endpoint paths, (c) response parsing per direction.
- **Reference tests:** `test/unit/modules/test_sfp_ohdeere_geoip.py` — same `mock.patch("modules.<name>.get_client", return_value=stub)` pattern. Copy the test structure; add two extra tests for the forward direction.
- **Helper API:** `get_client().get(path, base_url, scope, timeout=30) → dict`. Raises `OhDeereAuthError`, `OhDeereServerError`, or `OhDeereClientError` (base) on failure.
- **Coordinate format:** `PHYSICAL_COORDINATES` events carry `"<lat>,<lon>"` strings (e.g. `"37.77,-122.42"`). The module's `_parse_coords` splits on comma and validates both halves parse as floats; returns `(None, None)` on any parse failure.
- **Nominatim quirks baked into tests:**
  - Forward response is a **list** of result objects. Empty list is a valid response (not an error).
  - Reverse response is a **single object**. Has `display_name` (full address string) and `address` (dict with `country`, `city`, `town`, `village`, `road`, `postcode`, etc.).
  - `lat` and `lon` in responses are **strings**, not floats. The module preserves them as-is when emitting `PHYSICAL_COORDINATES`.
  - City field chain: `address.city → address.town → address.village`. Pick first present value.
- **Running tests:** `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py -v`.
- **Flake8:** `python3 -m flake8 <file>`. Config in `setup.cfg`, max-line 120.
- **No new event types.** All five emitted types exist in `spiderfoot/event_types.py`.

---

## Task 1: Failing tests for `sfp_ohdeere_maps` (TDD red)

**Files:**
- Create: `test/unit/modules/test_sfp_ohdeere_maps.py`

- [ ] **Step 1: Create the test file with 14 tests**

Write EXACTLY this content to `test/unit/modules/test_sfp_ohdeere_maps.py`:

```python
# test_sfp_ohdeere_maps.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_maps import sfp_ohdeere_maps
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereServerError,
)


_REVERSE_FULL = {
    "place_id": 12345,
    "lat": "37.77",
    "lon": "-122.42",
    "display_name": "1 Market St, San Francisco, CA, United States",
    "address": {
        "road": "1 Market St",
        "city": "San Francisco",
        "state": "CA",
        "postcode": "94105",
        "country": "United States",
        "country_code": "us",
    },
}


_FORWARD_FULL = [
    {
        "place_id": 67890,
        "lat": "37.77",
        "lon": "-122.42",
        "display_name": "1 Market St, San Francisco, CA, United States",
    }
]


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereMaps(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_maps()
        with mock.patch("modules.sfp_ohdeere_maps.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_maps()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_maps()
        self.assertEqual(set(module.watchedEvents()),
                         {"PHYSICAL_COORDINATES", "PHYSICAL_ADDRESS"})
        for t in ("PHYSICAL_ADDRESS", "PHYSICAL_COORDINATES",
                  "COUNTRY_NAME", "GEOINFO", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        evt = self._event("37.77,-122.42", "PHYSICAL_COORDINATES")
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(evt)
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_reverse_happy_path(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _REVERSE_FULL
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        data_by_type = {e.eventType: e.data for e in emissions}
        types = [e.eventType for e in emissions]
        self.assertEqual(types.count("PHYSICAL_ADDRESS"), 1)
        self.assertEqual(types.count("COUNTRY_NAME"), 1)
        self.assertEqual(types.count("GEOINFO"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        self.assertEqual(
            data_by_type["PHYSICAL_ADDRESS"],
            "1 Market St, San Francisco, CA, United States")
        self.assertEqual(data_by_type["COUNTRY_NAME"], "United States")
        self.assertEqual(data_by_type["GEOINFO"],
                         "San Francisco, United States")

    def test_reverse_no_display_name_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = dict(_REVERSE_FULL)
        payload.pop("display_name")
        client.get.return_value = payload
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("PHYSICAL_ADDRESS", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_reverse_city_fallback_to_town(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = {
            "display_name": "Some Road, Smalltown, United States",
            "address": {
                "town": "Smalltown",
                "country": "United States",
            },
        }
        client.get.return_value = payload
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("40.0,-80.0", "PHYSICAL_COORDINATES"))
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(data_by_type["GEOINFO"], "Smalltown, United States")

    def test_reverse_no_city_falls_back_to_country_only(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = {
            "display_name": "Antarctica",
            "address": {"country": "Antarctica"},
        }
        client.get.return_value = payload
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("-75.0,0.0", "PHYSICAL_COORDINATES"))
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(data_by_type["GEOINFO"], "Antarctica")

    def test_reverse_malformed_coords_skipped_without_api_call(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "debug") as m_debug:
            module.handleEvent(
                self._event("not-a-number", "PHYSICAL_COORDINATES"))
        client.get.assert_not_called()
        m_notify.assert_not_called()
        m_debug.assert_called()

    def test_forward_happy_path(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _FORWARD_FULL
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(
                self._event("1 Market St, San Francisco",
                            "PHYSICAL_ADDRESS"))
        types = [e.eventType for e in emissions]
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(types.count("PHYSICAL_COORDINATES"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        self.assertEqual(data_by_type["PHYSICAL_COORDINATES"], "37.77,-122.42")

    def test_forward_empty_results_emits_only_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = []
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "debug") as m_debug:
            module.handleEvent(
                self._event("Unknown Place, Nowhere", "PHYSICAL_ADDRESS"))
        types = [e.eventType for e in emissions]
        self.assertNotIn("PHYSICAL_COORDINATES", types)
        self.assertIn("RAW_RIR_DATA", types)
        m_debug.assert_called()

    def test_dedup_same_input_single_helper_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _REVERSE_FULL
        _, module = self._module(client)
        evt = self._event("37.77,-122.42", "PHYSICAL_COORDINATES")
        with mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)
        self.assertEqual(client.get.call_count, 1)

    def test_reverse_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_forward_server_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("503 upstream")
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(
                self._event("1 Market St", "PHYSICAL_ADDRESS"))
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_errorstate_short_circuits_both_event_types(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("down")
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(
                self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
            module.handleEvent(
                self._event("1 Market St", "PHYSICAL_ADDRESS"))
        # Only the first event's fetch runs; errorState blocks the second.
        self.assertEqual(client.get.call_count, 1)
```

- [ ] **Step 2: Run the tests and confirm they fail at collection**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py -v`

Expected: collection failure with `ModuleNotFoundError: No module named 'modules.sfp_ohdeere_maps'`.

- [ ] **Step 3: Flake8**

Run: `python3 -m flake8 test/unit/modules/test_sfp_ohdeere_maps.py`

Expected: clean. If it warns, fix inline.

- [ ] **Step 4: Commit**

```bash
git add test/unit/modules/test_sfp_ohdeere_maps.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_ohdeere_maps

14 unit tests driving Task 2: opts/optdescs parity, watched/produced
events, silent-no-op when helper is disabled, reverse happy path
(all four event types emitted), reverse nullable display_name,
reverse city fallback to town / country-only, reverse malformed
coordinates skipped, forward happy path, forward empty results,
per-scan dedup, OhDeereAuthError on reverse / OhDeereServerError
on forward both set errorState, and errorState short-circuits
subsequent events regardless of type.

Refs docs/superpowers/specs/2026-04-20-ohdeere-maps-module-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement `modules/sfp_ohdeere_maps.py`

**Files:**
- Create: `modules/sfp_ohdeere_maps.py`

- [ ] **Step 1: Create the module**

Write this content to `modules/sfp_ohdeere_maps.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_maps
# Purpose:      Forward + reverse geocoding via the self-hosted
#               ohdeere-maps-service. PHYSICAL_COORDINATES → /reverse;
#               PHYSICAL_ADDRESS → /geocode. Second consumer of
#               spiderfoot/ohdeere_client.py.
#
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


class sfp_ohdeere_maps(SpiderFootPlugin):

    meta = {
        "name": "OhDeere Maps",
        "summary": "Forward and reverse geocoding via the self-hosted "
                   "ohdeere-maps-service (Nominatim-backed). Watches "
                   "PHYSICAL_COORDINATES and PHYSICAL_ADDRESS; emits "
                   "PHYSICAL_ADDRESS, PHYSICAL_COORDINATES, COUNTRY_NAME, "
                   "GEOINFO, and RAW_RIR_DATA.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Real World"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/maps-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/maps-service/"],
            "description": "Self-hosted wrapper around Nominatim + MaxMind GeoLite2. "
                           "Requires the OhDeere client-credentials token "
                           "(OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET env vars) "
                           "with maps:read scope.",
        },
    }

    opts = {
        "maps_base_url": "https://maps.ohdeere.internal",
    }

    optdescs = {
        "maps_base_url": "Base URL of the ohdeere-maps-service. Defaults to the "
                         "cluster-internal hostname; override for local testing.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._seen: set[str] = set()
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["PHYSICAL_COORDINATES", "PHYSICAL_ADDRESS"]

    def producedEvents(self):
        return [
            "PHYSICAL_ADDRESS",
            "PHYSICAL_COORDINATES",
            "COUNTRY_NAME",
            "GEOINFO",
            "RAW_RIR_DATA",
        ]

    def handleEvent(self, event):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if event.data in self._seen:
            return
        self._seen.add(event.data)

        if event.eventType == "PHYSICAL_COORDINATES":
            self._reverse_geocode(event)
        elif event.eventType == "PHYSICAL_ADDRESS":
            self._forward_geocode(event)

    def _reverse_geocode(self, event):
        lat, lon = self._parse_coords(event.data)
        if lat is None:
            self.debug(f"unparseable PHYSICAL_COORDINATES: {event.data}")
            return
        params = urllib.parse.urlencode({"lat": lat, "lon": lon})
        payload = self._call(f"/api/v1/reverse?{params}")
        if payload is None:
            return
        self._emit(event, "RAW_RIR_DATA", json.dumps(payload))

        display = payload.get("display_name")
        if display:
            self._emit(event, "PHYSICAL_ADDRESS", display)

        address = payload.get("address") or {}
        country = address.get("country")
        city = address.get("city") or address.get("town") or address.get("village")
        if country:
            self._emit(event, "COUNTRY_NAME", country)
            geoinfo = f"{city}, {country}" if city else country
            self._emit(event, "GEOINFO", geoinfo)

    def _forward_geocode(self, event):
        params = urllib.parse.urlencode({"q": event.data, "limit": 1})
        payload = self._call(f"/api/v1/geocode?{params}")
        if payload is None:
            return
        self._emit(event, "RAW_RIR_DATA", json.dumps(payload))

        if not isinstance(payload, list) or not payload:
            self.debug(f"geocode returned no results for: {event.data}")
            return
        first = payload[0]
        lat = first.get("lat")
        lon = first.get("lon")
        if lat is not None and lon is not None:
            self._emit(event, "PHYSICAL_COORDINATES", f"{lat},{lon}")

    def _call(self, path_with_query):
        base = self.opts["maps_base_url"].rstrip("/")
        try:
            return self._client.get(path_with_query, base_url=base,
                                    scope="maps:read")
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
            return None
        except OhDeereServerError as exc:
            self.error(f"OhDeere maps server error: {exc}")
            self.errorState = True
            return None
        except OhDeereClientError as exc:
            self.error(f"OhDeere maps request failed: {exc}")
            self.errorState = True
            return None

    def _parse_coords(self, data: str):
        if not data or "," not in data:
            return None, None
        parts = data.split(",", 1)
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
        except (ValueError, IndexError):
            return None, None
        return lat, lon

    def _emit(self, source_event, event_type: str, data: str) -> None:
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_maps class
```

- [ ] **Step 2: Run the module tests**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py -v`

Expected: **14 passed**.

Common failure modes:
- `test_reverse_happy_path` — check GEOINFO formatting: `"San Francisco, United States"` (city-comma-country).
- `test_reverse_city_fallback_to_town` — ensure the fallback chain reads `city → town → village`, not just `city`.
- `test_reverse_malformed_coords_skipped_without_api_call` — `_parse_coords("not-a-number")` must return `(None, None)` and `_reverse_geocode` must return immediately after `self.debug(...)`. Verify `_seen.add(event.data)` still happens (otherwise dedup tests may misbehave).
- `test_forward_happy_path` — coordinates must preserve Nominatim's string format (`"37.77,-122.42"`, not `"37.77000,-122.42000"`).
- Error-path tests — each `except` branch must both `self.error(...)` AND `self.errorState = True` AND return `None`.

- [ ] **Step 3: Run the full suite**

Run: `./test/run`

Expected: `1424 passed, 35 skipped`. Flake8 clean.

- [ ] **Step 4: Flake8**

Run: `python3 -m flake8 modules/sfp_ohdeere_maps.py`

Expected: clean.

- [ ] **Step 5: Verify module discovery**

Run:
```bash
python3 ./sf.py -M 2>&1 | grep "sfp_ohdeere_maps"
```

Expected: one line showing the module + its summary.

- [ ] **Step 6: Commit**

```bash
git add modules/sfp_ohdeere_maps.py
git commit -m "$(cat <<'EOF'
modules: add sfp_ohdeere_maps — forward + reverse geocoding

Second consumer of spiderfoot/ohdeere_client.py. Wraps two
endpoints of ohdeere-maps-service: /api/v1/reverse for
PHYSICAL_COORDINATES → PHYSICAL_ADDRESS + COUNTRY_NAME + GEOINFO
conversion, and /api/v1/geocode for PHYSICAL_ADDRESS →
PHYSICAL_COORDINATES. Uses maps:read scope.

Silent no-op when OhDeere client is disabled — safe to merge
before the cluster has env vars set. Auth and server errors set
errorState, matching the sfp_ohdeere_geoip pattern. Malformed
input coordinates (unparseable PHYSICAL_COORDINATES data) are
logged at debug and skipped without calling the API.

Closes the address/coordinates round-trip gap: chains like
IP → (geoip) PHYSICAL_COORDINATES → (maps) PHYSICAL_ADDRESS now
work end-to-end.

Refs docs/superpowers/specs/2026-04-20-ohdeere-maps-module-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Final verification

- [ ] **Step 1: Full CI-equivalent run**

Run: `./test/run 2>&1 | tail -10`

Expected: flake8 clean, `1424 passed, 35 skipped`, zero failures.

- [ ] **Step 2: Smoke scan with the client disabled (no env vars)**

```bash
rm -f /tmp/sf-maps-smoke.log
unset OHDEERE_CLIENT_ID OHDEERE_CLIENT_SECRET OHDEERE_AUTH_URL
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_maps 2>/tmp/sf-maps-smoke.log &
SF_PID=$!
sleep 25
kill $SF_PID 2>/dev/null; wait $SF_PID 2>/dev/null

echo "--- import errors ---"
grep -iE "ImportError|ModuleNotFoundError|Traceback" /tmp/sf-maps-smoke.log || echo "(none)"
echo "--- ohdeere maps log lines ---"
grep -E '"module": "sfp_ohdeere_maps"' /tmp/sf-maps-smoke.log | head -5 || echo "(none — disabled module logs nothing, expected)"
rm -f /tmp/sf-maps-smoke.log
```

Expected:
- Import errors: `(none)`.
- sfp_ohdeere_maps log lines: `(none — ...)`.

- [ ] **Step 3: Module discovery**

```bash
python3 ./sf.py -M 2>&1 | grep "sfp_ohdeere_maps"
```

Expected: one line listing the module.

- [ ] **Step 4: Optional live smoke scan**

If you can set `OHDEERE_CLIENT_ID` / `OHDEERE_CLIENT_SECRET` from a real cluster secret:

```bash
export OHDEERE_CLIENT_ID=spiderfoot-m2m
export OHDEERE_CLIENT_SECRET="<retrieve from sealed secret>"
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_geoip,sfp_ohdeere_maps \
    2>&1 | tail -30
```

Expected: `PHYSICAL_ADDRESS` and `GEOINFO` events surface after `sfp_ohdeere_geoip` emits `PHYSICAL_COORDINATES`. No auth errors in the log.

If the implementer lacks cluster access, skip and note in the report.

- [ ] **Step 5: Typed-event-registry invariants still green**

Run:
```bash
python3 -m pytest test/unit/spiderfoot/test_event_types.py test/unit/spiderfoot/test_spiderfootevent.py -v 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 6: Report completion**

Summary: two commits — failing tests + module implementation. Module count 187 → 188. Test count 1410 → 1424. Second consumer of the OhDeere client helper lands cleanly. Follow-up: CLAUDE.md inventory update in a separate commit, and an optional live smoke scan once credentials are wired.
