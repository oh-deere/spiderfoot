# `sfp_ohdeere_celltower` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `sfp_ohdeere_celltower` — a SpiderFoot module that wraps the self-hosted `ohdeere-celltower-service` (OpenCellID) for both directions: nearby-tower lookup from a `PHYSICAL_COORDINATES` event (Path A), and CGI-tuple resolve via a new `CGI_TOWER` event type (Path B). Reuses `maps_deeplink()` for clickable map URLs and the same grid-snap cache + per-scan cap pattern as `sfp_ohdeere_maps`.

**Architecture:** New module + one new event type (`CGI_TOWER`, `ENTITY` category). Two trigger paths in one module — `_nearby` (coordinate-driven) and `_resolve` (CGI-driven). Path B emits `PHYSICAL_COORDINATES` which feeds back into Path A and into `sfp_ohdeere_maps`; the loop is bounded because nothing re-emits `PHYSICAL_COORDINATES` from a coord input.

**Tech Stack:** Python 3.7+, stdlib only (`urllib.parse`, `json`). Existing `OhDeereClient` for HTTP+auth (`celltower:read` scope). `spiderfoot.ohdeere_maps_url.maps_deeplink` for SFURLs. No new Python deps, no Dockerfile change, no new env vars.

**Spec:** `docs/superpowers/specs/2026-04-26-sfp-ohdeere-celltower-design.md`

---

## File map

| Action | File |
|---|---|
| Modify | `spiderfoot/event_types.py` — add `EventType.CGI_TOWER` + `EVENT_TYPES` entry |
| Modify | `test/unit/spiderfoot/test_event_types.py` — bump count assertions (172→173, ENTITY 57→58) |
| Create | `modules/sfp_ohdeere_celltower.py` |
| Create | `test/unit/modules/test_sfp_ohdeere_celltower.py` (~10 tests) |
| Modify | `CLAUDE.md` — FREE_NOAUTH_UNLIMITED list, OhDeere consumer-modules table, surviving-modules count, helpers section |
| Modify | `docs/superpowers/BACKLOG.md` — mark celltower shipped, no longer parked |

---

## Task 1: Register the `CGI_TOWER` event type

**Files:**
- Modify: `spiderfoot/event_types.py`
- Modify: `test/unit/spiderfoot/test_event_types.py`

- [ ] **Step 1: Update the count assertions first (failing tests)**

Edit `test/unit/spiderfoot/test_event_types.py`. Find the lines:

```python
        self.assertEqual(len(EVENT_TYPES), 172)
```

and:

```python
        self.assertEqual(counts[EventTypeCategory.ENTITY], 57)
```

Bump both:

```python
        self.assertEqual(len(EVENT_TYPES), 173)
```

```python
        self.assertEqual(counts[EventTypeCategory.ENTITY], 58)
```

- [ ] **Step 2: Run the test file to verify the failures**

Run: `python3 -m pytest test/unit/spiderfoot/test_event_types.py -v`
Expected: at least the count + ENTITY-category tests fail (`172 != 173`, `57 != 58`). Other invariant tests may also fail (they check that every `EventType` enum member has an `EVENT_TYPES` entry — but no new member exists yet so those still pass).

- [ ] **Step 3: Add the enum member + dict entry to `event_types.py`**

In `spiderfoot/event_types.py`, find the `EventType` enum block. Insert in alphabetical position (between `BSSID` / `CO2_INTENSITY` / similar — exact neighbours don't matter, but keep alphabetical):

Find an existing line like `BSSID = "BSSID"` to anchor your edit, and add:

```python
    CGI_TOWER = "CGI_TOWER"
```

In the `EVENT_TYPES` dict (further down the file), find a similarly-positioned ENTITY entry (e.g. `EventType.BSSID` or `EventType.BGP_AS_OWNER`) to anchor, and add:

```python
    EventType.CGI_TOWER: EventTypeDef(
        "CGI_TOWER", "Cell Tower (CGI)",
        EventTypeCategory.ENTITY, is_raw=False,
    ),
```

- [ ] **Step 4: Run the event-types tests; expect green**

Run: `python3 -m pytest test/unit/spiderfoot/test_event_types.py -v`
Expected: all green. The drift, count, and category-distribution assertions should now agree.

- [ ] **Step 5: Lint**

Run: `python3 -m flake8 spiderfoot/event_types.py test/unit/spiderfoot/test_event_types.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add spiderfoot/event_types.py test/unit/spiderfoot/test_event_types.py
git commit -m "event_types: add CGI_TOWER (Cell Tower) ENTITY-category type"
```

---

## Task 2: Failing tests for `sfp_ohdeere_celltower`

**Files:**
- Create: `test/unit/modules/test_sfp_ohdeere_celltower.py`

- [ ] **Step 1: Inspect the maps test file for the established fixture pattern**

Run: `head -55 test/unit/modules/test_sfp_ohdeere_maps.py`
Expected: shows `_module(client)` patching `get_client`, `setTarget`, `_event(data, etype)`. Mirror that.

- [ ] **Step 2: Write the failing test file**

Create `test/unit/modules/test_sfp_ohdeere_celltower.py`:

```python
# test_sfp_ohdeere_celltower.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_celltower import sfp_ohdeere_celltower
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
)


_RESOLVE_CELL = {
    "mcc": 240, "mnc": 1, "lac": 12345, "cid": 67890,
    "radio": "GSM", "lon": 18.0686, "lat": 59.3293,
    "rangeM": 1500, "samples": 234, "changeable": False,
    "firstSeen": "2020-01-01T00:00:00Z",
    "lastSeen": "2024-12-31T00:00:00Z",
    "averageSignal": -85,
}

_NEARBY_RESPONSE = [
    {
        "cell": {
            "mcc": 240, "mnc": 1, "lac": 100, "cid": 42,
            "radio": "LTE", "lon": 18.0686, "lat": 59.3293,
            "rangeM": 1000, "samples": 10,
        },
        "distanceMeters": 123.4,
    },
    {
        "cell": {
            "mcc": 240, "mnc": 2, "lac": 100, "cid": 99,
            "radio": "GSM", "lon": 18.07, "lat": 59.33,
            "rangeM": 800, "samples": 5,
        },
        "distanceMeters": 250.0,
    },
]


def _fake_get_routing(cgi_record=None, nearby=None):
    """Route /cgi/nearby vs /cgi/{m}/{n}/{l}/{c} to the right fake response."""
    def fake(path, **_kwargs):
        if "/cgi/nearby" in path:
            return [] if nearby is None else nearby
        if "/cgi/" in path:
            return cgi_record
        return None
    return fake


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereCelltower(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_celltower()
        with mock.patch("modules.sfp_ohdeere_celltower.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype):
        root = SpiderFootEvent("ROOT", data, "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_celltower()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_celltower()
        self.assertEqual(set(module.watchedEvents()),
                         {"PHYSICAL_COORDINATES", "CGI_TOWER"})
        self.assertEqual(set(module.producedEvents()),
                         {"GEOINFO", "RAW_RIR_DATA", "PHYSICAL_COORDINATES"})

    def test_path_a_nearby_emits_per_tower_geoinfo_and_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("59.3293,18.0686", "PHYSICAL_COORDINATES"))

        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)
        url = nearby_calls[0].args[0]
        self.assertIn("lat=59.33", url)
        self.assertIn("lon=18.07", url)
        self.assertIn("radius_m=5000", url)

        geos = [e for e in emitted if e.eventType == "GEOINFO"]
        self.assertEqual(len(geos), 2)
        self.assertIn("Cell tower [LTE] 240/1/100/42", geos[0].data)
        self.assertIn("range ~1000m", geos[0].data)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/59.3293/18.0686</SFURL>",
            geos[0].data,
        )

        raws = [e for e in emitted if e.eventType == "RAW_RIR_DATA"]
        self.assertEqual(len(raws), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/59.33/18.07</SFURL>",
            raws[0].data,
        )

    def test_path_a_strips_sfurl_suffix_from_coord_input(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        module.notifyListeners = lambda evt: None
        # Upstream emitters (sfp_ohdeere_geoip, sfp_ohdeere_maps) append
        # "\n<SFURL>...</SFURL>" to the coord data.
        coord = "59.3293,18.0686\n<SFURL>https://x</SFURL>"
        module.handleEvent(self._event(coord, "PHYSICAL_COORDINATES"))
        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)

    def test_path_a_cache_hit_skips_second_api_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        module.notifyListeners = lambda evt: None
        module.handleEvent(self._event("59.3293,18.0686", "PHYSICAL_COORDINATES"))
        # Different ".data" string but same 0.01° cell.
        module.handleEvent(self._event("59.3299,18.0691", "PHYSICAL_COORDINATES"))
        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)

    def test_path_a_cap_drops_after_threshold(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(nearby=_NEARBY_RESPONSE)
        _, module = self._module(client)
        module.opts["nearby_max_unique_cells_per_scan"] = 2
        module.notifyListeners = lambda evt: None
        module.handleEvent(self._event("59.33,18.07", "PHYSICAL_COORDINATES"))
        module.handleEvent(self._event("40.71,-74.00", "PHYSICAL_COORDINATES"))
        module.handleEvent(self._event("51.50,-0.12", "PHYSICAL_COORDINATES"))
        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 2)

    def test_path_b_resolve_emits_coords_geoinfo_raw(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(cgi_record=_RESOLVE_CELL)
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("240,1,12345,67890", "CGI_TOWER"))

        # Hit the resolve URL with the right path.
        resolve_calls = [c for c in client.get.call_args_list
                         if "/cgi/240/1/12345/67890" in c.args[0]]
        self.assertEqual(len(resolve_calls), 1)

        types = [e.eventType for e in emitted]
        self.assertIn("PHYSICAL_COORDINATES", types)
        self.assertIn("GEOINFO", types)
        self.assertIn("RAW_RIR_DATA", types)

        coord = next(e for e in emitted if e.eventType == "PHYSICAL_COORDINATES")
        self.assertIn("59.3293,18.0686", coord.data)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/59.3293/18.0686</SFURL>",
            coord.data,
        )

        geo = next(e for e in emitted if e.eventType == "GEOINFO")
        self.assertIn("Cell tower [GSM] 240/1/12345/67890", geo.data)
        self.assertIn("range ~1500m", geo.data)

    def test_path_b_unknown_cgi_404_no_emissions_no_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        # Mirror what OhDeereClient raises for any 4xx (including 404).
        client.get.side_effect = OhDeereClientError(
            "404 on GET https://celltower.ohdeere.internal/api/v1/cgi/240/1/0/0: "
        )
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("240,1,0,0", "CGI_TOWER"))
        self.assertEqual(emitted, [])
        self.assertFalse(module.errorState)

    def test_path_b_malformed_cgi_input_skipped(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        # Malformed: only 3 fields, and last one isn't a number.
        module.handleEvent(self._event("240,1,nope", "CGI_TOWER"))
        client.get.assert_not_called()
        self.assertEqual(emitted, [])
        self.assertFalse(module.errorState)

    def test_path_b_input_dedup(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = _fake_get_routing(cgi_record=_RESOLVE_CELL)
        _, module = self._module(client)
        module.notifyListeners = lambda evt: None
        module.handleEvent(self._event("240,1,12345,67890", "CGI_TOWER"))
        module.handleEvent(self._event("240,1,12345,67890", "CGI_TOWER"))
        resolve_calls = [c for c in client.get.call_args_list
                         if "/cgi/240/1/12345/67890" in c.args[0]]
        self.assertEqual(len(resolve_calls), 1)

    def test_auth_error_trips_errorstate_and_short_circuits(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(self._event("59.33,18.07", "PHYSICAL_COORDINATES"))
            module.handleEvent(self._event("40.71,-74.00", "PHYSICAL_COORDINATES"))
        self.assertTrue(module.errorState)
        self.assertEqual(client.get.call_count, 1)
```

- [ ] **Step 3: Run to verify red state**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_celltower.py -v`
Expected: ImportError on `modules.sfp_ohdeere_celltower`. Collection fails.

- [ ] **Step 4: Commit the failing tests**

```bash
git add test/unit/modules/test_sfp_ohdeere_celltower.py
git commit -m "test: add failing tests for sfp_ohdeere_celltower (Path A + B)"
```

---

## Task 3: Implement `sfp_ohdeere_celltower`

**Files:**
- Create: `modules/sfp_ohdeere_celltower.py`

- [ ] **Step 1: Write the module**

Create `modules/sfp_ohdeere_celltower.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_celltower
# Purpose:      Cell-tower lookups via the self-hosted ohdeere-celltower-service
#               (OpenCellID-backed). Path A: PHYSICAL_COORDINATES → /api/v1/
#               cgi/nearby. Path B: CGI_TOWER → /api/v1/cgi/{mcc}/{mnc}/{lac}/
#               {cid}.
# Introduced:   2026-04-26 — unblocks the previously parked module by adding
#               CGI_TOWER as a new ENTITY-category event type AND wiring a
#               coordinate-driven nearby path that doesn't need a producer.
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
from spiderfoot.ohdeere_maps_url import DEFAULT_BASE_URL, maps_deeplink


class sfp_ohdeere_celltower(SpiderFootPlugin):

    meta = {
        "name": "OhDeere Cell Tower",
        "summary": "Resolve cell-tower CGI tuples and discover towers near a "
                   "coordinate via the self-hosted ohdeere-celltower-service "
                   "(OpenCellID-backed). Watches PHYSICAL_COORDINATES (nearby "
                   "lookup) and CGI_TOWER (resolve to lat/lon).",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Real World"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/celltower-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/celltower-service/",
                           "https://opencellid.org"],
            "description": "Self-hosted OpenCellID wrapper. Requires the "
                           "OhDeere client-credentials token "
                           "(OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET env "
                           "vars) with celltower:read scope.",
        },
    }

    opts = {
        "celltower_base_url": "https://celltower.ohdeere.internal",
        "maps_ui_base_url": DEFAULT_BASE_URL,
        "nearby_radius_m": 5000,
        "nearby_limit": 10,
        "nearby_max_unique_cells_per_scan": 25,
    }

    optdescs = {
        "celltower_base_url": "Base URL of the ohdeere-celltower-service. "
                              "Defaults to the cluster-internal hostname.",
        "maps_ui_base_url": "Base URL of the maps web UI used to build SFURL "
                            "deep-links on emitted events.",
        "nearby_radius_m": "Search radius in meters for /cgi/nearby tower "
                           "lookup (default 5000 — towers cover km-scale "
                           "areas).",
        "nearby_limit": "Max towers returned per /cgi/nearby call (default 10).",
        "nearby_max_unique_cells_per_scan": "Soft cap on unique grid cells "
                                            "(~1km each) probed per scan "
                                            "(default 25).",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._nearby_cells: dict[tuple[float, float], list] = {}
        self._seen_cgi: set[str] = set()
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["PHYSICAL_COORDINATES", "CGI_TOWER"]

    def producedEvents(self):
        return ["GEOINFO", "RAW_RIR_DATA", "PHYSICAL_COORDINATES"]

    def handleEvent(self, event):
        if self._client.disabled:
            return
        if self.errorState:
            return

        if event.eventType == "PHYSICAL_COORDINATES":
            self._nearby(event)
        elif event.eventType == "CGI_TOWER":
            self._resolve(event)

    def _nearby(self, event):
        lat, lon = self._parse_coords(event.data)
        if lat is None:
            return
        cell = (round(lat, 2), round(lon, 2))
        if cell in self._nearby_cells:
            return
        cap = int(self.opts["nearby_max_unique_cells_per_scan"])
        if len(self._nearby_cells) >= cap:
            self.debug(
                f"hit nearby_max_unique_cells_per_scan={cap}; "
                f"skipping cell {cell}"
            )
            return

        params = urllib.parse.urlencode({
            "lat": cell[0],
            "lon": cell[1],
            "radius_m": int(self.opts["nearby_radius_m"]),
            "limit": int(self.opts["nearby_limit"]),
        })
        url = f"/api/v1/cgi/nearby?{params}"
        payload = self._call(url)
        items = payload if isinstance(payload, list) else []
        self._nearby_cells[cell] = items

        self._emit_with_link(
            event, "RAW_RIR_DATA",
            json.dumps(items, ensure_ascii=False),
            cell[0], cell[1],
        )

        for entry in items:
            tower = entry.get("cell") if isinstance(entry, dict) else None
            if not isinstance(tower, dict):
                continue
            data = self._format_tower(tower)
            if data is None:
                continue
            t_lat = tower.get("lat")
            t_lon = tower.get("lon")
            if t_lat is None or t_lon is None:
                continue
            self._emit_with_link(event, "GEOINFO", data, t_lat, t_lon)

    def _resolve(self, event):
        if event.data in self._seen_cgi:
            return
        self._seen_cgi.add(event.data)

        parts = [p.strip() for p in (event.data or "").split(",")]
        if len(parts) != 4:
            self.debug(f"malformed CGI_TOWER (need 4 comma-separated ints): "
                       f"{event.data!r}")
            return
        try:
            mcc, mnc, lac, cid = (int(p) for p in parts)
        except ValueError:
            self.debug(f"malformed CGI_TOWER (non-integer field): "
                       f"{event.data!r}")
            return

        url = f"/api/v1/cgi/{mcc}/{mnc}/{lac}/{cid}"
        payload = self._call_resolve(url)
        if not isinstance(payload, dict):
            return

        t_lat = payload.get("lat")
        t_lon = payload.get("lon")
        if t_lat is None or t_lon is None:
            self.debug(f"resolve returned record without lat/lon: {payload}")
            return

        self._emit_with_link(
            event, "RAW_RIR_DATA",
            json.dumps(payload, ensure_ascii=False),
            t_lat, t_lon,
        )
        self._emit_with_link(
            event, "PHYSICAL_COORDINATES",
            f"{t_lat},{t_lon}", t_lat, t_lon,
        )
        data = self._format_tower(payload)
        if data is not None:
            self._emit_with_link(event, "GEOINFO", data, t_lat, t_lon)

    def _format_tower(self, tower) -> "str | None":
        try:
            radio = tower.get("radio") or "?"
            mcc = tower.get("mcc")
            mnc = tower.get("mnc")
            lac = tower.get("lac")
            cid = tower.get("cid")
            if mcc is None or mnc is None or lac is None or cid is None:
                return None
            range_m = tower.get("rangeM")
            range_str = f"~{range_m}m" if range_m is not None else "unknown"
            return (
                f"Cell tower [{radio}] {mcc}/{mnc}/{lac}/{cid} "
                f"\u2014 range {range_str}"
            )
        except Exception as exc:
            self.debug(f"tower format failed: {exc}")
            return None

    def _parse_coords(self, data: str):
        # Tolerate the "\n<SFURL>...</SFURL>" suffix that other OhDeere modules
        # append to PHYSICAL_COORDINATES emissions.
        first = (data or "").split("\n", 1)[0]
        if "," not in first:
            return None, None
        parts = first.split(",", 1)
        try:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
        except (ValueError, IndexError):
            return None, None
        return lat, lon

    def _call(self, path_with_query):
        """Call the gateway; trip errorState on auth/server errors only."""
        base = self.opts["celltower_base_url"].rstrip("/")
        try:
            return self._client.get(
                path_with_query, base_url=base, scope="celltower:read",
            )
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
            return None
        except OhDeereServerError as exc:
            self.error(f"OhDeere celltower server error: {exc}")
            self.errorState = True
            return None
        except OhDeereClientError as exc:
            # 4xx (incl. 404 on /nearby for an out-of-range coord) — debug-log,
            # skip, no errorState.
            self.debug(f"OhDeere celltower request rejected: {exc}")
            return None

    def _call_resolve(self, path):
        """Same as _call but treats 4xx as 'unknown CGI' (no error)."""
        return self._call(path)

    def _emit_with_link(self, source_event, event_type: str, data: str,
                        lat, lon) -> None:
        link = maps_deeplink(
            float(lat), float(lon),
            base_url=self.opts["maps_ui_base_url"],
        )
        evt = SpiderFootEvent(
            event_type,
            f"{data}\n<SFURL>{link}</SFURL>",
            self.__name__,
            source_event,
        )
        self.notifyListeners(evt)


# End of sfp_ohdeere_celltower class
```

- [ ] **Step 2: Run all tests; expect 10 green**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_celltower.py -v`
Expected: 10 passed.

- [ ] **Step 3: Lint**

Run: `python3 -m flake8 modules/sfp_ohdeere_celltower.py test/unit/modules/test_sfp_ohdeere_celltower.py`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add modules/sfp_ohdeere_celltower.py
git commit -m "sfp_ohdeere_celltower: Path A nearby + Path B CGI resolve"
```

---

## Task 4: Loader smoke + repo-wide lint + neighbour tests

**Files:** none — verification only.

- [ ] **Step 1: Loader smoke**

Run:

```bash
python3 -c "
from spiderfoot import SpiderFootHelpers
mods = SpiderFootHelpers.loadModulesAsDict('modules', ['sfp__stor_db.py', 'sfp__stor_stdout.py'])
m = mods['sfp_ohdeere_celltower']
print('name:', m['name'])
print('cats:', m['cats'])
print('produces:', m['provides'])
print('consumes:', m['consumes'])
print('opts:', sorted(m['opts'].keys()))
"
```

Expected output:

```
name: OhDeere Cell Tower
cats: ['Real World']
produces: ['GEOINFO', 'RAW_RIR_DATA', 'PHYSICAL_COORDINATES']
consumes: ['PHYSICAL_COORDINATES', 'CGI_TOWER']
opts: ['celltower_base_url', 'maps_ui_base_url', 'nearby_limit', 'nearby_max_unique_cells_per_scan', 'nearby_radius_m']
```

- [ ] **Step 2: Repo-wide lint**

Run: `python3 -m flake8 . --count`
Expected: `0`.

- [ ] **Step 3: Run touched + neighbour tests**

Run:

```bash
python3 -m pytest \
  test/unit/spiderfoot/test_event_types.py \
  test/unit/modules/test_sfp_ohdeere_celltower.py \
  test/unit/modules/test_sfp_ohdeere_maps.py \
  test/unit/modules/test_sfp_ohdeere_geoip.py \
  test/unit/spiderfoot/test_ohdeere_maps_url.py \
  -q --no-cov
```

Expected: all green. ~50+ tests total.

- [ ] **Step 4: No commit** — verification only.

---

## Task 5: Docs — CLAUDE.md + BACKLOG.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/BACKLOG.md`

- [ ] **Step 1: Update CLAUDE.md FREE_NOAUTH_UNLIMITED list**

Find `### FREE_NOAUTH_UNLIMITED (97)` and change to:

```
### FREE_NOAUTH_UNLIMITED (98)
```

In the same list (alphabetical), find `- sfp_ohdeere_search` and insert above it (alphabetical: "celltower" < "geoip" < ... < "search" — actually "celltower" comes *before* the OhDeere block alphabetically, but the list groups OhDeere together; insert in OhDeere alphabetical order):

Find `- sfp_ohdeere_geoip` and insert above it:

```
- sfp_ohdeere_celltower
```

- [ ] **Step 2: Update CLAUDE.md surviving-modules count**

Find:

```
The **187** surviving non-storage modules are listed below
```

Change to:

```
The **188** surviving non-storage modules are listed below
```

- [ ] **Step 3: Update CLAUDE.md OhDeere consumer-modules table**

Insert this row in the table (logical position next to `sfp_ohdeere_maps`, since the two share the coordinate-driven pattern):

```
| `sfp_ohdeere_celltower` | `celltower:read` | `PHYSICAL_COORDINATES` (nearby tower lookup, grid-cached ~1km, `nearby_max_unique_cells_per_scan=25` cap), `CGI_TOWER` (resolve a CGI tuple) → `PHYSICAL_COORDINATES`, `GEOINFO`, `RAW_RIR_DATA`. All emissions carry SFURL deep-links. New `CGI_TOWER` event type lets future producers (leaked-CDR parsers, IoT dumps) feed cell IDs in. |
```

- [ ] **Step 4: Add a one-line CGI_TOWER note to the helpers/notes section**

Find the "Shared helpers" or similar section in CLAUDE.md and append (place after the `ohdeere_maps_url.py` line):

```
- `CGI_TOWER` (new ENTITY-category event type, 2026-04-26) — `"MCC,MNC,LAC,CID"` strings consumed by `sfp_ohdeere_celltower` for tower resolution. No in-tree producers yet; available for future leaked-CDR / IoT-dump parser modules.
```

- [ ] **Step 5: Update BACKLOG.md — promote celltower from Parked to Done**

Find this section:

```
### `sfp_ohdeere_celltower` (parked — no event fit)
- **What:** OpenCellID lookups. Takes MCC/MNC/LAC/CID tuples or lat/lon.
- **Blocker:** no existing SpiderFoot event type carries cell tower identifiers; no input events means no natural event-bus flow.
- **Size:** small if unblocked, but design question is: which event type would trigger this module?
- **Status:** parked until a specific use case emerges (e.g. correlation with leaked call-detail records).
```

Replace with:

```
### `sfp_ohdeere_celltower` — shipped 2026-04-26
- Path A: trigger on `PHYSICAL_COORDINATES`, call `/api/v1/cgi/nearby`, emit per-tower `GEOINFO` + bulk `RAW_RIR_DATA` with map deep-links.
- Path B: new `CGI_TOWER` event type (`"MCC,MNC,LAC,CID"`) → `/api/v1/cgi/{mcc}/{mnc}/{lac}/{cid}` → emits `PHYSICAL_COORDINATES` + `GEOINFO` + `RAW_RIR_DATA`. No in-tree producers yet; the new event type unblocks future leaked-CDR / IoT-dump parsers.
- Reuses `sfp_ohdeere_maps_url.maps_deeplink` and the grid-snap cache pattern from `sfp_ohdeere_maps`.
- Spec: `docs/superpowers/specs/2026-04-26-sfp-ohdeere-celltower-design.md`.
- Plan: `docs/superpowers/plans/2026-04-26-sfp-ohdeere-celltower.md`.
```

Find the priority-table row:

```
| Parked | `sfp_ohdeere_celltower` (no event fit) |
```

Replace with:

```
| ~~Parked~~ Done | ~~`sfp_ohdeere_celltower`~~ — shipped 2026-04-26 |
```

- [ ] **Step 6: Verify**

Run: `grep -A 1 "sfp_ohdeere_celltower.*shipped" docs/superpowers/BACKLOG.md | head -3`
Expected: shows the "shipped 2026-04-26" header.

Run: `grep -c "sfp_ohdeere_celltower" CLAUDE.md`
Expected: at least `2` (list entry + table row).

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "docs: CLAUDE.md + BACKLOG.md — sfp_ohdeere_celltower shipped"
```

---

## Task 6: Final verify

**Files:** none — verification only.

- [ ] **Step 1: Show the commit chain**

Run: `git log --oneline -8`
Expected: ~5 new commits — event-type registry, failing tests, impl, (no Task 4 commit), docs.

- [ ] **Step 2: Run focused tests one more time**

Run:

```bash
python3 -m pytest \
  test/unit/modules/test_sfp_ohdeere_celltower.py \
  test/unit/spiderfoot/test_event_types.py \
  -q --no-cov
```

Expected: all green.

- [ ] **Step 3: Done.** Report the commit list and any notes.

---

## Self-review

**Spec coverage:**

- "Architecture / single new module + event-type registry change" → Tasks 1, 2, 3.
- "Event-type registry change" (CGI_TOWER, ENTITY category, count bumps 172→173 and 57→58) → Task 1.
- "CGI string format" (`"MCC,MNC,LAC,CID"`, comma-separated, `s.split(",")`) → Task 3 step 1's `_resolve` parser; Task 2 tests #7, #8, #9.
- "Module shape" (meta block, opts incl. `nearby_radius_m=5000`) → Task 3 step 1.
- "Path A" (PHYSICAL_COORDINATES → /cgi/nearby, grid-snap cache, per-scan cap) → Task 3 step 1's `_nearby`; Task 2 tests #3, #4, #5, #6.
- "Path B" (CGI_TOWER → /cgi/{...}, emit PHYSICAL_COORDINATES + GEOINFO + RAW_RIR_DATA, dedup) → Task 3 step 1's `_resolve`; Task 2 tests #7, #10.
- "Output format details" (GEOINFO `Cell tower [RADIO] M/N/L/C — range ~Rm`) → Task 3 step 1's `_format_tower`; Task 2 tests #3, #7 assert the format.
- "Error contract" — auth/server errors trip errorState, 4xx debug-logged, malformed input debug-logged → Task 3 step 1's `_call` + `_resolve`; Task 2 tests #8, #9, #10.
- "Testing" — all 10 spec'd tests appear in Task 2.
- "CLAUDE.md / BACKLOG.md updates" — Task 5.

**Placeholder scan:** No "TBD" / "TODO" / "add error handling" / etc. Every code block is complete; every shell command has expected output.

**Type consistency:**
- `_format_tower(tower)` returns `str | None`; consumers (`_nearby`, `_resolve`) check `if data is None: continue` / `if data is not None: emit`. Consistent.
- `_parse_coords(data)` returns `(lat, lon)` or `(None, None)`; consumer checks `if lat is None: return`. Consistent.
- `_call(path)` returns `dict | list | None`; `_nearby` checks `isinstance(payload, list)`; `_resolve` checks `isinstance(payload, dict)`. Consistent with the gateway's actual response shapes (list-of-NearbyCell vs single Cell).
- `_emit_with_link(source_event, event_type, data, lat, lon)` — same signature shape as `sfp_ohdeere_maps`'s helper; called identically from both `_nearby` and `_resolve`.
- Opt names — `celltower_base_url`, `maps_ui_base_url`, `nearby_radius_m`, `nearby_limit`, `nearby_max_unique_cells_per_scan` — match between source (Task 3), tests (Task 2), spec, and CLAUDE.md (Task 5).
- `EventType.CGI_TOWER` enum value matches the string `"CGI_TOWER"` used in `watchedEvents()` (Task 3) and in the spec.
