# `sfp_ohdeere_notification` — scan-lifecycle Slack pings

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Fifth consumer of `spiderfoot/ohdeere_client.py`. Unlike previous consumers which are event-bus enrichment modules, this is a **sink module** that fires Slack notifications at scan-lifecycle boundaries via `ohdeere-notification-service`.

- **Scan start:** handled by watching the `ROOT` event (fired once per scan, data = target value).
- **Scan complete:** handled by overriding `SpiderFootPlugin.finish()`.

Both sends use scope `notifications:slack:send` against `POST /api/notifications/slack`.

## Non-goals

- **Not** notifying on individual high-value event types (`MALICIOUS_*`, `VULNERABILITY_*`). v1 is lifecycle-only. Event-filtered notifications are a separate follow-up if the user wants them.
- **Not** using Slack Block Kit `blocks`. Plain text message in the `text` field, optionally with a clickable URL.
- **Not** emailing. The notification service supports email, but scope `notifications:slack:send` is narrower than `notifications:send`; our client is provisioned for Slack only.
- **Not** including scan-summary stats (event counts, duration, module breakdown). The `finish()` hook doesn't receive that context without extra plumbing. A richer "scan summary" notification would be a follow-up.
- **Not** producing any events. Pure sink module.

## Design

### Module shape

One new file `modules/sfp_ohdeere_notification.py` (~180 lines). Standard `SpiderFootPlugin` with the additions:

- Override `watchedEvents() → ["ROOT"]` so the first event of every scan triggers `handleEvent`.
- Override `finish()` — new territory; previous consumers didn't use it. Called by the scan orchestrator multiple times during wind-down, so guarded by a boolean to ensure one notification per scan.
- `producedEvents() → []`. Sink module.

**Metadata:**
- `flags = []`
- `useCases = ["Footprint", "Investigate", "Passive"]` (enabled in all scan modes)
- `categories = ["Real World"]` (no great fit; "Real World" is the closest — it's what ohdeere_geoip uses)
- `dataSource.model = "FREE_NOAUTH_UNLIMITED"`
- `dataSource.website = "https://docs.ohdeere.se/notification-service/"`

**Opts:**

```python
opts = {
    "notification_base_url": "https://notification.ohdeere.internal",
    "slack_channel": "",
    "spiderfoot_ui_url": "",
}
```

- `slack_channel` empty → service uses its default (`notifications`).
- `spiderfoot_ui_url` empty → message has no clickable link. If set to something like `https://spiderfoot.ohdeere.internal`, the message appends ` (https://spiderfoot.ohdeere.internal/scaninfo?id=<scanId>)`.

### Lifecycle hooks

```python
def setup(self, sfc, userOpts):
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
    if self._client.disabled or self.errorState: return
    if self._start_notified: return
    self._start_notified = True
    self._notify(f"🔎 Scan started for {event.data}")

def finish(self):
    if self._client.disabled or self.errorState: return
    if self._complete_notified: return
    self._complete_notified = True
    target = "this scan"
    try:
        # Scan target stored on the SpiderFootTarget attached to the module.
        t = self.getTarget()
        if t is not None and t.targetValue:
            target = t.targetValue
    except Exception:
        pass
    self._notify(f"✅ Scan completed for {target}")
```

### Message construction

`_notify(body)` appends the scan-UI link if configured and POSTs:

```python
def _notify(self, body: str):
    ui = self.opts.get("spiderfoot_ui_url", "").rstrip("/")
    if ui:
        try:
            scan_id = self.getScanId()
        except Exception:
            scan_id = None
        if scan_id:
            body = f"{body} ({ui}/scaninfo?id={scan_id})"

    payload = {"text": body}
    channel = self.opts.get("slack_channel", "")
    if channel:
        payload["channel"] = channel

    base = self.opts["notification_base_url"].rstrip("/")
    try:
        self._client.post("/api/notifications/slack", body=payload,
                          base_url=base, scope="notifications:slack:send")
    except OhDeereAuthError as exc:
        self.error(f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}")
        self.errorState = True
    except OhDeereServerError as exc:
        self.error(f"OhDeere notification server error: {exc}")
        self.errorState = True
    except OhDeereClientError as exc:
        self.error(f"OhDeere notification request failed: {exc}")
        self.errorState = True
```

### Guards

- **Duplicate `finish()` calls:** the scan orchestrator's wind-down loop calls `finish()` on every module, possibly more than once. `self._complete_notified` prevents a duplicate Slack ping.
- **Duplicate ROOT events:** unlikely (ROOT fires once at scan start), but `self._start_notified` is defensive.
- **`client.disabled`:** silent no-op, matches every other OhDeere module.
- **Errors:** the module sets `errorState` on any OhDeere failure. This prevents further notifications during the same scan (so if auth fails on start, the complete notification doesn't also fail noisily). Every other OhDeere consumer uses the same pattern.
- **Scan target missing / no scanId:** both are defensively handled. The message degrades gracefully to `"Scan completed for this scan"` with no URL if either is unavailable.

### Why `.post()` not `.get()`

The helper already exposes `post(path, body, base_url, scope)` which serializes the dict to JSON and sets `Content-Type: application/json`. No helper changes needed.

## Testing

`test/unit/modules/test_sfp_ohdeere_notification.py`, 10 tests:

1. `opts`/`optdescs` key parity.
2. `watchedEvents == ["ROOT"]`, `producedEvents == []`.
3. Silent no-op when client disabled on both ROOT and finish().
4. ROOT event → one `client.post` call with `text` containing `🔎` and the target value.
5. Duplicate ROOT events → one `client.post` call only.
6. `finish()` after ROOT → two `client.post` calls total (one start, one complete); the complete message contains `✅`.
7. Duplicate `finish()` calls → only one complete notification.
8. `spiderfoot_ui_url` configured → message contains `/scaninfo?id=<scanId>` link; with it empty → no link fragment.
9. `slack_channel` configured → body has `channel` key; empty → body has no `channel` key.
10. `OhDeereAuthError` → `errorState = True`, `self.error(...)` called.

**Full-suite target:** baseline 1441 + 35 → **1451 + 35** after +10 new tests.

## Rollout

Single module, two commits (TDD failing tests, then implementation). Safe to merge whether or not credentials are set — disabled client means the module is a silent no-op in local dev.

Follow-ups (not in this spec):
- `CLAUDE.md` Module Inventory add to `FREE_NOAUTH_UNLIMITED`.
- Scan-summary stats in the complete message (counts by event type, duration, errorState modules) — needs access to scan-level info that `finish()` doesn't currently receive.
- Email notifications — blocked by narrower `notifications:slack:send` scope on our client; request a broader scope separately.

## Follow-ups enabled

- First module using `finish()` lifecycle hook. Establishes the pattern for future "end of scan" modules (e.g. a scan-summary report writer).
- Demonstrates `.post()` against the OhDeere client. Sixth consumer (after searxng, geoip, maps, wiki, search) — every helper method (`get`/`post`) is now exercised by real modules.
