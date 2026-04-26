# `sfp_ohdeere_notification` Richer Scan-Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing single-line scan-complete Slack ping with a multi-line markdown summary that includes scan duration, total/per-type event counts, and a top-5 list of correlation findings sorted by risk priority. Scan-start notification stays unchanged.

**Architecture:** Single-module modification of `modules/sfp_ohdeere_notification.py`. Add three private formatters (`_completion_message`, `_format_duration`, `_top_findings`) plus a `_get_db()` helper that mirrors the pattern in `sfp_ohdeere_llm_summary.py`. Wire them into `finish()`. On any DB-access failure, fall back to the existing terse line so notifications stay reliable.

**Tech Stack:** Python 3.7+, stdlib only (`collections.Counter`, `time`). No new deps. Reads via the existing `SpiderFootDb` instance attached to the plugin (`db.scanInstanceGet`, `db.scanResultEvent`, `db.scanCorrelationList`).

**Spec:** `docs/superpowers/specs/2026-04-26-sfp-ohdeere-notification-richer-design.md`

---

## File map

| Action | File |
|---|---|
| Modify | `modules/sfp_ohdeere_notification.py` (add helpers, rewire `finish()`, ~50 new lines) |
| Modify | `test/unit/modules/test_sfp_ohdeere_notification.py` (add 7 new tests; update one existing assertion) |
| Modify | `CLAUDE.md` (one-sentence update to the `sfp_ohdeere_notification` row) |
| Modify | `docs/superpowers/BACKLOG.md` (mark item shipped) |

---

## Task 1: Failing tests for the rich completion message

**Files:**
- Modify: `test/unit/modules/test_sfp_ohdeere_notification.py`

- [ ] **Step 1: Inspect existing assertion that locks in the old terse format**

Run: `grep -n "Scan completed" test/unit/modules/test_sfp_ohdeere_notification.py`
Expected: line 79 currently asserts `self.assertIn("Scan completed", body["text"])`. That substring will *still* match the new rich message (the headline is still "✅ Scan completed for X"). No update needed unless additional asserts on that test method check exact length — they don't.

- [ ] **Step 2: Append new test helpers + tests**

Append to `test/unit/modules/test_sfp_ohdeere_notification.py` (inside `TestModuleOhDeereNotification` class):

```python
    def _attach_db(self, module, instance=None, events=None, correlations=None):
        """Attach a fake SpiderFootDb to the module via the name-mangled slot.

        Defaults: instance row implies a 90s duration; no events; no findings.
        """
        db = mock.MagicMock()
        db.scanInstanceGet.return_value = instance if instance is not None else [
            "scan-name", "example.com",
            1700000000.0,  # created
            1700000000.0,  # started
            1700000090.0,  # ended (90s after start)
            "FINISHED",
        ]
        db.scanResultEvent.return_value = events if events is not None else []
        db.scanCorrelationList.return_value = (
            correlations if correlations is not None else []
        )
        # _get_db() prefers __sfdb__, falls back to _SpiderFootPlugin__sfdb__.
        module._SpiderFootPlugin__sfdb__ = db
        return db

    def _completion_body(self, client):
        """Return the body dict from the second post call (the completion one)."""
        complete_call = client.post.call_args_list[1]
        return complete_call.kwargs.get(
            "body", complete_call.args[1] if len(complete_call.args) > 1 else None,
        )

    def test_rich_completion_includes_duration_total_top_types_top_findings(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        # 6 events: 3 INTERNET_NAME, 2 EMAILADDR, 1 LINKED_URL_INTERNAL.
        # SpiderFootDb.scanResultEvent rows have event type at index 4.
        events = [
            ("h1", "sub.example.com", "example.com", "mod_a", "INTERNET_NAME"),
            ("h2", "alt.example.com", "example.com", "mod_a", "INTERNET_NAME"),
            ("h3", "x.example.com",   "example.com", "mod_a", "INTERNET_NAME"),
            ("h4", "a@example.com",   "example.com", "mod_b", "EMAILADDR"),
            ("h5", "b@example.com",   "example.com", "mod_b", "EMAILADDR"),
            ("h6", "https://example.com/", "example.com", "mod_c", "LINKED_URL_INTERNAL"),
        ]
        correlations = [
            (1, "Subdomain Takeover", "rule_st", "HIGH", "ST", "...", "...", 2),
            (2, "Open Email", "rule_oe", "MEDIUM", "OE", "...", "...", 1),
        ]
        self._attach_db(module, events=events, correlations=correlations)
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        self.assertIn("*Duration:* 1m 30s", text)
        self.assertIn("*Events:* 6", text)
        self.assertIn("*Top event types:*", text)
        self.assertIn("INTERNET_NAME: 3", text)
        self.assertIn("EMAILADDR: 2", text)
        self.assertIn("*Top findings:*", text)
        self.assertIn("[HIGH] Subdomain Takeover", text)
        self.assertIn("[MEDIUM] Open Email", text)

    def test_top_findings_capped_at_five_and_sorted_by_risk(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        # 10 correlations, deliberately scrambled risk levels.
        correlations = [
            (i, f"Finding {i}", "r", risk, "n", "d", "l", 1)
            for i, risk in enumerate([
                "LOW", "HIGH", "INFO", "MEDIUM", "HIGH",
                "LOW", "MEDIUM", "HIGH", "INFO", "LOW",
            ])
        ]
        self._attach_db(module, correlations=correlations)
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        # Count [HIGH], [MEDIUM], [LOW], [INFO] occurrences in the message.
        self.assertEqual(text.count("[HIGH]"), 3)   # all three HIGHs included
        self.assertEqual(text.count("[MEDIUM]"), 2)  # both MEDIUMs included
        self.assertEqual(text.count("[LOW]"), 0)    # cap hit before LOW
        self.assertEqual(text.count("[INFO]"), 0)   # cap hit before INFO

    def test_empty_scan_emits_zero_events_no_sections(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        self._attach_db(module, events=[], correlations=[])
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        self.assertIn("*Events:* 0", text)
        self.assertNotIn("*Top event types:*", text)
        self.assertNotIn("*Top findings:*", text)

    def test_db_failure_falls_back_to_terse_message(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        # No DB attached at all; _get_db() returns None.
        module.handleEvent(self._root_event())
        module.finish()

        # Completion notification still went out (call #2).
        self.assertEqual(client.post.call_count, 2)
        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        # The terse fallback is exactly the old single-line format.
        self.assertNotIn("*Duration:*", text)
        self.assertNotIn("*Events:*", text)
        self.assertFalse(module.errorState)

    def test_db_raises_falls_back_to_terse_message(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        db = mock.MagicMock()
        db.scanInstanceGet.side_effect = RuntimeError("db down")
        module._SpiderFootPlugin__sfdb__ = db
        module.handleEvent(self._root_event())
        module.finish()

        self.assertEqual(client.post.call_count, 2)
        text = self._completion_body(client)["text"]
        self.assertIn("Scan completed for example.com", text)
        self.assertNotIn("*Duration:*", text)
        self.assertFalse(module.errorState)

    def test_start_notification_unchanged_and_no_db_queries(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client)
        db = self._attach_db(module)
        module.handleEvent(self._root_event())

        # Start ping is exactly the old line.
        start_body = client.post.call_args_list[0].kwargs.get(
            "body", client.post.call_args_list[0].args[1])
        self.assertIn("\U0001F50E Scan started for example.com",
                      start_body["text"])
        # Start path must not query the DB.
        db.scanInstanceGet.assert_not_called()
        db.scanResultEvent.assert_not_called()
        db.scanCorrelationList.assert_not_called()

    def test_ui_url_link_appended_to_first_line_in_rich_message(self):
        client = mock.MagicMock()
        client.disabled = False
        client.post.return_value = {"delivered": True}
        _, module = self._module(client, opts={
            "spiderfoot_ui_url": "https://spiderfoot.example.test",
        })
        events = [("h1", "x", "y", "m", "INTERNET_NAME")]
        self._attach_db(module, events=events)
        module.handleEvent(self._root_event())
        module.finish()

        text = self._completion_body(client)["text"]
        first_line = text.splitlines()[0]
        self.assertIn(
            "https://spiderfoot.example.test/scaninfo?id=scan-abc-123",
            first_line,
        )
```

- [ ] **Step 3: Run to verify the new tests fail**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_notification.py -v`
Expected: 7 new tests fail (assertions about `*Duration:*`, `*Events:*`, etc. since the module hasn't been changed yet); existing tests still pass.

- [ ] **Step 4: Commit the failing tests**

```bash
git add test/unit/modules/test_sfp_ohdeere_notification.py
git commit -m "test: add failing tests for sfp_ohdeere_notification rich payload"
```

---

## Task 2: Implement the rich completion message

**Files:**
- Modify: `modules/sfp_ohdeere_notification.py`

- [ ] **Step 1: Add the imports**

Edit `modules/sfp_ohdeere_notification.py`. Add `Counter` import below the existing imports:

```python
from collections import Counter
```

(Place after `from spiderfoot.ohdeere_client import (...)` block.)

- [ ] **Step 2: Define the risk-priority constant**

Add as a module-level constant (between the imports and the class):

```python
_RISK_PRIORITY = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
_TOP_TYPES_N = 5
_TOP_FINDINGS_N = 5
```

- [ ] **Step 3: Add `_get_db` helper**

Add as a method on `sfp_ohdeere_notification` (place it just above `_notify`):

```python
    def _get_db(self):
        # __sfdb__ is the production attribute; tests inject via the
        # name-mangled fallback. Mirrors sfp_ohdeere_llm_summary._get_db.
        db = getattr(self, "__sfdb__", None)
        if db is None:
            return getattr(self, "_SpiderFootPlugin__sfdb__", None)
        return db
```

- [ ] **Step 4: Replace `finish()` with the rich-message version**

Replace the existing `finish()` method body. The new version computes the rich message; on any DB-access failure it falls back to the terse string.

```python
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

    def _completion_message(self, target: str) -> str:
        """Build the rich completion message, falling back to terse on DB error."""
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
            lines.append(f"*Duration:* {duration}  \u00b7  *Events:* {total_events}")

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
                        f"  \u2022 [{risk}] {title} \u2014 {event_count} {suffix}"
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
        if delta < 0 or delta != delta:  # negative or NaN
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
        """Return up to _TOP_FINDINGS_N (risk, title, event_count) tuples."""
        # Row columns: id, title, rule_id, rule_risk, rule_name, descr, logic, event_count.
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
```

- [ ] **Step 5: Run all tests to verify**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_notification.py -v`
Expected: all tests green (new 7 + the original ~10 still passing).

- [ ] **Step 6: Lint**

Run: `python3 -m flake8 modules/sfp_ohdeere_notification.py test/unit/modules/test_sfp_ohdeere_notification.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add modules/sfp_ohdeere_notification.py
git commit -m "sfp_ohdeere_notification: rich scan-complete payload (counts + findings)"
```

---

## Task 3: Loader smoke + repo-wide lint

**Files:** none — verification only.

- [ ] **Step 1: Loader smoke**

Run:

```bash
python3 -c "
from spiderfoot import SpiderFootHelpers
mods = SpiderFootHelpers.loadModulesAsDict('modules', ['sfp__stor_db.py', 'sfp__stor_stdout.py'])
m = mods['sfp_ohdeere_notification']
print('opts:', sorted(m['opts'].keys()))
print('produces:', m['provides'])
print('consumes:', m['consumes'])
"
```

Expected:
```
opts: ['notification_base_url', 'slack_channel', 'spiderfoot_ui_url']
produces: []
consumes: ['ROOT']
```

(Opts unchanged — no new module options were added per the spec.)

- [ ] **Step 2: Repo-wide lint**

Run: `python3 -m flake8 . --count`
Expected: `0`.

- [ ] **Step 3: Run touched + neighbouring tests**

Run:

```bash
python3 -m pytest \
  test/unit/modules/test_sfp_ohdeere_notification.py \
  test/unit/modules/test_sfp_ohdeere_llm_summary.py \
  test/unit/spiderfoot/test_ohdeere_client.py \
  -q --no-cov
```

Expected: all green.

- [ ] **Step 4: No commit** — verification only.

---

## Task 4: Docs — CLAUDE.md + BACKLOG.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/BACKLOG.md`

- [ ] **Step 1: Update CLAUDE.md table row**

Find this row in `CLAUDE.md`:

```
| `sfp_ohdeere_notification` | `notifications:slack:send` | `ROOT` event + `finish()` hook → no event-bus output; fires Slack pings at scan start + complete |
```

Replace with:

```
| `sfp_ohdeere_notification` | `notifications:slack:send` | `ROOT` event + `finish()` hook → no event-bus output; Slack ping at scan start, plus a rich scan-complete ping with duration, top event-type counts, and top-5 risk-sorted correlation findings |
```

- [ ] **Step 2: Update BACKLOG.md — promote item to "shipped"**

Find this section in `docs/superpowers/BACKLOG.md`:

```
### Notification module — richer scan-complete content
- **What:** extend `sfp_ohdeere_notification` to include event counts, duration, top-5 riskiest findings in the scan-complete Slack ping instead of just "Scan completed for X".
- **Blocker:** `finish()` doesn't receive scan-outcome context. Need to query SQLite (like `sfp_ohdeere_llm_summary` does) to get the stats.
- **Size:** small — adds ~30 lines.
- **Value:** replaces the current "dumb" completion ping with something actually informative.
```

Replace with:

```
### Notification module — richer scan-complete content — shipped 2026-04-26
- Replaces the single-line "✅ Scan completed for X" with a multi-line markdown payload: duration, total + top-5 event-type counts, top-5 risk-sorted correlation findings.
- Falls back to the terse line on any DB-access failure so notifications stay reliable.
- No new module options.
- Spec: `docs/superpowers/specs/2026-04-26-sfp-ohdeere-notification-richer-design.md`.
- Plan: `docs/superpowers/plans/2026-04-26-sfp-ohdeere-notification-richer.md`.
```

- [ ] **Step 3: Update the priority-table row**

Find this line in BACKLOG.md (in the "Summary by urgency" table):

```
| Medium | Richer `sfp_ohdeere_notification` completion payload |
```

Replace with:

```
| ~~Medium~~ Done | ~~Richer `sfp_ohdeere_notification` completion payload~~ — shipped 2026-04-26 |
```

- [ ] **Step 4: Verify**

Run: `grep -A 1 "richer scan-complete content — shipped" docs/superpowers/BACKLOG.md | head -3`
Expected: shows the "shipped 2026-04-26" line.

Run: `grep "Done.*Richer.*notification" docs/superpowers/BACKLOG.md`
Expected: the `~~Medium~~ Done | ~~Richer ...~~` row.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "docs: CLAUDE.md + BACKLOG.md — notification rich payload shipped"
```

---

## Task 5: Final verify

**Files:** none — verification only.

- [ ] **Step 1: Show the commit chain**

Run: `git log --oneline -8`
Expected: ~3 new commits — failing tests, impl, docs.

- [ ] **Step 2: Run focused tests one more time**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_notification.py -q --no-cov`
Expected: all green (~17 tests total).

- [ ] **Step 3: Done.** Report the commit list.

---

## Self-review

**Spec coverage:**

- "Architecture / single-module mod with three formatters + `_get_db()`" → Tasks 1-2.
- "DB access" methods (scanInstanceGet, scanResultEvent, scanCorrelationList) → Task 2 step 4.
- "Message format" (multi-line markdown shape, link on first line, top event types, top findings) → Task 2 step 4 + Task 1 step 2 tests.
- "Section rendering rules" (skip top-types when 0 events, skip findings when none, duration formatting cases) → Task 2 step 4 (`_format_duration` covers the < 60s, < 1h, >= 1h, unknown cases; the lines/skip logic is in `_completion_message`) + Task 1's `test_empty_scan_emits_zero_events_no_sections`.
- "Risk sort priority" (HIGH=3 ... INFO=0) → Task 2 step 2 `_RISK_PRIORITY` constant; Task 1's `test_top_findings_capped_at_five_and_sorted_by_risk`.
- "Error contract" (DB failure → terse fallback, no errorState) → Task 2 step 4 (`try`/`except` in `_completion_message`); Task 1's `test_db_failure_falls_back_to_terse_message` and `test_db_raises_falls_back_to_terse_message`. Notification POST errors are unchanged (existing `_notify` keeps its existing handlers).
- "Testing" — all 7 spec'd tests appear in Task 1.
- "Distribution / docs" — Task 4 covers CLAUDE.md row + BACKLOG.md.
- "Out of scope" — no new opts, no Block Kit, no scan-failed path. None added.

**Placeholder scan:** No "TBD" / "TODO" / "add error handling" / etc. Every code block is complete; every shell command has expected output.

**Type consistency:**
- `_get_db()` defined in Task 2 step 3, called once in Task 2 step 4 inside `_completion_message`.
- `_format_duration(instance) -> str` and `_top_findings(correlations) -> list` defined and called in the same edit (Task 2 step 4); names consistent.
- `_RISK_PRIORITY`, `_TOP_TYPES_N`, `_TOP_FINDINGS_N` — module-level constants defined in Task 2 step 2; referenced in `_top_findings` and `_completion_message`.
- `instance` row indices: spec says `[name, target, created, started, ended, status]` (verified against `db.scanInstanceGet` in `spiderfoot/db.py`). `_format_duration` uses `instance[3]` (started) and `instance[4]` (ended) — matches.
- `correlations` row indices: spec says `[id, title, rule_id, rule_risk, rule_name, rule_descr, rule_logic, event_count]` (verified against `db.scanCorrelationList` in `spiderfoot/db.py`). `_top_findings` uses `row[1]` (title), `row[3]` (risk), `row[7]` (event_count) — matches.
- Scan ID: `module.setScanId("scan-abc-123")` in the test fixture; `self.getScanId()` in the implementation. SpiderFoot built-ins, no naming drift.
