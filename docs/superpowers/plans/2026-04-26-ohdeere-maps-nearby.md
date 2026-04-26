# OhDeere Maps `/nearby` + Map Deep-Link Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap `/api/v1/nearby` in `sfp_ohdeere_maps` (with grid-snap dedup + soft cap) and add a tiny `maps_deeplink()` helper that both `sfp_ohdeere_maps` and `sfp_ohdeere_geoip` use to append `<SFURL>` map-UI deep-links to coordinate-bearing emissions.

**Architecture:** One new pure-formatter helper (`spiderfoot/ohdeere_maps_url.py`) consumed by two existing modules. `sfp_ohdeere_maps` gains a `_nearby` path with a `(round(lat, 2), round(lon, 2))` cell cache and per-scan unique-cells counter. Existing emissions in both modules append the SFURL via the helper. No new event types; no new Python deps; no DB changes.

**Tech Stack:** Python 3.7+, existing `OhDeereClient` for HTTP + auth, `urllib.parse` for URL building, stdlib only. SpiderFoot's normal plugin model. pytest + unittest.mock for tests.

**Spec:** `docs/superpowers/specs/2026-04-26-ohdeere-maps-nearby-design.md`

---

## File map

| File | Purpose |
|---|---|
| `spiderfoot/ohdeere_maps_url.py` (new) | Pure formatter: `maps_deeplink(lat, lon, *, base_url, zoom)`. ~15 lines. No SpiderFoot imports. |
| `test/unit/spiderfoot/test_ohdeere_maps_url.py` (new) | 3 tests for the helper. |
| `modules/sfp_ohdeere_maps.py` (modify) | Add `/nearby` path, grid cache, cap, new opts, deep-link append on existing emissions. |
| `test/unit/modules/test_sfp_ohdeere_maps.py` (modify) | Add 6 new tests. Existing tests must keep passing (their event-data assertions need updating to tolerate the appended SFURL). |
| `modules/sfp_ohdeere_geoip.py` (modify) | Add `maps_ui_base_url` opt + append SFURL to PHYSICAL_COORDINATES emission. |
| `test/unit/modules/test_sfp_ohdeere_geoip.py` (modify) | Add 1 new test; update any existing PHYSICAL_COORDINATES assertion to allow the SFURL suffix. |
| `CLAUDE.md` (modify) | Update OhDeere integration table rows + helper-list note. |
| `docs/superpowers/BACKLOG.md` (modify) | Mark `/nearby` extension item as shipped. |

---

## Task 1: Helper — `maps_deeplink`

**Files:**
- Create: `spiderfoot/ohdeere_maps_url.py`
- Create: `test/unit/spiderfoot/test_ohdeere_maps_url.py`

- [ ] **Step 1: Write the failing tests**

Create `test/unit/spiderfoot/test_ohdeere_maps_url.py`:

```python
# test_ohdeere_maps_url.py
import unittest

from spiderfoot.ohdeere_maps_url import (
    DEFAULT_BASE_URL,
    DEFAULT_ZOOM,
    maps_deeplink,
)


class TestMapsDeeplink(unittest.TestCase):

    def test_default_base_and_zoom(self):
        url = maps_deeplink(59.33, 18.07)
        self.assertEqual(url, "https://maps.ohdeere.se/#15/59.33/18.07")

    def test_custom_zoom(self):
        url = maps_deeplink(59.33, 18.07, zoom=12)
        self.assertEqual(url, "https://maps.ohdeere.se/#12/59.33/18.07")

    def test_custom_base_url_strips_trailing_slash(self):
        url = maps_deeplink(59.33, 18.07, base_url="http://localhost:8080/")
        self.assertEqual(url, "http://localhost:8080/#15/59.33/18.07")

    def test_module_constants_are_exported(self):
        self.assertEqual(DEFAULT_BASE_URL, "https://maps.ohdeere.se")
        self.assertEqual(DEFAULT_ZOOM, 15)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest test/unit/spiderfoot/test_ohdeere_maps_url.py -v`
Expected: ImportError on `spiderfoot.ohdeere_maps_url`. Red state.

- [ ] **Step 3: Implement the helper**

Create `spiderfoot/ohdeere_maps_url.py`:

```python
"""Format MapLibre hash deep-links into the OhDeere maps web UI.

The maps web UI runs MapLibre with ``hash: true``, so the URL hash is
the standard MapLibre ``#zoom/lat/lon`` format. Module-level defaults
target the public host; consumers pass ``base_url`` from a module opt
to support self-hosters and local dev.

Pure formatter — no I/O, no SpiderFoot imports.
"""

DEFAULT_BASE_URL = "https://maps.ohdeere.se"
DEFAULT_ZOOM = 15


def maps_deeplink(
    lat: float,
    lon: float,
    *,
    base_url: str = DEFAULT_BASE_URL,
    zoom: int = DEFAULT_ZOOM,
) -> str:
    """Return a MapLibre hash URL into the OhDeere maps UI.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        base_url: Base URL of the maps web UI. Trailing slash tolerated.
        zoom: MapLibre zoom level (0-20). Defaults to 15 (street-level).

    Returns:
        URL string like ``https://maps.ohdeere.se/#15/59.33/18.07``.
    """
    base = base_url.rstrip("/")
    return f"{base}/#{zoom}/{lat}/{lon}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test/unit/spiderfoot/test_ohdeere_maps_url.py -v`
Expected: 4 passed.

- [ ] **Step 5: Lint**

Run: `python3 -m flake8 spiderfoot/ohdeere_maps_url.py test/unit/spiderfoot/test_ohdeere_maps_url.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add spiderfoot/ohdeere_maps_url.py test/unit/spiderfoot/test_ohdeere_maps_url.py
git commit -m "ohdeere_maps_url: maps_deeplink() helper for SFURL deep-links"
```

---

## Task 2: Maps module — append SFURL to existing emissions

This task only touches the existing `_reverse_geocode` and `_forward_geocode` paths (already in the module). `/nearby` comes in Task 3.

**Files:**
- Modify: `modules/sfp_ohdeere_maps.py`
- Modify: `test/unit/modules/test_sfp_ohdeere_maps.py`

- [ ] **Step 1: Inspect what existing tests assert about event.data shape**

Run: `grep -n 'evt.data\|event.data\|\.data ==\|\.data,' test/unit/modules/test_sfp_ohdeere_maps.py`
Expected: Several assertions check exact data strings (e.g. `display_name == "1 Market St..."`). Note their line numbers — they need updating to tolerate the appended SFURL.

- [ ] **Step 2: Write the failing test for the SFURL append**

Append to `test/unit/modules/test_sfp_ohdeere_maps.py` (inside the existing `TestModuleOhDeereMaps` class):

```python
    def test_reverse_geocode_appends_maps_deeplink_to_address(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _REVERSE_FULL
        sf, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        addr_events = [e for e in emitted if e.eventType == "PHYSICAL_ADDRESS"]
        self.assertEqual(len(addr_events), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            addr_events[0].data,
        )

    def test_forward_geocode_appends_maps_deeplink_to_coordinates(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _FORWARD_FULL
        sf, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(
            self._event("1 Market St, San Francisco", "PHYSICAL_ADDRESS"),
        )
        coord_events = [e for e in emitted if e.eventType == "PHYSICAL_COORDINATES"]
        self.assertEqual(len(coord_events), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            coord_events[0].data,
        )
```

- [ ] **Step 3: Run to verify they fail**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py::TestModuleOhDeereMaps::test_reverse_geocode_appends_maps_deeplink_to_address test/unit/modules/test_sfp_ohdeere_maps.py::TestModuleOhDeereMaps::test_forward_geocode_appends_maps_deeplink_to_coordinates -v`
Expected: both fail (SFURL substring not found).

- [ ] **Step 4: Wire in the helper in `sfp_ohdeere_maps.py`**

Edit `modules/sfp_ohdeere_maps.py`:

a) Add the import near the top (after the `OhDeereClient` import block):

```python
from spiderfoot.ohdeere_maps_url import DEFAULT_BASE_URL, maps_deeplink
```

b) Add the new opt to `opts` and `optdescs`:

```python
    opts = {
        "maps_base_url": "https://maps.ohdeere.internal",
        "maps_ui_base_url": DEFAULT_BASE_URL,
    }

    optdescs = {
        "maps_base_url": "Base URL of the ohdeere-maps-service. Defaults to the "
                         "cluster-internal hostname; override for local testing.",
        "maps_ui_base_url": "Base URL of the maps web UI used to build SFURL "
                            "deep-links on emitted events. Defaults to the public "
                            "host; override for self-hosters.",
    }
```

c) Add a small private helper above `_emit`:

```python
    def _emit_with_link(self, source_event, event_type: str, data: str,
                       lat, lon) -> None:
        """Emit ``event_type`` with a maps-UI deep-link appended to ``data``."""
        link = maps_deeplink(
            float(lat), float(lon),
            base_url=self.opts["maps_ui_base_url"],
        )
        self._emit(source_event, event_type, f"{data}\n<SFURL>{link}</SFURL>")
```

d) In `_reverse_geocode`, change the address/geoinfo emissions to use `_emit_with_link` (the lat/lon are already parsed at the top of the method):

```python
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
            self._emit_with_link(event, "PHYSICAL_ADDRESS", display, lat, lon)

        address = payload.get("address") or {}
        country = address.get("country")
        city = address.get("city") or address.get("town") or address.get("village")
        if country:
            self._emit(event, "COUNTRY_NAME", country)
            geoinfo = f"{city}, {country}" if city else country
            self._emit_with_link(event, "GEOINFO", geoinfo, lat, lon)
```

e) In `_forward_geocode`, change the coordinate emission similarly:

```python
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
            self._emit_with_link(
                event, "PHYSICAL_COORDINATES", f"{lat},{lon}", lat, lon,
            )
```

- [ ] **Step 5: Update existing tests that asserted exact event.data strings**

In `test/unit/modules/test_sfp_ohdeere_maps.py`, find any existing test assertion of the form `self.assertEqual(evt.data, "<exact string>")` for `PHYSICAL_ADDRESS`, `GEOINFO`, or `PHYSICAL_COORDINATES` events emitted by `_reverse_geocode` or `_forward_geocode`. Change them to `self.assertIn("<exact string>", evt.data)` (the SFURL is now appended on a second line). Inspect and edit each one — typical change:

```python
# Before
self.assertEqual(addr.data, "1 Market St, San Francisco, CA, United States")
# After
self.assertIn("1 Market St, San Francisco, CA, United States", addr.data)
```

If a test asserts `COUNTRY_NAME` or `RAW_RIR_DATA` content — leave it alone (those types do NOT get the SFURL appended).

- [ ] **Step 6: Run all maps tests to confirm**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py -v`
Expected: all green (existing tests + the 2 new ones).

- [ ] **Step 7: Lint**

Run: `python3 -m flake8 modules/sfp_ohdeere_maps.py test/unit/modules/test_sfp_ohdeere_maps.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add modules/sfp_ohdeere_maps.py test/unit/modules/test_sfp_ohdeere_maps.py
git commit -m "sfp_ohdeere_maps: append SFURL deep-link to address/coord/geoinfo"
```

---

## Task 3: Maps module — `/nearby` happy path

**Files:**
- Modify: `modules/sfp_ohdeere_maps.py`
- Modify: `test/unit/modules/test_sfp_ohdeere_maps.py`

- [ ] **Step 1: Write the failing test for /nearby happy path**

Append to the maps test file:

```python
_NEARBY_RESPONSE = [
    {
        "place_id": 1,
        "lat": "37.7700",
        "lon": "-122.4200",
        "display_name": "Operakällaren, San Francisco",
        "class": "amenity",
        "type": "restaurant",
    },
    {
        "place_id": 2,
        "lat": "37.7799",
        "lon": "-122.4199",
        "display_name": "Civic Center BART Station, San Francisco",
        "class": "railway",
        "type": "station",
    },
]


    def test_nearby_emits_per_poi_geoinfo_and_one_raw_rir_data(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _NEARBY_RESPONSE
        sf, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))

        # /nearby is called once, with snapped coords (round to 0.01).
        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)
        url = nearby_calls[0].args[0]
        self.assertIn("lat=37.77", url)
        self.assertIn("lon=-122.42", url)
        self.assertIn("radius_m=1000", url)
        self.assertIn("limit=10", url)

        # One GEOINFO per POI with the per-POI deep-link.
        geos = [e for e in emitted if e.eventType == "GEOINFO"
                and "Operakällaren" in e.data]
        self.assertEqual(len(geos), 1)
        self.assertIn("amenity:restaurant", geos[0].data)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            geos[0].data,
        )

        # One RAW_RIR_DATA from /nearby (in addition to the /reverse one)
        # carrying the cell deep-link.
        nearby_raws = [e for e in emitted if e.eventType == "RAW_RIR_DATA"
                       and "Operakällaren" in e.data]
        self.assertEqual(len(nearby_raws), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            nearby_raws[0].data,
        )
```

(Note: `_NEARBY_RESPONSE` is a module-level constant — add it near the top with the other `_REVERSE_FULL`/`_FORWARD_FULL` constants. The new test method goes inside `TestModuleOhDeereMaps`.)

- [ ] **Step 2: Verify red state**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py::TestModuleOhDeereMaps::test_nearby_emits_per_poi_geoinfo_and_one_raw_rir_data -v`
Expected: failure — no `/nearby` call happens (only `/reverse`), GEOINFO assertion fails.

- [ ] **Step 3: Implement /nearby in `sfp_ohdeere_maps.py`**

a) Extend `opts` and `optdescs` with the four new `nearby_*` opts:

```python
    opts = {
        "maps_base_url": "https://maps.ohdeere.internal",
        "maps_ui_base_url": DEFAULT_BASE_URL,
        "nearby_radius_m": 1000,
        "nearby_limit": 10,
        "nearby_categories": "",
        "nearby_max_unique_cells_per_scan": 25,
    }

    optdescs = {
        "maps_base_url": "Base URL of the ohdeere-maps-service. Defaults to the "
                         "cluster-internal hostname; override for local testing.",
        "maps_ui_base_url": "Base URL of the maps web UI used to build SFURL "
                            "deep-links on emitted events. Defaults to the public "
                            "host; override for self-hosters.",
        "nearby_radius_m": "Search radius in meters for /nearby POI lookup "
                           "(default 1000).",
        "nearby_limit": "Max POIs returned per /nearby call (default 10).",
        "nearby_categories": "Comma-separated Nominatim categories (e.g. "
                             "'restaurant,cafe'). Empty = all. Currently only the "
                             "first value is sent per call.",
        "nearby_max_unique_cells_per_scan": "Soft cap on unique grid cells (~1km "
                                            "each) probed per scan (default 25).",
    }
```

b) Initialize the cache + counter in `setup`:

```python
    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._seen: set[str] = set()
        self._nearby_cells: dict[tuple[float, float], list] = {}
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]
```

c) In `handleEvent`, after `_reverse_geocode`, also call the new `_nearby` for `PHYSICAL_COORDINATES` events. Replace the existing branch:

```python
        if event.eventType == "PHYSICAL_COORDINATES":
            self._reverse_geocode(event)
            self._nearby(event)
        elif event.eventType == "PHYSICAL_ADDRESS":
            self._forward_geocode(event)
```

d) Add the `_nearby` method (place it after `_forward_geocode`):

```python
    def _nearby(self, event):
        lat, lon = self._parse_coords(event.data)
        if lat is None:
            return
        cell = (round(lat, 2), round(lon, 2))
        if cell in self._nearby_cells:
            return  # already emitted at first miss; nothing more to do.

        cap = int(self.opts["nearby_max_unique_cells_per_scan"])
        if len(self._nearby_cells) >= cap:
            self.debug(
                f"hit nearby_max_unique_cells_per_scan={cap}; "
                f"skipping cell {cell}"
            )
            return

        params = {
            "lat": cell[0],
            "lon": cell[1],
            "radius_m": int(self.opts["nearby_radius_m"]),
            "limit": int(self.opts["nearby_limit"]),
        }
        category = next(
            (c.strip() for c in self.opts["nearby_categories"].split(",")
             if c.strip()),
            None,
        )
        if category:
            params["category"] = category
        url = f"/api/v1/nearby?{urllib.parse.urlencode(params)}"
        payload = self._call(url)
        # Cache the response (or empty list on bad data) so we don't retry.
        items = payload if isinstance(payload, list) else []
        self._nearby_cells[cell] = items

        # One RAW_RIR_DATA for the whole response, with cell deep-link.
        self._emit_with_link(
            event, "RAW_RIR_DATA", json.dumps(items), cell[0], cell[1],
        )

        # One GEOINFO per POI with its own deep-link.
        for item in items:
            poi_lat = item.get("lat")
            poi_lon = item.get("lon")
            display = item.get("display_name")
            if poi_lat is None or poi_lon is None or not display:
                self.debug(f"skipping malformed POI: {item}")
                continue
            klass = item.get("class") or "?"
            ptype = item.get("type") or "?"
            data = f"{klass}:{ptype} — {display}"
            self._emit_with_link(event, "GEOINFO", data, poi_lat, poi_lon)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py -v`
Expected: all green including the new `test_nearby_emits_per_poi_geoinfo_and_one_raw_rir_data`.

- [ ] **Step 5: Lint**

Run: `python3 -m flake8 modules/sfp_ohdeere_maps.py test/unit/modules/test_sfp_ohdeere_maps.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add modules/sfp_ohdeere_maps.py test/unit/modules/test_sfp_ohdeere_maps.py
git commit -m "sfp_ohdeere_maps: wrap /nearby with per-POI GEOINFO emissions"
```

---

## Task 4: Maps module — cache hit + per-scan cap

**Files:**
- Modify: `test/unit/modules/test_sfp_ohdeere_maps.py`

(No source change needed; the cache + cap logic was implemented in Task 3. This task adds the tests that lock the behavior.)

- [ ] **Step 1: Add the cache + cap tests**

Append to `TestModuleOhDeereMaps`:

```python
    def test_nearby_cache_hit_skips_second_api_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _NEARBY_RESPONSE
        sf, module = self._module(client)
        module.notifyListeners = lambda evt: None

        # Two events that snap to the same 0.01° cell.
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        # Different ".data" string so _seen doesn't dedupe; still rounds to (37.77, -122.42).
        module.handleEvent(self._event("37.7704,-122.4203", "PHYSICAL_COORDINATES"))

        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)

    def test_nearby_cap_drops_after_threshold(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _NEARBY_RESPONSE
        sf, module = self._module(client)
        module.opts["nearby_max_unique_cells_per_scan"] = 2
        module.notifyListeners = lambda evt: None

        # Three events in three distinct cells.
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))
        module.handleEvent(self._event("40.71,-74.00", "PHYSICAL_COORDINATES"))
        module.handleEvent(self._event("51.50,-0.12", "PHYSICAL_COORDINATES"))

        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 2)
```

- [ ] **Step 2: Run them**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py::TestModuleOhDeereMaps::test_nearby_cache_hit_skips_second_api_call test/unit/modules/test_sfp_ohdeere_maps.py::TestModuleOhDeereMaps::test_nearby_cap_drops_after_threshold -v`
Expected: both pass on first run (logic was implemented in Task 3).

If either fails: re-read Task 3 step 3.d — most likely `cell in self._nearby_cells` check (cache hit) or `len(...) >= cap` check (cap) is wrong.

- [ ] **Step 3: Commit**

```bash
git add test/unit/modules/test_sfp_ohdeere_maps.py
git commit -m "test: lock /nearby cache hit + per-scan cell cap"
```

---

## Task 5: Maps module — `nearby_categories` opt + malformed JSON

**Files:**
- Modify: `test/unit/modules/test_sfp_ohdeere_maps.py`

(No source change — Task 3's `_nearby` already handles both. This task adds the lock-in tests.)

- [ ] **Step 1: Add the tests**

Append to `TestModuleOhDeereMaps`:

```python
    def test_nearby_categories_first_value_forwarded(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = []
        sf, module = self._module(client)
        module.opts["nearby_categories"] = "restaurant, cafe"
        module.notifyListeners = lambda evt: None
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))

        nearby_calls = [c for c in client.get.call_args_list
                        if "/nearby" in c.args[0]]
        self.assertEqual(len(nearby_calls), 1)
        self.assertIn("category=restaurant", nearby_calls[0].args[0])

    def test_nearby_malformed_response_does_not_trip_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        # Gateway returns a dict instead of a list (malformed).
        client.get.return_value = {"unexpected": "shape"}
        sf, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        module.handleEvent(self._event("37.77,-122.42", "PHYSICAL_COORDINATES"))

        self.assertFalse(module.errorState)
        # No GEOINFO from /nearby, but RAW_RIR_DATA still goes out (empty list).
        nearby_geos = [e for e in emitted if e.eventType == "GEOINFO"
                       and "—" in e.data]  # POI GEOINFO has the em-dash separator.
        self.assertEqual(nearby_geos, [])
```

- [ ] **Step 2: Run**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_maps.py::TestModuleOhDeereMaps::test_nearby_categories_first_value_forwarded test/unit/modules/test_sfp_ohdeere_maps.py::TestModuleOhDeereMaps::test_nearby_malformed_response_does_not_trip_errorstate -v`
Expected: both pass.

- [ ] **Step 3: Lint**

Run: `python3 -m flake8 modules/sfp_ohdeere_maps.py test/unit/modules/test_sfp_ohdeere_maps.py`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add test/unit/modules/test_sfp_ohdeere_maps.py
git commit -m "test: lock nearby_categories + malformed-response handling"
```

---

## Task 6: Geoip module — append SFURL to PHYSICAL_COORDINATES

**Files:**
- Modify: `modules/sfp_ohdeere_geoip.py`
- Modify: `test/unit/modules/test_sfp_ohdeere_geoip.py`

- [ ] **Step 1: Inspect existing geoip test for the PHYSICAL_COORDINATES assertion**

Run: `grep -n 'PHYSICAL_COORDINATES' test/unit/modules/test_sfp_ohdeere_geoip.py`
Expected: at least one assertion checking the data string. Note the line so you can update it in step 4.

- [ ] **Step 2: Write the failing test for the SFURL append**

Append to the geoip test file's main test class (find the `class TestModuleOhDeereGeoip(...)` block):

```python
    def test_physical_coordinates_carries_maps_deeplink(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = {
            "country": {"name": "United States"},
            "city": {"name": "San Francisco"},
            "location": {"lat": 37.77, "lon": -122.42},
            "asn": {"org": "Cloudflare"},
        }
        sf, module = self._module(client)
        emitted = []
        module.notifyListeners = lambda evt: emitted.append(evt)
        root = SpiderFootEvent("ROOT", "1.1.1.1", "", "")
        module.handleEvent(SpiderFootEvent("IP_ADDRESS", "1.1.1.1",
                                           "test_mod", root))
        coord_events = [e for e in emitted
                        if e.eventType == "PHYSICAL_COORDINATES"]
        self.assertEqual(len(coord_events), 1)
        self.assertIn(
            "<SFURL>https://maps.ohdeere.se/#15/37.77/-122.42</SFURL>",
            coord_events[0].data,
        )
```

- [ ] **Step 3: Verify red**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_geoip.py::TestModuleOhDeereGeoip::test_physical_coordinates_carries_maps_deeplink -v`
Expected: failure (SFURL substring not present).

- [ ] **Step 4: Wire the helper into `sfp_ohdeere_geoip.py`**

a) Add the import block near the top:

```python
from spiderfoot.ohdeere_maps_url import DEFAULT_BASE_URL, maps_deeplink
```

b) Add the `maps_ui_base_url` opt:

```python
    opts = {
        "geoip_base_url": "https://geoip.ohdeere.internal",
        "maps_ui_base_url": DEFAULT_BASE_URL,
    }
```

(If the existing `opts` block has more keys, preserve them — only the additions matter.)

c) Add the matching `optdescs` entry:

```python
    optdescs = {
        "geoip_base_url": "Base URL of the ohdeere-geoip-service.",
        "maps_ui_base_url": "Base URL of the maps web UI used to append SFURL "
                            "deep-links to PHYSICAL_COORDINATES events. Defaults "
                            "to the public host.",
    }
```

(Same: preserve existing keys.)

d) In `handleEvent`, change the PHYSICAL_COORDINATES emission. Find this block:

```python
        if lat is not None and lon is not None:
            self._emit(event, "PHYSICAL_COORDINATES", f"{lat},{lon}")
```

Replace with:

```python
        if lat is not None and lon is not None:
            link = maps_deeplink(
                float(lat), float(lon),
                base_url=self.opts["maps_ui_base_url"],
            )
            self._emit(
                event,
                "PHYSICAL_COORDINATES",
                f"{lat},{lon}\n<SFURL>{link}</SFURL>",
            )
```

- [ ] **Step 5: Update any pre-existing geoip test that asserts an exact PHYSICAL_COORDINATES string**

Find any existing assertion like `self.assertEqual(<...>.data, "<lat>,<lon>")` for `PHYSICAL_COORDINATES` and change `assertEqual` → `assertIn` with the lat/lon-only substring (the SFURL is now appended). Example:

```python
# Before
self.assertEqual(coord.data, "37.77,-122.42")
# After
self.assertIn("37.77,-122.42", coord.data)
```

Leave assertions for other event types (`COUNTRY_NAME`, `GEOINFO`, etc.) alone — they don't get the SFURL.

- [ ] **Step 6: Run the geoip tests**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_geoip.py -v`
Expected: all green.

- [ ] **Step 7: Lint**

Run: `python3 -m flake8 modules/sfp_ohdeere_geoip.py test/unit/modules/test_sfp_ohdeere_geoip.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add modules/sfp_ohdeere_geoip.py test/unit/modules/test_sfp_ohdeere_geoip.py
git commit -m "sfp_ohdeere_geoip: append SFURL deep-link to PHYSICAL_COORDINATES"
```

---

## Task 7: Smoke-check both modules + full lint + test

**Files:** none — verification only.

- [ ] **Step 1: Loader smoke for both modules**

Run:

```bash
python3 -c "
from spiderfoot import SpiderFootHelpers
mods = SpiderFootHelpers.loadModulesAsDict('modules', ['sfp__stor_db.py', 'sfp__stor_stdout.py'])
for name in ('sfp_ohdeere_maps', 'sfp_ohdeere_geoip'):
    m = mods[name]
    print(f'{name}: opts={sorted(m[\"opts\"].keys())}')
"
```

Expected: both modules load. Verify `maps_ui_base_url` appears in both opts lists. Verify `nearby_radius_m`, `nearby_limit`, `nearby_categories`, `nearby_max_unique_cells_per_scan` appear in `sfp_ohdeere_maps` opts.

- [ ] **Step 2: Repo-wide lint**

Run: `python3 -m flake8 . --count`
Expected: `0`.

- [ ] **Step 3: Run touched + neighboring tests**

Run:

```bash
python3 -m pytest \
  test/unit/spiderfoot/test_ohdeere_maps_url.py \
  test/unit/modules/test_sfp_ohdeere_maps.py \
  test/unit/modules/test_sfp_ohdeere_geoip.py \
  test/unit/spiderfoot/test_ohdeere_client.py \
  test/unit/spiderfoot/test_ohdeere_llm.py \
  -q --no-cov
```

Expected: all green. Total ≈ 30+ tests (4 helper + ~12 maps + ~10 geoip + ohdeere_client + ohdeere_llm).

- [ ] **Step 4: No commit** — verification only.

---

## Task 8: Docs — CLAUDE.md + BACKLOG.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/BACKLOG.md`

- [ ] **Step 1: Update CLAUDE.md OhDeere integration table**

In `CLAUDE.md`, find the `Consumer modules (all FREE_NOAUTH_UNLIMITED ...)` table.

Change the `sfp_ohdeere_maps` row's "Watches → Emits" description to add `/nearby`:

```
| `sfp_ohdeere_maps` | `maps:read` | `PHYSICAL_COORDINATES` (reverse-geocode + /nearby POI lookup), `PHYSICAL_ADDRESS` (forward-geocode) → `PHYSICAL_ADDRESS`, `PHYSICAL_COORDINATES`, `COUNTRY_NAME`, `GEOINFO`, `RAW_RIR_DATA`. All emissions carry SFURL deep-links into the maps web UI. |
```

Change the `sfp_ohdeere_geoip` row to mention the deep-link suffix:

```
| `sfp_ohdeere_geoip` | `geoip:read` | `IP_ADDRESS`, `IPV6_ADDRESS` → `COUNTRY_NAME`, `GEOINFO`, `PHYSICAL_COORDINATES` (with SFURL map deep-link), `BGP_AS_OWNER`, `RAW_RIR_DATA` |
```

- [ ] **Step 2: Add a one-line note to the Shared helpers subsection**

Find the `**Shared helpers:**` block (around `spiderfoot/ohdeere_client.py` / `ohdeere_llm.py` / `ohdeere_vision.py`) and append:

```
- `spiderfoot/ohdeere_maps_url.py` — pure formatter for MapLibre hash deep-links into the OhDeere maps web UI. `maps_deeplink(lat, lon, *, base_url, zoom)` returns `https://maps.ohdeere.se/#<zoom>/<lat>/<lon>`. Used by `sfp_ohdeere_maps` and `sfp_ohdeere_geoip` to attach `<SFURL>` to coordinate-bearing events; future `sfp_ohdeere_celltower` reuses it directly.
```

- [ ] **Step 3: Update BACKLOG.md**

Find the "Extend `sfp_ohdeere_maps` with `/nearby`, `/autocomplete`, `/lookup`" section. Replace it with a shipped note matching the format used for the Postgres / pybreaker entries:

```
### Extend `sfp_ohdeere_maps` (`/nearby` + map deep-links) — shipped 2026-04-26
- `/nearby` POI lookup wrapped, with grid-snap (~1km) coordinate cache and `nearby_max_unique_cells_per_scan=25` soft cap.
- New helper `spiderfoot/ohdeere_maps_url.py` exports `maps_deeplink()`; both `sfp_ohdeere_maps` and `sfp_ohdeere_geoip` append SFURL deep-links to coordinate-bearing emissions.
- `/autocomplete` and `/lookup` were never on the maps gateway; spec dropped them.
- Spec: `docs/superpowers/specs/2026-04-26-ohdeere-maps-nearby-design.md`.
- Plan: `docs/superpowers/plans/2026-04-26-ohdeere-maps-nearby.md`.
```

Also find any "priority table" row referencing this item (matching the `~~Done~~` pattern used for Postgres/pybreaker/holehe) and add or update accordingly. If no such row exists, skip — the section header above is the authoritative status.

- [ ] **Step 4: Verify**

Run: `grep -c 'maps_deeplink\|ohdeere_maps_url' CLAUDE.md`
Expected: at least `1`.

Run: `grep -A 1 'Extend .sfp_ohdeere_maps' docs/superpowers/BACKLOG.md | head -3`
Expected: the new "shipped 2026-04-26" line.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "docs: CLAUDE.md + BACKLOG.md — maps /nearby + deep-link helper shipped"
```

---

## Task 9: Final verify

**Files:** none — verification only.

- [ ] **Step 1: Show the commit chain**

Run: `git log --oneline -10`
Expected: ~7 new commits — helper, maps SFURL, maps /nearby, cache+cap tests, categories/malformed tests, geoip SFURL, docs.

- [ ] **Step 2: Run the focused unit suite one more time**

Run:

```bash
python3 -m pytest \
  test/unit/spiderfoot/test_ohdeere_maps_url.py \
  test/unit/modules/test_sfp_ohdeere_maps.py \
  test/unit/modules/test_sfp_ohdeere_geoip.py \
  -q --no-cov
```
Expected: all green.

- [ ] **Step 3: Done.** Report the commit list and any notes.

---

## Self-review

**Spec coverage:** Spec section-by-section.

- "Architecture / three units" → Tasks 1, 2-5, 6 each touch one unit; Task 1 builds the helper first.
- "`/nearby` request shape" — Task 3 step 3.d builds the URL exactly per spec (lat, lon, radius_m, limit, optional category).
- "Coordinate cache" — Task 3 sets up the dict in `setup`; Task 4 tests the hit + cap behavior.
- "New opts on `sfp_ohdeere_maps`" — Task 3 step 3.a lists all five new opts (including the four `nearby_*` plus `maps_ui_base_url`); Task 2 introduces `maps_ui_base_url`.
- "New opt on `sfp_ohdeere_geoip`" — Task 6 step 4.b adds `maps_ui_base_url`.
- "Event-flow summary" — Task 3 step 3.d implements; Task 3 step 1 tests the per-POI GEOINFO + RAW_RIR_DATA emission.
- "Error contract" — JSON parse failure → cache empty list, no errorState (Task 5 second test). Auth/server/client errors keep existing `_call` behavior unchanged. Disabled client → existing no-op (untouched).
- "Testing" — every test from the spec maps to a step.
- "Out of scope" — no weather, no /autocomplete, no multi-category. None added.

**Placeholder scan:** No "TBD"/"TODO"/"add validation". Every code block is complete; every shell command has expected output.

**Type consistency:**
- `maps_deeplink(lat, lon, *, base_url=DEFAULT_BASE_URL, zoom=DEFAULT_ZOOM)` defined in Task 1; called identically in Tasks 2 (via `_emit_with_link`) and 6 (inline).
- `_emit_with_link(self, source_event, event_type, data, lat, lon)` defined in Task 2 step 4.c; reused in Task 3 step 3.d for `/nearby` GEOINFO + RAW_RIR_DATA emissions.
- `self._nearby_cells: dict[tuple[float, float], list]` — declared in Task 3 step 3.b; referenced consistently.
- Opt names — `maps_ui_base_url`, `nearby_radius_m`, `nearby_limit`, `nearby_categories`, `nearby_max_unique_cells_per_scan` — match between source (Task 3 step 3.a), tests (Task 4, 5), spec, and CLAUDE.md (Task 8).
- The cap message format `"hit nearby_max_unique_cells_per_scan={cap}; skipping cell {cell}"` is internal logging; no test asserts its text.
