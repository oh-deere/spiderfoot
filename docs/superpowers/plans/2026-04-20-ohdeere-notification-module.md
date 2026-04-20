# `sfp_ohdeere_notification` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Single-track plan.

**Goal:** Ship `modules/sfp_ohdeere_notification.py` — a sink module that fires Slack pings via `ohdeere-notification-service` at scan-start and scan-complete. Fifth consumer of `spiderfoot/ohdeere_client.py`; first to use `SpiderFootPlugin.finish()` as a lifecycle hook.

**Architecture:** Watches `ROOT` event for scan-start (data = target value), overrides `finish()` for scan-complete. Both boolean-guarded against duplicates. `.post()` against the OhDeere helper with scope `notifications:slack:send`. Same silent-no-op + errorState error-handling pattern as other OhDeere consumers.

**Tech Stack:** Python 3.12+ stdlib only. No new deps.

**Spec:** `docs/superpowers/specs/2026-04-20-ohdeere-notification-module-design.md`.

---

## File Structure

- **Create** `modules/sfp_ohdeere_notification.py` — ~180 lines.
- **Create** `test/unit/modules/test_sfp_ohdeere_notification.py` — ~220 lines, 10 unit tests.

No other file changes.

---

## Context for the implementer

- **Current baseline:** `./test/run` reports 1441 passed + 35 skipped. After this plan: **1451 passed + 35 skipped**.
- **Reference modules:** `modules/sfp_ohdeere_geoip.py` (OhDeereClient consumer pattern), `modules/sfp_ohdeere_wiki.py` (simpler emit pattern).
- **Reference tests:** `test/unit/modules/test_sfp_ohdeere_wiki.py` (same `mock.patch("modules.<name>.get_client", return_value=stub)` pattern).
- **Scan lifecycle accessors on `SpiderFootPlugin`:**
  - `self.getScanId()` returns the scan's UUID string. May raise `TypeError` if no scanId is set — catch defensively.
  - `self.getTarget()` returns the `SpiderFootTarget` instance; `.targetValue` is the string the user typed (domain, IP, etc.).
  - `self.finish()` override is called by the scan orchestrator during wind-down, possibly multiple times (per plugin.py docstring).
- **ROOT event:** fires once per scan as the first event with `data = target value`. See `sfscan.py:383-384`.
- **Notification service body shape:** `{"text": "...", "channel": "..." (optional), "blocks": [...] (optional)}`. Only `text` is required. We use `text` + optionally `channel`; no `blocks`.
- **Running single test file:** `python3 -m pytest test/unit/modules/test_sfp_ohdeere_notification.py -v`.
- **Flake8:** config in `setup.cfg`, max-line 120.

---

## Task 1: Failing tests

**Files:**
- Create: `test/unit/modules/test_sfp_ohdeere_notification.py`

- [ ] **Step 1: Create the test file**

Write EXACTLY this content:

```python
# test_sfp_ohdeere_notification.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_notification import sfp_ohdeere_notification
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereAuthError


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereNotification(unittest.TestCase):

    def _module(self, client, opts=None):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_notification()
        with mock.patch("modules.sfp_ohdeere_notification.get_client",
                        return_value=client):
            module.setup(sf, opts or {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        module.setScanId("scan-abc-123")
        return sf, module

    def _root_event(self, target="example.com"):
        return SpiderFootEvent("ROOT", target, "", "")

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_notification()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_notification()
        self.assertEqual(module.watchedEvents(), ["ROOT"])
        self.assertEqual(module.producedEvents(), [])

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.finish()
        client.post.assert_not_called()

    def test_root_event_fires_start_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event(target="example.com"))
        self.assertEqual(client.post.call_count, 1)
        call = client.post.call_args
        body = call.kwargs.get("body", call.args[1] if len(call.args) > 1 else None)
        self.assertIn("Scan started", body["text"])
        self.assertIn("example.com", body["text"])
        self.assertIn("🔎", body["text"])

    def test_duplicate_root_events_single_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.handleEvent(self._root_event())
        self.assertEqual(client.post.call_count, 1)

    def test_finish_fires_complete_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.finish()
        self.assertEqual(client.post.call_count, 2)
        complete_call = client.post.call_args_list[1]
        body = complete_call.kwargs.get("body",
                                        complete_call.args[1] if len(complete_call.args) > 1 else None)
        self.assertIn("Scan completed", body["text"])
        self.assertIn("✅", body["text"])

    def test_duplicate_finish_single_complete_notification(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        module.handleEvent(self._root_event())
        module.finish()
        module.finish()
        module.finish()
        self.assertEqual(client.post.call_count, 2)  # start + complete, once each

    def test_ui_url_configured_includes_scan_link(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client, opts={
            "spiderfoot_ui_url": "https://spiderfoot.example.test",
        })
        module.handleEvent(self._root_event())
        body = client.post.call_args.kwargs.get(
            "body", client.post.call_args.args[1])
        self.assertIn(
            "https://spiderfoot.example.test/scaninfo?id=scan-abc-123",
            body["text"],
        )

    def test_slack_channel_configured_included_in_payload(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client, opts={"slack_channel": "shootingstar"})
        module.handleEvent(self._root_event())
        body = client.post.call_args.kwargs.get(
            "body", client.post.call_args.args[1])
        self.assertEqual(body["channel"], "shootingstar")

    def test_auth_error_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.side_effect = OhDeereAuthError("bad creds")
        _, module = self._module(client)
        with mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._root_event())
        self.assertTrue(module.errorState)
        m_error.assert_called()
```

- [ ] **Step 2: Run the tests and confirm collection failure**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_notification.py -v`

Expected: `ModuleNotFoundError: No module named 'modules.sfp_ohdeere_notification'`.

- [ ] **Step 3: Flake8**

Run: `python3 -m flake8 test/unit/modules/test_sfp_ohdeere_notification.py`

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add test/unit/modules/test_sfp_ohdeere_notification.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_ohdeere_notification

Ten unit tests driving Task 2: opts/optdescs parity, watched=[ROOT]
produced=[] shape, silent no-op when helper disabled, ROOT event
fires start notification with expected payload, duplicate ROOT
events → single notification (boolean guard), finish() fires complete
notification, duplicate finish() calls → single complete (guard
handles orchestrator's multi-call cleanup), spiderfoot_ui_url opt
appends /scaninfo?id=<scanId> link, slack_channel opt passes through
to payload, OhDeereAuthError sets errorState.

Refs docs/superpowers/specs/2026-04-20-ohdeere-notification-module-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement the module

**Files:**
- Create: `modules/sfp_ohdeere_notification.py`

- [ ] **Step 1: Create the module**

Write this to `modules/sfp_ohdeere_notification.py`:

```python
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

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
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
        self._notify(f"🔎 Scan started for {event.data}")

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
        self._notify(f"✅ Scan completed for {target}")

    def _notify(self, body: str) -> None:
        body = self._append_scan_link(body)
        payload = {"text": body}
        channel = self.opts.get("slack_channel", "")
        if channel:
            payload["channel"] = channel

        base = self.opts["notification_base_url"].rstrip("/")
        try:
            self._client.post(
                "/api/notifications/slack",
                body=payload,
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

    def _append_scan_link(self, body: str) -> str:
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
```

- [ ] **Step 2: Run the tests**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_notification.py -v`

Expected: **10 passed**.

Common failure modes:
- `test_root_event_fires_start_notification` — emoji character in the message is `🔎` (U+1F50E); make sure it's literally present in the `f"🔎 Scan started..."` line.
- `test_ui_url_configured_includes_scan_link` — the link format is `<url>/scaninfo?id=<scanId>`. Ensure `spiderfoot_ui_url` is rstripped of trailing slash.
- `test_auth_error_sets_errorstate` — the `OhDeereAuthError` is raised by `client.post`, caught in `_notify`. `errorState = True` must happen before the method returns.

- [ ] **Step 3: Run the full suite**

Run: `./test/run`

Expected: `1451 passed, 35 skipped`. Flake8 clean.

- [ ] **Step 4: Flake8**

Run: `python3 -m flake8 modules/sfp_ohdeere_notification.py`

Expected: clean.

- [ ] **Step 5: Verify module discovery**

```bash
python3 ./sf.py -M 2>&1 | grep "sfp_ohdeere_notification"
```

Expected: one line with the module + summary.

- [ ] **Step 6: Commit**

```bash
git add modules/sfp_ohdeere_notification.py
git commit -m "$(cat <<'EOF'
modules: add sfp_ohdeere_notification — scan-lifecycle Slack pings

Fifth consumer of spiderfoot/ohdeere_client.py. First sink module
and first to use SpiderFootPlugin.finish() as a lifecycle hook.

Watches ROOT event for scan-start (data = target value, fired once
at scan begin), fires one Slack notification. Overrides finish()
for scan-complete, fires another. Both guarded by booleans so the
orchestrator's multi-call cleanup of finish() doesn't duplicate.

POST /api/notifications/slack with scope notifications:slack:send.
Plain-text message; optional channel override via slack_channel
opt; optional clickable /scaninfo?id=<scanId> link appended when
spiderfoot_ui_url is configured.

Silent no-op when helper is disabled. Auth / server errors raise
errorState so the scan-complete notification doesn't noisily re-fail
after a failed scan-start.

Refs docs/superpowers/specs/2026-04-20-ohdeere-notification-module-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Final verification

- [ ] **Step 1: Full CI run**

```bash
./test/run 2>&1 | tail -5
```

Expected: `1451 passed, 35 skipped`, flake8 clean.

- [ ] **Step 2: Smoke scan with client disabled**

```bash
rm -f /tmp/sf-notif-smoke.log
unset OHDEERE_CLIENT_ID OHDEERE_CLIENT_SECRET OHDEERE_AUTH_URL
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_notification 2>/tmp/sf-notif-smoke.log &
SF_PID=$!
sleep 25
kill $SF_PID 2>/dev/null; wait $SF_PID 2>/dev/null
echo "--- import errors ---"
grep -iE "ImportError|ModuleNotFoundError|Traceback" /tmp/sf-notif-smoke.log || echo "(none)"
rm -f /tmp/sf-notif-smoke.log
```

Expected: `(none)` — module loads silently when disabled.

- [ ] **Step 3: Module discovery**

```bash
python3 ./sf.py -M 2>&1 | grep "sfp_ohdeere_notification"
```

Expected: one line.

- [ ] **Step 4: OhDeere module-pair tests**

```bash
python3 -m pytest \
    test/unit/spiderfoot/test_ohdeere_client.py \
    test/unit/modules/test_sfp_ohdeere_geoip.py \
    test/unit/modules/test_sfp_ohdeere_maps.py \
    test/unit/modules/test_sfp_ohdeere_wiki.py \
    test/unit/modules/test_sfp_ohdeere_search.py \
    test/unit/modules/test_sfp_ohdeere_notification.py -v 2>&1 | tail -5
```

Expected: 11 + 12 + 14 + 7 + 10 + 10 = **64 passed**.

- [ ] **Step 5: Module count**

```bash
echo "Module count: $(ls modules/sfp_*.py | wc -l)"
```

Expected: 191 (was 190 before).

- [ ] **Step 6: Report**

Summary: 2 commits (tests + module), module count 190 → 191, test count 1441 → 1451, fifth OhDeere consumer lands cleanly using both lifecycle hooks.
