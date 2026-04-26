# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_duckduckgo
# Purpose:      Scrape DuckDuckGo's HTML search interface for site:<target>
#               dorks. Replaces the 2015-vintage Instant Answer wrapper.
#               Emits LINKED_URL_INTERNAL/EXTERNAL, INTERNET_NAME (subdomains),
#               EMAILADDR (from snippets), and RAW_RIR_DATA mirroring
#               sfp_searxng.
# Introduced:   2026-04-26 (replacement; original module dates to 2015).
# Licence:      MIT
# -------------------------------------------------------------------------------

import json
import re
import urllib.parse

from bs4 import BeautifulSoup

from spiderfoot import SpiderFootEvent, SpiderFootPlugin


_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_PAGE_SIZE = 30
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
_ANOMALY_SENTINEL = "anomaly-modal"
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


class sfp_duckduckgo(SpiderFootPlugin):

    meta = {
        "name": "DuckDuckGo",
        "summary": "Scrape DuckDuckGo HTML search results for site:<target> "
                   "dorks. Harvests URLs, subdomains, and emails. Zero-config — "
                   "works without a self-hosted search backend.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Search Engines"],
        "dataSource": {
            "website": "https://duckduckgo.com/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://duckduckgo.com/",
                           "https://html.duckduckgo.com/html/"],
            "description": "Public HTML search interface at "
                           "html.duckduckgo.com/html/. No API key required. "
                           "DDG occasionally rate-limits scrapers via a CAPTCHA "
                           "modal; the module detects this and stops for the "
                           "rest of the scan.",
        },
    }

    opts = {
        "max_pages": 2,
        "fetch_timeout": 30,
    }

    optdescs = {
        "max_pages": "Number of result pages to fetch per input event "
                     "(DDG returns ~30 results per page; default 2 ≈ 60 URLs).",
        "fetch_timeout": "HTTP timeout in seconds for each call to DuckDuckGo.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._handled_events: set = set()
        self._emitted_hostnames: set = set()
        self._emitted_emails: set = set()
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
        if self.errorState:
            return
        if event.data in self._handled_events:
            return
        self._handled_events.add(event.data)

        query = f"site:{event.data}"
        for pageno in range(int(self.opts["max_pages"])):
            offset = pageno * _PAGE_SIZE
            post_body = urllib.parse.urlencode({"q": query, "s": str(offset)})
            response = self.sf.fetchUrl(
                _DDG_HTML_URL,
                postData=post_body,
                timeout=int(self.opts["fetch_timeout"]),
                useragent=_USER_AGENT,
            )
            if not response or response.get("code") != "200":
                code = response.get("code") if response else "no-response"
                self.error(
                    f"DuckDuckGo HTTP {code} for {event.data} page {pageno + 1}"
                )
                self.errorState = True
                return

            body = response.get("content") or ""
            if _ANOMALY_SENTINEL in body:
                self.error(
                    "DuckDuckGo returned an anomaly page (CAPTCHA / "
                    "rate-limit); bailing for the rest of the scan"
                )
                self.errorState = True
                return

            results = self._parse(body)
            self._emit_event(
                "RAW_RIR_DATA",
                json.dumps(results, ensure_ascii=False),
                event,
            )
            for entry in results:
                self._process_result(entry, event)

    def _parse(self, body: str) -> list:
        try:
            soup = BeautifulSoup(body, "html.parser")
        except Exception as exc:
            self.debug(f"BeautifulSoup parse failed: {exc}")
            return []

        out = []
        for block in soup.select("div.result.results_links"):
            a = block.select_one("a.result__a")
            if a is None:
                continue
            href = a.get("href") or ""
            if not href:
                continue
            url = self._unwrap_uddg(href)
            snippet_el = block.select_one("a.result__snippet")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            out.append({"url": url, "snippet": snippet})
        return out

    def _unwrap_uddg(self, href: str) -> str:
        if (href.startswith("//duckduckgo.com/l/?")
                or href.startswith("https://duckduckgo.com/l/?")
                or href.startswith("http://duckduckgo.com/l/?")):
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            uddg = params.get("uddg")
            if uddg:
                return uddg[0]
        return href

    def _process_result(self, entry, source_event):
        url = entry.get("url")
        if not url:
            return

        try:
            hostname = self.sf.urlFQDN(url)
        except (TypeError, AttributeError) as exc:
            self.debug(f"urlFQDN failed on {url}: {exc}")
            return

        is_self_echo = (hostname == source_event.data)
        is_internal = False
        target = self.getTarget()
        if target is not None and hostname:
            is_internal = target.matches(hostname, includeChildren=True)

        if is_internal:
            self._emit_event("LINKED_URL_INTERNAL", url, source_event)
            if (not is_self_echo and hostname
                    and hostname not in self._emitted_hostnames):
                self._emitted_hostnames.add(hostname)
                self._emit_event("INTERNET_NAME", hostname, source_event)
        else:
            self._emit_event("LINKED_URL_EXTERNAL", url, source_event)

        snippet = entry.get("snippet") or ""
        for email in _EMAIL_RE.findall(snippet):
            if email in self._emitted_emails:
                continue
            self._emitted_emails.add(email)
            self._emit_event("EMAILADDR", email, source_event)

    def _emit_event(self, event_type: str, data: str, source_event):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_duckduckgo class
