# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_geoip
# Purpose:      Query the self-hosted ohdeere-geoip-service (MaxMind
#               GeoLite2) for IP address enrichment via the shared
#               OhDeereClient OAuth2 helper.
#
# Introduced:   2026-04-20 — first consumer of spiderfoot/ohdeere_client.py.
#               Replaces 4 external IP-geolocation modules in a follow-up
#               commit once live parity is verified.
# Licence:      MIT
# -------------------------------------------------------------------------------

import json

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
    OhDeereServerError,
    get_client,
)


class sfp_ohdeere_geoip(SpiderFootPlugin):

    meta = {
        "name": "OhDeere GeoIP",
        "summary": "Query the self-hosted ohdeere-geoip-service (MaxMind GeoLite2) "
                   "for country, city, coordinates, and ASN on IP_ADDRESS / "
                   "IPV6_ADDRESS events.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Real World"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/geoip-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/geoip-service/"],
            "description": "Self-hosted wrapper around MaxMind GeoLite2. Requires "
                           "the OhDeere client-credentials token (OHDEERE_CLIENT_ID "
                           "/ OHDEERE_CLIENT_SECRET env vars) with geoip:read scope.",
        },
    }

    opts = {
        "geoip_base_url": "https://geoip.ohdeere.internal",
    }

    optdescs = {
        "geoip_base_url": "Base URL of the ohdeere-geoip-service. Defaults to the "
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
        return ["IP_ADDRESS", "IPV6_ADDRESS"]

    def producedEvents(self):
        return [
            "COUNTRY_NAME",
            "GEOINFO",
            "PHYSICAL_COORDINATES",
            "BGP_AS_OWNER",
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

        base = self.opts["geoip_base_url"].rstrip("/")
        try:
            payload = self._client.get(
                f"/api/v1/lookup/{event.data}",
                base_url=base,
                scope="geoip:read",
            )
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
            return
        except OhDeereServerError as exc:
            self.error(f"OhDeere geoip server error: {exc}")
            self.errorState = True
            return
        except OhDeereClientError as exc:
            self.error(f"OhDeere geoip request failed: {exc}")
            self.errorState = True
            return

        self._emit(event, "RAW_RIR_DATA", json.dumps(payload))

        country = (payload.get("country") or {}).get("name")
        city = (payload.get("city") or {}).get("name")
        location = payload.get("location") or {}
        asn_org = (payload.get("asn") or {}).get("org")

        if country:
            self._emit(event, "COUNTRY_NAME", country)
            geoinfo = f"{city}, {country}" if city else country
            self._emit(event, "GEOINFO", geoinfo)
        lat = location.get("lat")
        lon = location.get("lon")
        if lat is not None and lon is not None:
            self._emit(event, "PHYSICAL_COORDINATES", f"{lat},{lon}")
        if asn_org:
            self._emit(event, "BGP_AS_OWNER", asn_org)

    def _emit(self, source_event, event_type: str, data: str) -> None:
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_geoip class
