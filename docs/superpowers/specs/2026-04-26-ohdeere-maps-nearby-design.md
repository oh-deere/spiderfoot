# OhDeere Maps `/nearby` + map deep-link helper — Design

**Status:** Design (2026-04-26)
**Backlog item:** "Extend `sfp_ohdeere_maps` with `/nearby`, `/autocomplete`, `/lookup`" (BACKLOG.md). The actual `ohdeere-maps-service` exposes `/nearby` only — `/autocomplete` and `/lookup` don't exist on the gateway. This spec covers `/nearby` plus a cross-module deep-link helper to the maps web UI (B1b in the brainstorming session).
**Author:** Claude (with Ola)

## Goal

Two pieces shipped in one milestone, both backend Python:

1. **Wrap `/api/v1/nearby`** in `sfp_ohdeere_maps` so any `PHYSICAL_COORDINATES` event triggers a POI lookup. Aggressively dedupe by snapping coords to a ~1km grid so realistic OSINT scans (50-200 IPs clustered around a few hosting hotspots) collapse to a small number of unique API calls.
2. **Cross-module map-UI deep-link helper** (`spiderfoot/ohdeere_maps_url.py`). Both `sfp_ohdeere_maps` and `sfp_ohdeere_geoip` append `<SFURL>https://maps.ohdeere.se/#15/<lat>/<lon></SFURL>` to their coordinate-bearing emissions, giving the operator a one-click jump from a SpiderFoot event into the MapLibre viewer. Future modules (`sfp_ohdeere_celltower`) reuse the helper for free.

## Non-goals

- No weather endpoints (`/weather/current`, `/weather/forecast`, `/weather/air-quality`). Available on the gateway, no clear OSINT trigger today; deferrable.
- No `/autocomplete` or `/lookup` — they don't exist on the gateway.
- No cross-scan persistent `/nearby` cache (would need a DB table, YAGNI).
- No new event types — reuses existing `GEOINFO` and `RAW_RIR_DATA` to avoid touching the registry and to avoid feedback loops with `PHYSICAL_ADDRESS` (which the module already watches).
- No frontend work. Embedding MapLibre in the React SPA (B2 from brainstorming) is explicitly deferred to a future spec; the SFURL deep-link is the click-through target for now.

## Architecture

Three units, with strict separation:

### `spiderfoot/ohdeere_maps_url.py` (new)

Pure formatter, no I/O. One function:

```python
DEFAULT_BASE_URL = "https://maps.ohdeere.se"
DEFAULT_ZOOM = 15

def maps_deeplink(
    lat: float,
    lon: float,
    *,
    base_url: str = DEFAULT_BASE_URL,
    zoom: int = DEFAULT_ZOOM,
) -> str:
    """Return a MapLibre hash URL: ``{base_url}/#{zoom}/{lat}/{lon}``."""
```

The maps web UI uses `hash: true` on its MapLibre instance, so the URL hash format is the standard MapLibre `#zoom/lat/lon`. Default zoom 15 (street-level). Helper is base-URL-agnostic; consumers pass in the module opt.

No SpiderFoot imports. ~10 lines including docstring.

### `modules/sfp_ohdeere_maps.py` (modified)

New responsibilities:

- **`/nearby` request path.** When a `PHYSICAL_COORDINATES` event arrives, snap its coords to a 0.01° grid (`round(lat, 2)`, `round(lon, 2)`), check the per-instance cache. On miss: increment the unique-cells counter; if at the cap, debug-log and skip; otherwise call the API and cache the result. On hit: reuse the cached response (no extra emissions — already emitted on the original miss).
- **POI emission.** Parse the response JSON. For each POI item, build a one-line GEOINFO data string and emit it with a deep-link SFURL pointing at the POI's own `lat`/`lon`. Emit one `RAW_RIR_DATA` per response, with a deep-link SFURL pointing at the queried coord (the snapped grid cell).
- **Deep-link wiring on existing emissions.** Append `\n<SFURL>{maps_deeplink(lat, lon, base_url=opts['maps_ui_base_url'])}</SFURL>` to the data string of `PHYSICAL_ADDRESS` (from `/reverse`), `PHYSICAL_COORDINATES` (from `/geocode`), and `GEOINFO` (from both `/reverse` and `/nearby`).

### `modules/sfp_ohdeere_geoip.py` (modified)

Append the same deep-link to its `PHYSICAL_COORDINATES` emissions. Adds the `maps_ui_base_url` opt (default `https://maps.ohdeere.se`).

## `/nearby` request shape

`GET /api/v1/nearby?lat=<lat>&lon=<lon>&radius_m=<r>&limit=<n>[&category=<c>]` via `OhDeereClient.get(...)` in `maps:read` scope.

| Param | Source | Default |
|---|---|---|
| `lat` | snapped grid-cell lat | (required) |
| `lon` | snapped grid-cell lon | (required) |
| `radius_m` | `nearby_radius_m` opt | 1000 |
| `limit` | `nearby_limit` opt | 10 |
| `category` | `nearby_categories` opt (first non-empty) | omitted (= `*`) |

Returns Nominatim `jsonv2` array. Each item carries at minimum: `display_name`, `type`, `class`, `address`, `lat`, `lon`. Other fields (`importance`, `place_rank`, `osm_id`, ...) are passed through unchanged in the `RAW_RIR_DATA` event but ignored for GEOINFO formatting.

If `nearby_categories` has multiple comma-separated values, only the first is sent (Nominatim takes one query string). Multi-category queries would need multiple API calls per cell — out of scope for this milestone; user can run additional scans with different categories.

## Coordinate cache

Per-instance dict on `sfp_ohdeere_maps`:

```python
self._nearby_cells: dict[tuple[float, float], list] = {}
```

- **Key:** `(round(lat, 2), round(lon, 2))` — 0.01° ≈ 1.1km at Sweden's latitude. Same grid resolution regardless of `nearby_radius_m`. For very small radii (<500m) this slightly overshoots, for very large (>5km) it undershoots — both edge cases acceptable; the helpful default is 1km radius which matches the grid.
- **Value:** the parsed POI list from the API response. On a cache hit we don't re-emit (events were already emitted at the original miss).
- **Lifetime:** per-scan (per-instance). New scan = new module instance = empty cache. Resetting in `setup()` ensures cleanliness.

## New opts on `sfp_ohdeere_maps`

| Opt | Default | Notes |
|---|---|---|
| `nearby_radius_m` | `1000` | Search radius in meters. Maps service default. |
| `nearby_limit` | `10` | Max POIs per call. Maps service default. |
| `nearby_categories` | `""` | Comma-separated Nominatim categories (e.g. `"restaurant,cafe"`). Empty = all (gateway sends `*`). Currently only the first value is used (see "request shape" above). |
| `nearby_max_unique_cells_per_scan` | `25` | Soft cap on unique grid cells visited per scan. Mirrors the `max_emails`/`max_events` pattern in `sfp_holehe` and `sfp_ohdeere_llm_translate`. |
| `maps_ui_base_url` | `https://maps.ohdeere.se` | Used by `maps_deeplink` for SFURL append on PHYSICAL_ADDRESS / PHYSICAL_COORDINATES / GEOINFO emissions. |

## New opt on `sfp_ohdeere_geoip`

| Opt | Default | Notes |
|---|---|---|
| `maps_ui_base_url` | `https://maps.ohdeere.se` | Used to append SFURL to PHYSICAL_COORDINATES emissions. |

## Event-flow summary

```
PHYSICAL_COORDINATES event arrives at sfp_ohdeere_maps
  ↓
errorState? → return
  ↓
parse "lat,lon" from event.data; snap to grid cell (round to 0.01°)
  ↓
cell already in self._nearby_cells? → cache hit, return
  ↓
unique cells used >= nearby_max_unique_cells_per_scan? → debug-log + return
  ↓
GET /api/v1/nearby?lat=...&lon=...&radius_m=1000&limit=10
  ↓
parse JSON; cache response under cell key; increment counter
  ↓
emit one RAW_RIR_DATA (full JSON) with SFURL → cell coord
  ↓
for each POI in response:
    build GEOINFO data string: "{type}: {display_name}"
    append SFURL → POI's own (lat, lon)
    emit GEOINFO
```

GEOINFO data-string format:

```
<class>:<type> — <display_name>
<SFURL>https://maps.ohdeere.se/#15/<poi_lat>/<poi_lon></SFURL>
```

Example: `amenity:restaurant — Operakällaren, Karl XII:s Torg 1, ...\n<SFURL>https://maps.ohdeere.se/#15/59.3294/18.0719</SFURL>`. The `class:type` prefix is the Nominatim convention and gives operators a quick filter ("show me only restaurants").

For existing PHYSICAL_ADDRESS / PHYSICAL_COORDINATES / GEOINFO from `/reverse` and `/geocode`: same SFURL append, but the coords come from the original lookup result rather than a POI.

## Error contract

Mirrors the existing module:

| Failure | Behavior |
|---|---|
| `OhDeereAuthError` / `OhDeereServerError` / `OhDeereClientError` from `OhDeereClient` | `self.error(...)` + `self.errorState = True`. Module no-ops for the rest of the scan. Cache stays untouched (next scan starts fresh anyway). |
| Malformed JSON in `/nearby` response | debug-log; skip emission for that cell; do **not** trip errorState (transient gateway hiccup shouldn't kill the module). Cache the empty list under the cell so we don't retry. |
| Missing `lat`/`lon` on a POI item | debug-log; skip that POI's GEOINFO emission; continue with the next POI. The bulk RAW_RIR_DATA still goes out. |
| Module disabled (client.disabled is True) | silent no-op (existing behavior). |

## Testing

### `test/unit/spiderfoot/test_ohdeere_maps_url.py` (new, ~3 tests)

1. **Default zoom + base URL** — `maps_deeplink(59.33, 18.07)` returns `"https://maps.ohdeere.se/#15/59.33/18.07"`.
2. **Custom zoom** — `maps_deeplink(59.33, 18.07, zoom=12)` puts `12` in the right place.
3. **Custom base URL** — `maps_deeplink(59.33, 18.07, base_url="http://localhost:8080")` strips no slashes / handles trailing-slash sanely.

### `test/unit/modules/test_sfp_ohdeere_maps.py` (~6 new tests on top of existing)

1. **`/nearby` happy path** — PHYSICAL_COORDINATES → API call with snapped coords + correct opts → emits per-POI GEOINFO with SFURL pointing to POI coords + one RAW_RIR_DATA with SFURL pointing to cell coords.
2. **Cache hit** — Two PHYSICAL_COORDINATES events that snap to the same grid cell → only one API call. Second event triggers no emissions (already emitted on first).
3. **Cap honored** — `nearby_max_unique_cells_per_scan=2` + three events with three distinct cells → only the first two trigger API calls; third is debug-logged and dropped.
4. **`nearby_categories` first value forwarded** — opt set to `"restaurant,cafe"` → API URL contains `category=restaurant`.
5. **Existing emissions get the SFURL appended** — PHYSICAL_ADDRESS event from `/reverse` carries the deep-link.
6. **Malformed `/nearby` JSON** — gateway returns garbage → debug-log + cache empty list + no errorState.

### `test/unit/modules/test_sfp_ohdeere_geoip.py` (~1 new test)

1. **PHYSICAL_COORDINATES emission carries the deep-link SFURL** — patch the geoip API call, check the emitted event's data string ends with the expected SFURL.

## Distribution

- No new Python deps (uses only stdlib + existing `OhDeereClient`).
- No Dockerfile change.
- No new env vars (`maps_ui_base_url` defaults to the public host; client credentials reuse the existing OhDeere env vars).
- No new event types in `spiderfoot/db.py`.

## CLAUDE.md updates

After landing:

- Update the OhDeere integration table row for `sfp_ohdeere_maps`: add `/nearby` to the description and reflect that emissions now carry map deep-links.
- Update the row for `sfp_ohdeere_geoip` similarly (PHYSICAL_COORDINATES carries deep-link).
- Add a single sentence to the "Shared helpers" subsection mentioning `spiderfoot/ohdeere_maps_url.py`.
- Mark the BACKLOG.md "Extend `sfp_ohdeere_maps`" item as shipped.

## Out of scope (explicitly deferred)

- `/weather/*` wrappers — defer until a use case emerges.
- B2: MapLibre embed in the SPA — deferred to a separate frontend spec.
- Multi-category `/nearby` queries — would require N API calls per cell; out of scope.
- Cross-scan persistent `/nearby` cache — would need DB schema work; YAGNI.
- A consolidated "OhDeere internal-URLs" config (e.g. `OHDEERE_MAPS_UI_URL` env var) — for now the per-module opt suffices; revisit if more modules need the URL and ENV is preferable to opts.
