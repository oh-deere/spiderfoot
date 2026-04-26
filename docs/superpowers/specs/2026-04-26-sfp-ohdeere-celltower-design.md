# `sfp_ohdeere_celltower` — Cell-tower lookups via OpenCellID

**Status:** Design (2026-04-26)
**Backlog item:** "`sfp_ohdeere_celltower` (parked — no event fit)" (BACKLOG.md). Path C unblocks both directions: trigger on `PHYSICAL_COORDINATES` for nearby-tower lookup, **and** introduce a new `CGI_TOWER` event type so producers (now or future) can hand the module an explicit MCC/MNC/LAC/CID tuple to resolve.
**Author:** Claude (with Ola)

## Goal

Wrap the `ohdeere-celltower-service` (Spring Boot wrapper around OpenCellID) as a SpiderFoot module that does two things:

1. **Path A — coordinate-driven nearby lookup.** When a `PHYSICAL_COORDINATES` event fires (e.g. from `sfp_ohdeere_geoip`), call `/api/v1/cgi/nearby` and emit one `GEOINFO` per nearby tower (with a clickable map deep-link) plus a bulk `RAW_RIR_DATA`. Same per-instance grid-snap cache + per-scan cap as `sfp_ohdeere_maps`.
2. **Path B — CGI-driven resolve.** Introduce a new `CGI_TOWER` event type carrying `"MCC,MNC,LAC,CID"`. When such an event arrives, call `/api/v1/cgi/{mcc}/{mnc}/{lac}/{cid}` to resolve to a single tower record and emit `PHYSICAL_COORDINATES` (with deep-link) + `GEOINFO` + `RAW_RIR_DATA`.

Path B has no producers in-tree today. It exists so future modules — leaked-CDR parsers, IoT device dumps, IMSI-catcher logs — can plug in without further plumbing. It also enables the `Path B → emits PHYSICAL_COORDINATES → triggers Path A on the same module + sfp_ohdeere_maps reverse/nearby` cascade, which is the OSINT-useful "given a CGI, what does the area around it look like" flow.

## Non-goals

- No batch lookup (the gateway doesn't expose one; nearby-by-coord covers the bulk case).
- No tower density / signal-strength heatmap aggregation. Single-event emissions only.
- No carrier (MNO) name resolution from MCC+MNC. The OpenCellID record has the codes but not the operator name; that's a separate dataset / endpoint.
- No new dependencies.
- No Dockerfile change.
- No CGI_TOWER producer module — pure consumer for now. The spec note in CLAUDE.md flags the new event type as available for producers.

## Architecture

Single new module + a small entry in the event-type registry. Mirrors the shape of `sfp_ohdeere_maps` (grid-cached `_nearby` path) plus a parallel `_resolve` path. Reuses the deep-link helper.

```
spiderfoot/event_types.py
   ├─ +EventType.CGI_TOWER
   └─ +EVENT_TYPES[EventType.CGI_TOWER] = EventTypeDef(...)

modules/sfp_ohdeere_celltower.py     (new)
   ├─ handleEvent(PHYSICAL_COORDINATES) → _nearby   (Path A)
   ├─ handleEvent(CGI_TOWER)           → _resolve  (Path B)
   ├─ _nearby_cells: dict[(rlat, rlon), list]    grid-snap cache
   ├─ _seen_cgi: set[str]                        Path B input dedup
   └─ uses spiderfoot.ohdeere_maps_url.maps_deeplink for SFURLs
```

The grid cache + per-scan cap parameters and pattern are copy-paste from `sfp_ohdeere_maps`. Cap is 25 unique cells per scan; grid is `round(lat, 2)` + `round(lon, 2)` (~1km).

## Event-type registry change

Add to `spiderfoot/event_types.py`:

```python
class EventType(str, enum.Enum):
    ...
    CGI_TOWER = "CGI_TOWER"
    ...

EVENT_TYPES = {
    ...
    EventType.CGI_TOWER: EventTypeDef(
        "CGI_TOWER", "Cell Tower (CGI)",
        EventTypeCategory.ENTITY, is_raw=False,
    ),
    ...
}
```

Invariant test counts in `test/unit/spiderfoot/test_event_types.py` need bumping:
- Total `len(EVENT_TYPES)`: **172 → 173**
- `EventTypeCategory.ENTITY`: **57 → 58**

Other category counts unchanged. The existing invariant tests (enum/dict drift, key types) catch any accidental mistake.

## CGI string format

The `CGI_TOWER` event data is a comma-separated string of four decimal integers in URL-path order:

```
"MCC,MNC,LAC,CID"
```

Example: `"240,1,12345,67890"`. Parsed with `s.split(",")` → 4 ints. No leading/trailing whitespace tolerated; no zero-padding required.

This format mirrors how `PHYSICAL_COORDINATES` already encodes lat/lon as `"lat,lon"` — same convention, different cardinality. Producer modules emit the string verbatim; consumers split on comma.

## Module shape

```python
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
                           "OhDeere client-credentials token (OHDEERE_CLIENT_ID "
                           "/ OHDEERE_CLIENT_SECRET env vars) with "
                           "celltower:read scope.",
        },
    }

    opts = {
        "celltower_base_url": "https://celltower.ohdeere.internal",
        "maps_ui_base_url": "https://maps.ohdeere.se",
        "nearby_radius_m": 5000,
        "nearby_limit": 10,
        "nearby_max_unique_cells_per_scan": 25,
    }
```

Defaults differ from the maps module: `nearby_radius_m=5000` (cell coverage is kilometre-scale; 1km is too tight). Other opts mirror maps.

## Path A — nearby lookup

```
PHYSICAL_COORDINATES event
  ↓
parse "lat,lon" (strip any SFURL appended by upstream emitter)
  ↓
snap to (round(lat, 2), round(lon, 2))
  ↓
cache hit → return (already emitted on first miss)
  ↓
cap reached → debug log + return
  ↓
GET /api/v1/cgi/nearby?lat=...&lon=...&radius_m=...&limit=...
  ↓
cache response under cell key
  ↓
emit one RAW_RIR_DATA (full JSON) with SFURL → cell coord
  ↓
for each tower:
    build GEOINFO data:
      "Cell tower [{radio}] {mcc}/{mnc}/{lac}/{cid} — range ~{rangeM}m"
    append SFURL → tower's own (lat, lon)
    emit GEOINFO
```

The PHYSICAL_COORDINATES data parsing must tolerate the `\n<SFURL>...</SFURL>` suffix that `sfp_ohdeere_maps` and `sfp_ohdeere_geoip` now append — split on first newline before parsing.

## Path B — CGI resolve

```
CGI_TOWER event
  ↓
input dedup via self._seen_cgi
  ↓
parse "MCC,MNC,LAC,CID" → 4 ints (malformed → debug log + return)
  ↓
GET /api/v1/cgi/{mcc}/{mnc}/{lac}/{cid}
  ↓
404 → debug log + return (no errorState; unknown tower is a normal outcome)
  ↓
parse Cell record (mcc, mnc, lac, cid, radio, lat, lon, rangeM, ...)
  ↓
emit RAW_RIR_DATA (full JSON)
emit PHYSICAL_COORDINATES "lat,lon\n<SFURL>...</SFURL>"
emit GEOINFO "Cell tower [radio] mcc/mnc/lac/cid — range ~rangeM m\n<SFURL>...</SFURL>"
```

The emitted `PHYSICAL_COORDINATES` will be picked up by `sfp_ohdeere_maps` (reverse-geocode + maps `/nearby`) and by *this same module's* `_nearby` path. The grid cache short-circuits the self-recursion so it's at most one extra `/cgi/nearby` call per resolved CGI. Acceptable.

## Output format details

**GEOINFO from nearby (per tower):**
```
Cell tower [GSM] 240/1/12345/67890 — range ~1500m
<SFURL>https://maps.ohdeere.se/#15/59.33/18.07</SFURL>
```

**GEOINFO from resolve:** same shape as above; `(lat, lon)` is the resolved tower's exact position.

**PHYSICAL_COORDINATES from resolve:** standard `"lat,lon\n<SFURL>...</SFURL>"` matching the convention `sfp_ohdeere_geoip` and `sfp_ohdeere_maps` already use.

**RAW_RIR_DATA:** `json.dumps(payload, ensure_ascii=False)` — full response. Carries SFURL pointing to the queried/cell coord (Path A) or the resolved tower (Path B).

## Error contract

| Failure | Behavior |
|---|---|
| `OhDeereAuthError` / `OhDeereServerError` / `OhDeereClientError` | `self.error(...)` + `errorState = True` (matches existing OhDeere modules) |
| 404 from `/cgi/{...}` (unknown CGI) | debug-log; no emission; **no errorState** — unknown towers are normal |
| Malformed JSON from gateway | debug-log; cache empty list under the cell (Path A) or skip (Path B); no errorState |
| Malformed `CGI_TOWER` input string | debug-log; skip; no errorState |
| Module disabled (`client.disabled is True`) | silent no-op |

## Testing

`test/unit/spiderfoot/test_event_types.py` — bump the count assertions (172→173, ENTITY 57→58). The existing invariant tests catch any drift between the enum and the dict.

`test/unit/modules/test_sfp_ohdeere_celltower.py` (~10 tests):

1. opts/optdescs key parity
2. `watchedEvents` returns `["PHYSICAL_COORDINATES", "CGI_TOWER"]`; `producedEvents` returns `["GEOINFO", "RAW_RIR_DATA", "PHYSICAL_COORDINATES"]`
3. **Path A happy path** — PHYSICAL_COORDINATES → API call with snapped coords + correct opts → emits per-tower GEOINFO with deep-link + bulk RAW_RIR_DATA
4. **Path A handles SFURL suffix in coord data** — PHYSICAL_COORDINATES data is `"37.77,-122.42\n<SFURL>...</SFURL>"`; parser strips correctly and call goes through
5. **Path A cache hit** — two coords snapping to same cell → only one API call
6. **Path A cap honored** — `nearby_max_unique_cells_per_scan=2` + three distinct cells → only two API calls
7. **Path B happy path** — CGI_TOWER `"240,1,12345,67890"` → `GET /api/v1/cgi/240/1/12345/67890` → emits PHYSICAL_COORDINATES + GEOINFO + RAW_RIR_DATA with expected formatting and SFURL
8. **Path B 404** — gateway returns None / empty → debug-log + no emissions + no errorState
9. **Path B malformed CGI string** — `"not,a,cgi"` or `"240,1,12345"` → debug-log + no emissions + no errorState
10. **Auth error trips errorState** — first call raises OhDeereAuthError → errorState True; second event short-circuits

## CLAUDE.md / BACKLOG.md updates

After landing:

- CLAUDE.md FREE_NOAUTH_UNLIMITED list: add `sfp_ohdeere_celltower` (alphabetical position, between `sfp_ohdeere_search` and `sfp_ohdeere_wiki` after the existing OhDeere set). Bump count 97→98 and surviving-modules count 187→188.
- CLAUDE.md OhDeere consumer-modules table: add a new row for `sfp_ohdeere_celltower` with scope `celltower:read`, watches `PHYSICAL_COORDINATES`+`CGI_TOWER`, emits `GEOINFO`/`RAW_RIR_DATA`/`PHYSICAL_COORDINATES`, with a one-line note about Path A nearby + Path B resolve.
- CLAUDE.md "Shared helpers" / event-type note: add a brief note that `CGI_TOWER` is a new entity-category event type (`spiderfoot/event_types.py`) with no in-tree producers yet — available for future leaked-CDR / IoT-dump parsers.
- BACKLOG.md: change "Parked" status of `sfp_ohdeere_celltower` to "shipped 2026-04-26" with a 1-2-line summary mirroring the Postgres / pybreaker shipped-entry format. Update the priority table row from "Parked" to "Done".

## Out of scope (explicitly deferred)

- MNO/operator name resolution from MCC+MNC (separate dataset).
- Batch resolve (gateway doesn't expose one; not worth a module-level batcher).
- An `sfp_ohdeere_celltower_input` parser that produces `CGI_TOWER` events from breach dumps. Future work; new event type is the unblock that lets such a module land cleanly.
- Persistent cross-scan cache. Per-scan grid cache is enough for realistic OSINT scans.
- A separate `CGI_TOWER` data-format helper (`spiderfoot/cgi_tower.py`). The parse/format logic is 5 lines; inline in the module is fine. Revisit if a second consumer appears.
