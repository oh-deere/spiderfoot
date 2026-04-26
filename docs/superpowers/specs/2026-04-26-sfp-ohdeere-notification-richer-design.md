# `sfp_ohdeere_notification` — Richer scan-complete payload

**Status:** Design (2026-04-26)
**Backlog item:** "Notification module — richer scan-complete content" (BACKLOG.md, Medium priority).
**Author:** Claude (with Ola)

## Goal

Replace the current single-line scan-complete Slack ping (`✅ Scan completed for example.com`) with a multi-line markdown summary that includes scan duration, total/per-type event counts, and a top-5 list of correlation findings sorted by risk priority. The change is always-on (no opt-in flag) — the cost of the richer message is small and there's no scenario where the terse line is preferable.

## Non-goals

- No Slack Block Kit payload. Sticking with the existing `{text: "..."}` shape so the gateway and any non-Slack channel handler keeps working.
- No opt-in flag (`rich_completion=...`) — YAGNI. If anyone needs the terse line back, an opt is a 5-line addition later.
- No change to the scan-*start* notification. That message ("🔎 Scan started for X") stays exactly as is.
- No new event types in the registry.
- No new module options.
- No correlation-rule changes — we read whatever the existing rules already produced.

## Architecture

Single-module modification of `modules/sfp_ohdeere_notification.py`. Add private helpers, wire them into `finish()`. Reuses the DB-access pattern already proven in `sfp_ohdeere_llm_summary.py` (lazy `_get_db()` + `db.scanInstanceGet` + `db.scanResultEvent` + `db.scanCorrelationList`).

```
finish()
  ↓
collect: scan_id, target, instance row, events list, correlations list
  ↓
build text via _completion_message(...)
  ↓ (on DB error → fallback to terse "✅ Scan completed for X")
self._notify(text)
```

The fallback path keeps the notification reliable even if a DB query unexpectedly fails — the operator still gets a ping; only the enrichment is lost.

## DB access

| Method | Returns | Used for |
|---|---|---|
| `db.scanInstanceGet(scan_id)` | `[name, target, created, started, ended, status]` | Target string, duration calc (`ended - started`) |
| `db.scanResultEvent(scan_id)` | rows of events; row[4] is event type | `Counter` over event types for total + per-type counts |
| `db.scanCorrelationList(scan_id)` | rows of correlations including `rule_risk`, `title`, `event_count` | Top-5 findings sorted by risk |

`_get_db()` mirrors the helper in `sfp_ohdeere_llm_summary.py` (handles the name-mangled `__sfdb__` slot and the test-injection fallback).

## Message format

Single text body, multi-line markdown, Slack-renders correctly. Schematic:

```
✅ Scan completed for {target}
*Duration:* {dur}  ·  *Events:* {total_events}
*Top event types:*
  • {TYPE_A}: {count}
  • {TYPE_B}: {count}
  • ... (up to 5)
*Top findings:*
  • [{RISK}] {title} — {event_count} event(s)
  • ... (up to 5, sorted by risk priority)
```

If `_append_scan_link` has a `spiderfoot_ui_url` set, the existing `(URL)` suffix is appended to the *first line* (matching current behavior — the link goes on the headline, not at the end of a multi-line block).

### Section rendering rules

- **Top event types**: top-5 by count from the event-type Counter. Skip the section entirely if `total_events == 0` (replace with a single line `*Events:* 0`).
- **Top findings**: top-5 by risk priority (HIGH > MEDIUM > LOW > INFO; ties broken by title alphabetical). Each line: `[RISK] title — N event(s)`. Skip the entire section if there are zero correlations.
- **Duration formatting**:
  - `< 60s` → `"23s"`
  - `< 1h` → `"12m 34s"`
  - `>= 1h` → `"1h 5m 23s"`
  - Negative or unparseable → `"unknown"`

### Risk sort priority

`{"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}`. Anything else (rare) sorts as 0.

## Error contract

| Failure | Behavior |
|---|---|
| DB queries raise / return None / `_get_db()` returns None | Catch broadly; fall back to terse `"✅ Scan completed for {target}"`; debug-log the cause; do **not** trip `errorState`. The notification still goes out. |
| `OhDeereAuthError` / `OhDeereServerError` / `OhDeereClientError` from the actual notification POST | Existing behavior — `self.error(...)` + `errorState = True`. Unchanged. |
| Slack channel rejects the rich message | Same as above — handled by existing notification code. We don't pre-validate. |

## Testing

Tests live in `test/unit/modules/test_sfp_ohdeere_notification.py`. Add ~6 new tests on top of the existing suite:

1. **Rich completion message includes duration, total events, top event types, top findings** — set up a fake `db` returning a populated instance, 3 event-type buckets, 2 correlations; assert the emitted POST body's `text` field contains the duration string, the total count, the top type names, and the [RISK] tags.
2. **Top-5 cap on findings** — 10 correlations in DB → only 5 lines in the message; assert highest-risk ones win the cut.
3. **Risk sort order** — mixed risks → ordering is HIGH, MEDIUM, LOW, INFO regardless of insertion order.
4. **Empty scan** (no events, no correlations) → message is `"✅ Scan completed for X\n*Events:* 0"` with neither types section nor findings section.
5. **DB unavailable / raises** → falls back to terse `"✅ Scan completed for X"`; `errorState` is False; `_notify` was still called once.
6. **`scan-started` notification unchanged** — regression test that `handleEvent(ROOT)` still emits the exact existing 1-line "🔎 Scan started for X" body, no DB queries triggered.
7. **`spiderfoot_ui_url` link still appended** — when the opt is set, the URL appears on the first line of the rich message (not after the findings list).

## Distribution / docs

- No new Python deps.
- No Dockerfile change.
- No new env vars.
- CLAUDE.md: update the `sfp_ohdeere_notification` row in the OhDeere consumer-modules table to mention the rich payload (one-sentence change). No structural change to the table.
- BACKLOG.md: mark "Notification module — richer scan-complete content" shipped 2026-04-26.

## Out of scope (explicitly deferred)

- Configurable top-N (`top_findings_n`, `top_types_n` opts). Default 5 is fine; revisit if anyone asks.
- Slack Block Kit / attachments / colour-coded sections. Not portable across channels.
- A separate "scan-failed" notification path. Existing module ignores failure status; that's a separate, smaller spec.
- Per-event-type or per-finding deep-link URLs into the SpiderFoot UI. The single scan-link suffix is enough for one-click drill-in.
