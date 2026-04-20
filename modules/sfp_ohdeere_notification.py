# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_notification
# Purpose:      Fire Slack notifications at scan-start and scan-complete
#               via the self-hosted ohdeere-notification-service. Fifth
#               consumer of spiderfoot/ohdeere_client.py; first sink
#               module, first to use SpiderFootPlugin.finish() as a
#               lifecycle hook.
# Introduced:   2026-04-20
# Licence:      MIT
# -------------------------------------------------------------------------------

from spiderfoot import SpiderFootPlugin
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
    OhDeereServerError,
    get_client,
)


class sfp_ohdeere_notification(SpiderFootPlugin):

    meta = {
        "name": "OhDeere Notification",
        "summary": "Fire Slack notifications at scan start and scan complete "
                   "via the self-hosted ohdeere-notification-service. "
                   "Optional clickable link to the scan UI.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Real World"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/notification-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/notification-service/"],
            "description": "Self-hosted email + Slack dispatch service. Requires "
                           "the OhDeere client-credentials token "
                           "(OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET env vars) "
                           "with notifications:slack:send scope.",
        },
    }

    opts = {
        "notification_base_url": "https://notification.ohdeere.internal",
        "slack_channel": "",
        "spiderfoot_ui_url": "",
    }

    optdescs = {
        "notification_base_url": "Base URL of the ohdeere-notification-service. "
                                 "Defaults to the cluster-internal hostname.",
        "slack_channel": "Override the Slack channel. Empty uses the service "
                         "default ('notifications').",
        "spiderfoot_ui_url": "Base URL of your SpiderFoot web UI (e.g. "
                             "https://spiderfoot.ohdeere.internal). When set, "
                             "the notification message includes a clickable "
                             "/scaninfo?id=<scanId> link. Empty = no link.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._start_notified = False
        self._complete_notified = False
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["ROOT"]

    def producedEvents(self):
        return []

    def handleEvent(self, event):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if self._start_notified:
            return
        self._start_notified = True
        self._notify(f"\U0001F50E Scan started for {event.data}")

    def finish(self):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if self._complete_notified:
            return
        self._complete_notified = True
        target = "this scan"
        try:
            t = self.getTarget()
            if t is not None and getattr(t, "targetValue", None):
                target = t.targetValue
        except Exception:
            pass
        self._notify(f"\u2705 Scan completed for {target}")

    def _notify(self, body):
        body = self._append_scan_link(body)
        payload = {"text": body}
        channel = self.opts.get("slack_channel", "")
        if channel:
            payload["channel"] = channel

        base = self.opts["notification_base_url"].rstrip("/")
        try:
            self._client.post(
                "/api/notifications/slack",
                payload,
                base_url=base,
                scope="notifications:slack:send",
            )
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
        except OhDeereServerError as exc:
            self.error(f"OhDeere notification server error: {exc}")
            self.errorState = True
        except OhDeereClientError as exc:
            self.error(f"OhDeere notification request failed: {exc}")
            self.errorState = True

    def _append_scan_link(self, body):
        ui = self.opts.get("spiderfoot_ui_url", "").rstrip("/")
        if not ui:
            return body
        try:
            scan_id = self.getScanId()
        except Exception:
            return body
        if not scan_id:
            return body
        return f"{body} ({ui}/scaninfo?id={scan_id})"


# End of sfp_ohdeere_notification class
