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
        payload = self._call(url)
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

    def _format_tower(self, tower):
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
            # 4xx (incl. 404 for unknown CGI) — debug-log, skip, no errorState.
            self.debug(f"OhDeere celltower request rejected: {exc}")
            return None

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
