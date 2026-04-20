# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_wiki
# Purpose:      Entity enrichment via the self-hosted ohdeere-wiki-service
#               (Kiwix ZIM full-text search). Third consumer of
#               spiderfoot/ohdeere_client.py.
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


class sfp_ohdeere_wiki(SpiderFootPlugin):

    meta = {
        "name": "OhDeere Wiki",
        "summary": "Look up companies or human names in the self-hosted "
                   "ohdeere-wiki-service (Kiwix ZIM full-text search) and "
                   "emit a DESCRIPTION_ABSTRACT snippet for the best match.",
        "flags": [],
        "useCases": ["Investigate", "Passive"],
        "categories": ["Content Analysis"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/wiki-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/wiki-service/"],
            "description": "Self-hosted Kiwix proxy (Wikipedia, Stack Exchange, "
                           "LibreTexts ZIMs). Requires the OhDeere client-credentials "
                           "token (OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET env "
                           "vars) with wiki:read scope.",
        },
    }

    opts = {"wiki_base_url": "https://wiki.ohdeere.internal"}
    optdescs = {"wiki_base_url": "Base URL of the ohdeere-wiki-service. Defaults to "
                                 "the cluster-internal hostname; override for local "
                                 "testing."}

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._seen: set[str] = set()
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["COMPANY_NAME", "HUMAN_NAME"]

    def producedEvents(self):
        return ["DESCRIPTION_ABSTRACT", "RAW_RIR_DATA"]

    def handleEvent(self, event):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if event.data in self._seen:
            return
        self._seen.add(event.data)

        params = urllib.parse.urlencode({"q": event.data, "limit": 1})
        payload = self._call(f"/api/v1/search?{params}")
        if payload is None:
            return
        self._emit(event, "RAW_RIR_DATA", json.dumps(payload))

        results = payload.get("results") or []
        if not results:
            self.debug(f"no wiki match for: {event.data}")
            return
        snippet = results[0].get("snippet")
        if snippet:
            self._emit(event, "DESCRIPTION_ABSTRACT", snippet)

    def _call(self, path_with_query):
        base = self.opts["wiki_base_url"].rstrip("/")
        try:
            return self._client.get(path_with_query, base_url=base,
                                    scope="wiki:read")
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
            return None
        except OhDeereServerError as exc:
            self.error(f"OhDeere wiki server error: {exc}")
            self.errorState = True
            return None
        except OhDeereClientError as exc:
            self.error(f"OhDeere wiki request failed: {exc}")
            self.errorState = True
            return None

    def _emit(self, source_event, event_type, data):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_wiki class
