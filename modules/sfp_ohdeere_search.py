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
