# `sfp_ohdeere_maps` — forward + reverse geocoding module

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Add a second consumer of `spiderfoot/ohdeere_client.py`: `modules/sfp_ohdeere_maps.py` wraps the self-hosted `ohdeere-maps-service`'s Nominatim-backed place index. Provides two-way geocoding:

- `PHYSICAL_COORDINATES` event → reverse-geocode via `/api/v1/reverse` → emit `PHYSICAL_ADDRESS` + `COUNTRY_NAME` + `GEOINFO` + `RAW_RIR_DATA`.
- `PHYSICAL_ADDRESS` event → forward-geocode via `/api/v1/geocode` → emit `PHYSICAL_COORDINATES` + `RAW_RIR_DATA`.

This is new capability — no surviving SpiderFoot module does forward or reverse geocoding. Closes the "address ↔ coordinates" loop so chains like `IP_ADDRESS → (geoip) PHYSICAL_COORDINATES → (maps) PHYSICAL_ADDRESS` work end-to-end.

## Non-goals

- **Not** wrapping `/api/v1/nearby` (POI search). High-value OSINT capability ("what businesses are at this physical address") but different event-type decision (new `NEARBY_POI` type, or reuse `PHYSICAL_ADDRESS`?); deferred to backlog task #40.
- **Not** wrapping `/api/v1/autocomplete` (typeahead UX — not scan-useful).
- **Not** wrapping `/api/v1/lookup` (OSM ID re-fetch — niche).
- **Not** wrapping `/api/v1/weather/*` (marginal OSINT fit).
- **Not** using `/api/v1/geocode/structured`. Forward geocode uses the freeform `q=<address>` endpoint. Structured fields would require parsing addresses upstream, which is complexity for marginal gain.
- **Not** emitting top-N forward results. `limit=1`; if a follow-up shows value, a `max_results` opt is a one-line add.
- **Not** modifying `spiderfoot/ohdeere_client.py`. The helper is done.

## Design

### Module shape

One new file `modules/sfp_ohdeere_maps.py` (~200 lines). Standard `SpiderFootPlugin` with class-level `meta` / `opts` / `optdescs`. Uses the shared `get_client()` singleton from `spiderfoot/ohdeere_client.py` with scope `maps:read`.

**Watched events:** `["PHYSICAL_COORDINATES", "PHYSICAL_ADDRESS"]`.

**Produced events:** `["PHYSICAL_ADDRESS", "PHYSICAL_COORDINATES", "COUNTRY_NAME", "GEOINFO", "RAW_RIR_DATA"]`.

**Opts:**

```python
opts = {"maps_base_url": "https://maps.ohdeere.internal"}
optdescs = {"maps_base_url": "Base URL of the ohdeere-maps-service. Defaults to the "
                             "cluster-internal hostname; override for local testing."}
```

**Meta:**

- `flags`: `[]`
- `useCases`: `["Footprint", "Investigate", "Passive"]`
- `categories`: `["Real World"]`
- `dataSource.model`: `FREE_NOAUTH_UNLIMITED` (self-hosted, user controls quota)
- `dataSource.website`: `https://docs.ohdeere.se/maps-service/`
- `dataSource.description`: short note about Nominatim + GeoLite2, requires the OhDeere client-credentials token with `maps:read` scope.

### handleEvent flow

```
handleEvent(event):
    if client.disabled → return
    if errorState → return
    if event.data already seen this scan → return
    _seen.add(event.data)
    if event.eventType == "PHYSICAL_COORDINATES":
        _reverse_geocode(event)
    elif event.eventType == "PHYSICAL_ADDRESS":
        _forward_geocode(event)
```

### Reverse geocode

Input: `event.data` is the `"lat,lon"` string format emitted by `sfp_ohdeere_geoip` (or typed in manually).

1. Parse comma-split into `(lat, lon)`. If unparseable (non-float, wrong format), log `self.debug(...)` and return — not an error state.
2. Call `client.get(f"/api/v1/reverse?lat={lat}&lon={lon}", base_url=self.opts["maps_base_url"].rstrip("/"), scope="maps:read")` via the shared `_call` helper.
3. On success, emit `RAW_RIR_DATA` with the serialized JSON payload.
4. From `payload.get("display_name")`: if present, emit `PHYSICAL_ADDRESS`.
5. From `payload.get("address", {}).get("country")`: if present, emit `COUNTRY_NAME`.
6. City fallback chain: `address.city → address.town → address.village`. First present value wins. If country present, emit `GEOINFO` as `"{city}, {country}"` if city present, else `"{country}"` alone.

### Forward geocode

Input: `event.data` is a freeform address string.

1. URL-encode via `urllib.parse.urlencode({"q": event.data, "limit": 1})`.
2. Call `/api/v1/geocode?q=...&limit=1`.
3. On success, emit `RAW_RIR_DATA` (even for empty result arrays — the raw response is still useful for inspection).
4. Response is a list. If empty or non-list, log `self.debug(...)` and return — not an error.
5. Take `payload[0]`. If `lat` and `lon` both present, emit `PHYSICAL_COORDINATES` as `"{lat},{lon}"` (preserve Nominatim's string format — matches the convention of `sfp_ohdeere_geoip`).

### Shared `_call` helper

```python
def _call(self, path_with_query, source_event):
    base = self.opts["maps_base_url"].rstrip("/")
    try:
        return self._client.get(path_with_query, base_url=base, scope="maps:read")
    except OhDeereAuthError as exc:
        self.error(f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}")
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
```

Both `_reverse_geocode` and `_forward_geocode` call `_call(...)` and check for `None` before emitting. Matches the error contract in the client spec: auth errors distinct from server errors, both set `errorState`, both logged at `error` level.

### Format quirks worth locking in

- **Nominatim returns `lat`/`lon` as strings.** Preserve as-is in the emitted `PHYSICAL_COORDINATES` string. Matches the convention already established by `sfp_ohdeere_geoip`.
- **`/geocode` response is a list**, `/reverse` is a single object. The module handles both shapes explicitly.
- **Empty `/geocode` results are valid.** Log debug, emit only `RAW_RIR_DATA`.
- **Malformed input coordinates are not an error.** The upstream event source might have emitted garbage; log debug and return without calling the API. Preserves the `errorState` signal for real infrastructure failures.

## Testing

`test/unit/modules/test_sfp_ohdeere_maps.py` (~240 lines). Same `mock.patch("modules.sfp_ohdeere_maps.get_client", return_value=stub_client)` pattern used by `test_sfp_ohdeere_geoip.py`.

14 tests:

1. `opts` / `optdescs` key parity.
2. `watchedEvents` and `producedEvents` shape.
3. Silent no-op when helper is disabled.
4. Reverse happy path — full Nominatim response → all four expected events emitted.
5. Reverse with no `display_name` → only `RAW_RIR_DATA`.
6. Reverse `city → town` fallback — response has `address.town` but no `address.city`, `GEOINFO` uses `town`.
7. Reverse no-city fallback — neither `city`/`town`/`village`, `GEOINFO` uses country alone.
8. Reverse malformed coordinates — `event.data = "not-a-number"` → `self.debug` logged, no client call, no emissions.
9. Forward happy path — response is single-element list → `PHYSICAL_COORDINATES` + `RAW_RIR_DATA`.
10. Forward empty results — empty array → only `RAW_RIR_DATA`, `self.debug` logged.
11. Per-scan dedup — same coordinate string handled twice → one client call.
12. `OhDeereAuthError` (reverse direction) → `errorState`, no emissions, `self.error(...)`.
13. `OhDeereServerError` (forward direction) → `errorState`, no emissions, `self.error(...)`.
14. `errorState` short-circuits subsequent events of either type.

**Integration / smoke:** deliberately skipped at unit level. Live smoke is in the implementation-plan's final-verification task — run a scan against a real target with OhDeere env vars set, confirm reverse-geocode produces a real `PHYSICAL_ADDRESS` for the target's IP-geolocated coordinates.

**Full-suite verification:** current baseline is 1410 passed + 35 skipped. After this spec: 1424 passed + 35 skipped (+14 new tests). Flake8 clean.

## Rollout

Single commit with the module + test file. Like `sfp_ohdeere_geoip`, it's silent-no-op when the client is disabled (no `OHDEERE_*` env vars), so merging is safe even before the cluster has credentials deployed.

Follow-up tasks not in this spec:
- CLAUDE.md inventory update — add `sfp_ohdeere_maps` to `FREE_NOAUTH_UNLIMITED`, note that forward/reverse geocoding is now available.
- Live-scan smoke with real credentials against a known target to verify the round-trip `IP_ADDRESS → (geoip) PHYSICAL_COORDINATES → (maps reverse) PHYSICAL_ADDRESS`.
- Extend with `/nearby` (POI search from coordinates) — backlog task #40.

## Follow-ups enabled

- With this module landed, the full chain `IP → geo-coords → address` works end-to-end for every IP in a scan. OSINT queries like "where does this IP actually live" become useful.
- `/nearby` extension becomes cheaper once the base module is shipped — just one more watched-event/produced-event pair reusing the same `_call` helper.
- Future `sfp_ohdeere_notification` (scan-lifecycle pings) can include "scan enrichment complete: N addresses geocoded" as part of its status message.
