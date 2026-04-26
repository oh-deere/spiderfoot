# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_holehe
# Purpose:      Probe ~120 services for account existence using the holehe
#               library. For each EMAILADDR event, emit one
#               ACCOUNT_EXTERNAL_OWNED per confirmed registration.
# Introduced:   2026-04-26
# Licence:      MIT
# -------------------------------------------------------------------------------

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.holehe_runner import probe_email


class sfp_holehe(SpiderFootPlugin):

    meta = {
        "name": "Holehe Account Discovery",
        "summary": "Probe ~120 services to see if a registered account "
                   "exists for an email address (via holehe).",
        "flags": ["invasive"],
        "useCases": ["Investigate"],
        "categories": ["Social Media"],
        "dataSource": {
            "website": "https://github.com/megadose/holehe",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://github.com/megadose/holehe"],
            "description": "Open-source library that uses password-reset "
                           "and signup differential responses to detect "
                           "whether an email is registered at a service. "
                           "No API keys required.",
        },
    }

    opts = {
        "max_emails": 25,
        "timeout_s": 60,
        "skip_providers": "",
    }

    optdescs = {
        "max_emails": "Max emails to probe per scan (default 25). Holehe "
                      "is slow and invasive; keep this small.",
        "timeout_s": "Per-email wall-clock timeout in seconds (default 60).",
        "skip_providers": "Comma-separated provider names to skip, in "
                          "addition to the built-in skip list.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._processed = 0
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["EMAILADDR"]

    def producedEvents(self):
        return ["ACCOUNT_EXTERNAL_OWNED"]

    def handleEvent(self, event):
        if self.errorState:
            return

        max_emails = int(self.opts["max_emails"])
        if self._processed >= max_emails:
            self.debug(f"hit max_emails={max_emails}; skipping {event.data}")
            return

        skip = {
            s.strip() for s in self.opts["skip_providers"].split(",")
            if s.strip()
        }

        try:
            hits = probe_email(
                event.data,
                skip=skip,
                timeout_s=int(self.opts["timeout_s"]),
            )
        except Exception as exc:
            self.error(f"holehe runner failed: {exc}")
            self.errorState = True
            return

        self._processed += 1

        for hit in hits:
            data = (
                f"Holehe: {hit.provider} (Domain: {hit.domain})\n"
                f"<SFURL>https://{hit.domain}</SFURL>"
            )
            evt = SpiderFootEvent(
                "ACCOUNT_EXTERNAL_OWNED", data, self.__name__, event,
            )
            self.notifyListeners(evt)


# End of sfp_holehe class
