# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_searxng
# Purpose:      Query a user-operated SearXNG instance for site:<target>
#               dorks, emitting URL/subdomain/email/raw-response events.
#
# Introduced:   2026-04-20 — replaces sfp_bingsearch, sfp_bingsharedip,
#               sfp_googlesearch, and sfp_pastebin (all removed in the
#               dead-module audit).
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import re
import urllib.parse

from spiderfoot import SpiderFootEvent, SpiderFootPlugin

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")


class sfp_searxng(SpiderFootPlugin):

    meta = {
        "name": "SearXNG",
        "summary": "Query a self-hosted SearXNG instance for site:<target> dorks and harvest URLs, "
                   "subdomains, and emails from the aggregated result set.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Search Engines"],
        "dataSource": {
            "website": "https://github.com/searxng/searxng",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": [
                "https://docs.searxng.org/dev/search_api.html",
            ],
            "description": "SearXNG is a privacy-respecting metasearch engine that aggregates results "
                           "from DuckDuckGo, Brave, Qwant, Startpage, Mojeek, and others. This module "
                           "queries a user-operated SearXNG instance via its JSON API, so results depend "
                           "on the instance's configured backends. Public instances are listed at https://searx.space/.",
        },
    }

    opts = {
        "searxng_url": "",
        "max_pages": 3,
        "fetch_timeout": 30,
    }

    optdescs = {
        "searxng_url": "Base URL of your SearXNG instance (e.g. https://searxng.ohdeere.internal). "
                       "Leave empty to disable this module.",
        "max_pages": "Number of result pages to fetch per input event (SearXNG returns ~10-20 results per page; "
                     "3 pages ≈ 30-60 URLs, a reasonable depth for subdomain discovery).",
        "fetch_timeout": "HTTP timeout in seconds for each call to SearXNG.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._handled_events = set()
        self._emitted_hostnames = set()
        self._emitted_emails = set()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]
        # Normalise trailing slash on the URL so we can join safely.
        if self.opts.get("searxng_url"):
            self.opts["searxng_url"] = self.opts["searxng_url"].rstrip("/")

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
        if not self.opts.get("searxng_url"):
            return
        if self.errorState:
            return
        if event.data in self._handled_events:
            return
        self._handled_events.add(event.data)

        base = self.opts["searxng_url"]
        query = f"site:{event.data}"

        for pageno in range(1, int(self.opts["max_pages"]) + 1):
            params = urllib.parse.urlencode({
                "q": query,
                "format": "json",
                "safesearch": 0,
                "pageno": pageno,
            })
            url = f"{base}/search?{params}"
            response = self.sf.fetchUrl(
                url,
                timeout=int(self.opts["fetch_timeout"]),
                useragent=self.opts.get("_useragent", "SpiderFoot"),
            )
            if not response or response.get("code") != "200":
                code = response.get("code") if response else "no-response"
                self.error(f"SearXNG query failed (HTTP {code}) for {event.data} page {pageno}")
                self.errorState = True
                return

            try:
                payload = json.loads(response.get("content") or "{}")
            except json.JSONDecodeError as exc:
                self.error(f"SearXNG returned non-JSON for {event.data} page {pageno}: {exc}")
                self.errorState = True
                return

            self._emit_page(payload, event)

    def _emit_page(self, payload, source_event):
        self._emit_event("RAW_RIR_DATA", json.dumps(payload), source_event)
        for result in payload.get("results") or []:
            self._process_result(result, source_event)

    def _process_result(self, result, source_event):
        url = (result or {}).get("url")
        if not url:
            self.debug("SearXNG result missing url field; skipping")
            return

        try:
            hostname = self.sf.urlFQDN(url)
        except (TypeError, AttributeError) as exc:
            self.debug(f"urlFQDN failed on {url}: {exc}")
            return

        # Don't re-emit the input domain as a subdomain discovery (it's already
        # been emitted as the parent event).
        if hostname == source_event.data:
            # Still emit the URL itself as LINKED_URL_INTERNAL, but skip
            # the subdomain-discovery path below.
            is_self_echo = True
        else:
            is_self_echo = False

        is_internal = False
        target = self.getTarget()
        if target is not None and hostname:
            is_internal = target.matches(hostname, includeChildren=True)

        if is_internal:
            self._emit_event("LINKED_URL_INTERNAL", url, source_event)
            if not is_self_echo and hostname and hostname not in self._emitted_hostnames:
                self._emitted_hostnames.add(hostname)
                self._emit_event("INTERNET_NAME", hostname, source_event)
        else:
            self._emit_event("LINKED_URL_EXTERNAL", url, source_event)

        snippet = (result or {}).get("content") or ""
        for email in _EMAIL_RE.findall(snippet):
            if email in self._emitted_emails:
                continue
            self._emitted_emails.add(email)
            self._emit_event("EMAILADDR", email, source_event)

    def _emit_event(self, event_type, data, source_event):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_searxng class
