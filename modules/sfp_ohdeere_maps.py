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
from spiderfoot.ohdeere_maps_url import DEFAULT_BASE_URL, maps_deeplink


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

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._seen: set[str] = set()
        self._nearby_cells: dict[tuple[float, float], list] = {}
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
            if not self.errorState:
                self._nearby(event)
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
        self._emit(event, "RAW_RIR_DATA", json.dumps(payload, ensure_ascii=False))

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

    def _forward_geocode(self, event):
        params = urllib.parse.urlencode({"q": event.data, "limit": 1})
        payload = self._call(f"/api/v1/geocode?{params}")
        if payload is None:
            return
        self._emit(event, "RAW_RIR_DATA", json.dumps(payload, ensure_ascii=False))

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
        items = payload if isinstance(payload, list) else []
        self._nearby_cells[cell] = items

        self._emit_with_link(
            event, "RAW_RIR_DATA", json.dumps(items, ensure_ascii=False),
            cell[0], cell[1],
        )

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

    def _emit_with_link(self, source_event, event_type: str, data: str,
                        lat, lon) -> None:
        link = maps_deeplink(
            float(lat), float(lon),
            base_url=self.opts["maps_ui_base_url"],
        )
        self._emit(source_event, event_type, f"{data}\n<SFURL>{link}</SFURL>")

    def _emit(self, source_event, event_type: str, data: str) -> None:
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_maps class
