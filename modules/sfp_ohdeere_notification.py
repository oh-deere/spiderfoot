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

from collections import Counter

from spiderfoot import SpiderFootPlugin
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
    OhDeereServerError,
    get_client,
)


_RISK_PRIORITY = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
_TOP_TYPES_N = 5
_TOP_FINDINGS_N = 5


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

        body = self._completion_message(target)
        self._notify(body)

    def _get_db(self):
        db = getattr(self, "__sfdb__", None)
        if db is None:
            return getattr(self, "_SpiderFootPlugin__sfdb__", None)
        return db

    def _completion_message(self, target: str) -> str:
        terse = f"\u2705 Scan completed for {target}"
        try:
            db = self._get_db()
            if db is None:
                return terse
            scan_id = self.getScanId()
            instance = db.scanInstanceGet(scan_id) or []
            events = db.scanResultEvent(scan_id) or []
            correlations = db.scanCorrelationList(scan_id) or []
        except Exception as exc:
            self.debug(f"DB unavailable for rich completion message: {exc}")
            return terse

        try:
            duration = self._format_duration(instance)
            counts = Counter(row[4] for row in events if len(row) > 4)
            total_events = sum(counts.values())

            lines = [terse]
            lines.append(
                f"*Duration:* {duration}  \u00b7  *Events:* {total_events}"
            )

            if total_events > 0:
                lines.append("*Top event types:*")
                for evt_type, count in counts.most_common(_TOP_TYPES_N):
                    lines.append(f"  \u2022 {evt_type}: {count}")

            top_findings = self._top_findings(correlations)
            if top_findings:
                lines.append("*Top findings:*")
                for risk, title, event_count in top_findings:
                    suffix = "event" if event_count == 1 else "events"
                    lines.append(
                        f"  \u2022 [{risk}] {title} \u2014 "
                        f"{event_count} {suffix}"
                    )

            return "\n".join(lines)
        except Exception as exc:
            self.debug(f"failed to build rich completion message: {exc}")
            return terse

    def _format_duration(self, instance) -> str:
        if not instance or len(instance) < 5:
            return "unknown"
        try:
            started = float(instance[3])
            ended = float(instance[4])
        except (TypeError, ValueError):
            return "unknown"
        delta = ended - started
        if delta < 0 or delta != delta:
            return "unknown"
        secs = int(delta)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def _top_findings(self, correlations) -> list:
        rows = []
        for row in correlations or []:
            if len(row) < 8:
                continue
            risk = row[3] or "INFO"
            title = row[1] or ""
            event_count = row[7] or 0
            rows.append((risk, title, event_count))
        rows.sort(key=lambda r: (-_RISK_PRIORITY.get(r[0], 0), r[1]))
        return rows[:_TOP_FINDINGS_N]

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
        link = f" ({ui}/scaninfo?id={scan_id})"
        # Append to the first line so multi-line completion messages keep
        # their headline-with-link shape.
        first, sep, rest = body.partition("\n")
        return first + link + sep + rest


# End of sfp_ohdeere_notification class
