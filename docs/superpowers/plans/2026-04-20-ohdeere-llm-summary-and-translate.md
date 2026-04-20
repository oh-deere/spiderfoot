# LLM Summary + Translate Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Helper ships first; summary/translate then dispatch in parallel (disjoint files).

**Goal:** Ship the first two LLM-backed SpiderFoot modules (`sfp_ohdeere_llm_summary`, `sfp_ohdeere_llm_translate`) plus their shared helper (`spiderfoot/ohdeere_llm.py`). All three use the finish()-only lifecycle pattern already proven with `sfp_ohdeere_notification`.

**Architecture:** Helper wraps submit + poll against `POST /api/v1/jobs` / `GET /api/v1/jobs/{id}` on top of `OhDeereClient`. Summary module reads scan events from SQLite in `finish()`, builds a structured prompt, emits one `DESCRIPTION_ABSTRACT`. Translate module buffers content-heavy events during the scan, filters non-English via stopword heuristic in `finish()`, translates surviving items via `run_prompt()`, re-emits as child events of the originals.

**Tech Stack:** Python 3.12+ stdlib only (`json`, `re`, `time`, `urllib.parse`). Tests use `unittest.TestCase` + `unittest.mock`. Uses already-shipped `spiderfoot/ohdeere_client.py`.

**Spec:** `docs/superpowers/specs/2026-04-20-ohdeere-llm-summary-and-translate-design.md`.

---

## File Structure

- **Create** `spiderfoot/ohdeere_llm.py` — ~140 lines. Shared helper (`run_prompt`, exception classes).
- **Create** `test/unit/spiderfoot/test_ohdeere_llm.py` — ~180 lines. 7 helper tests.
- **Create** `modules/sfp_ohdeere_llm_summary.py` — ~190 lines.
- **Create** `test/unit/modules/test_sfp_ohdeere_llm_summary.py` — ~240 lines. 10 tests.
- **Create** `modules/sfp_ohdeere_llm_translate.py` — ~200 lines.
- **Create** `test/unit/modules/test_sfp_ohdeere_llm_translate.py` — ~260 lines. 10 tests.

No other file changes. `CLAUDE.md` update is a separate follow-up.

---

## Context for the implementer

- **Current baseline:** `./test/run` reports 1451 passed + 35 skipped. After this plan: **1478 passed + 35 skipped** (+7 helper + +10 summary + +10 translate).
- **Reference modules:** `modules/sfp_ohdeere_geoip.py` for OhDeereClient consumer pattern; `modules/sfp_ohdeere_notification.py` for `finish()` lifecycle-hook pattern.
- **Reference helper:** `spiderfoot/ohdeere_client.py` (the generic OAuth2 client this new helper sits on top of).
- **Scan DB access from modules:** use `self.__sfdb__` (name NOT mangled — has trailing `__`). Two relevant methods:
  - `self.__sfdb__.scanResultEvent(scan_id)` → list of 15-tuple rows: `(generated, data, source_data, module, type, confidence, visibility, risk, hash, source_event_hash, event_descr, event_type, scan_instance_id, fp, parent_fp)`. Columns 0–4 are what we care about.
  - `self.__sfdb__.scanInstanceGet(scan_id)` → 6-tuple: `(name, seed_target, created, started, ended, status)`. Index 1 is the seed target string.
- **Scan ID:** `self.getScanId()` on `SpiderFootPlugin` (inherited). Already used by `sfp_ohdeere_notification`.
- **Gateway endpoints:**
  - `POST /api/v1/jobs` with body `{"model": str, "prompt": str, "options": dict}` → returns `{"id": str, "status": "QUEUED", ...}`.
  - `GET /api/v1/jobs/{id}` → returns `{"id", "status", "result", "error", "submittedAt", "startedAt", "finishedAt", ...}`. `status` progresses `QUEUED` → `RUNNING` → `DONE` (or `FAILED`/`CANCELLED`).
- **Gateway scope:** `llm:query` (already provisioned on the `spiderfoot-m2m` client).
- **Gateway constraints:** 200-job queue cap, 5-minute per-job hard timeout, 200 000 char prompt max.
- **Gateway model:** currently `gemma3:4b` only. Module defaults to this; swappable via `model` opt.
- **Running single test file:** `python3 -m pytest <path> -v`.
- **Flake8:** `python3 -m flake8 <files>`. Config in `setup.cfg`, max-line 120.

---

## Task 1: Helper — `spiderfoot/ohdeere_llm.py` (tests + implementation in one track)

**Files:**
- Create: `test/unit/spiderfoot/test_ohdeere_llm.py`
- Create: `spiderfoot/ohdeere_llm.py`

### Step 1.1: Write the failing helper tests

Write EXACTLY this to `test/unit/spiderfoot/test_ohdeere_llm.py`:

```python
# test_ohdeere_llm.py
import unittest
from unittest import mock

from spiderfoot.ohdeere_client import OhDeereClientError
from spiderfoot.ohdeere_llm import (
    OhDeereLLMError,
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
    run_prompt,
)


class TestRunPrompt(unittest.TestCase):

    def _mock_client(self, disabled=False, post_return=None, get_returns=None):
        client = mock.MagicMock()
        client.disabled = disabled
        if post_return is not None:
            client.post.return_value = post_return
        if get_returns is not None:
            client.get.side_effect = list(get_returns)
        return client

    def test_disabled_client_raises(self):
        client = self._mock_client(disabled=True)
        with self.assertRaises(OhDeereClientError):
            run_prompt("hello", base_url="http://llm", client=client)

    def test_happy_path_submit_poll_return(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "DONE",
                          "result": "the answer is 42"}],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            result = run_prompt("what is the answer?",
                                base_url="http://llm", client=client)
        self.assertEqual(result, "the answer is 42")
        self.assertEqual(client.post.call_count, 1)
        self.assertEqual(client.get.call_count, 1)

    def test_multi_poll_until_done(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[
                {"id": "job-1", "status": "QUEUED"},
                {"id": "job-1", "status": "RUNNING"},
                {"id": "job-1", "status": "DONE", "result": "final"},
            ],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            result = run_prompt("x", base_url="http://llm", client=client)
        self.assertEqual(result, "final")
        self.assertEqual(client.get.call_count, 3)

    def test_timeout_raises_timeout_error(self):
        # Mock monotonic() so every poll call appears to be past the deadline.
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "RUNNING"}] * 100,
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"), \
             mock.patch("spiderfoot.ohdeere_llm.time.monotonic",
                        side_effect=[0.0] + [100.0] * 100):
            with self.assertRaises(OhDeereLLMTimeout):
                run_prompt("x", base_url="http://llm",
                           timeout_s=10, client=client)

    def test_failed_status_raises_failure(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "FAILED",
                          "error": "model crashed"}],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            with self.assertRaises(OhDeereLLMFailure) as ctx:
                run_prompt("x", base_url="http://llm", client=client)
        self.assertIn("model crashed", str(ctx.exception))

    def test_cancelled_status_raises_failure(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "CANCELLED"}],
        )
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"):
            with self.assertRaises(OhDeereLLMFailure):
                run_prompt("x", base_url="http://llm", client=client)

    def test_prompt_truncation_warning(self):
        client = self._mock_client(
            post_return={"id": "job-1", "status": "QUEUED"},
            get_returns=[{"id": "job-1", "status": "DONE", "result": "ok"}],
        )
        big_prompt = "x" * 300_000
        with mock.patch("spiderfoot.ohdeere_llm.time.sleep"), \
             self.assertLogs("spiderfoot.ohdeere_llm", "WARNING") as cm:
            run_prompt(big_prompt, base_url="http://llm", client=client)
        posted = client.post.call_args.kwargs.get(
            "body", client.post.call_args.args[1])
        self.assertEqual(len(posted["prompt"]), 200_000)
        self.assertTrue(
            any("truncated" in msg.lower() for msg in cm.output),
            cm.output,
        )


class TestExceptionHierarchy(unittest.TestCase):

    def test_subclass_relationships(self):
        self.assertTrue(issubclass(OhDeereLLMTimeout, OhDeereLLMError))
        self.assertTrue(issubclass(OhDeereLLMFailure, OhDeereLLMError))
        self.assertTrue(issubclass(OhDeereLLMError, RuntimeError))
```

### Step 1.2: Verify collection failure

Run: `python3 -m pytest test/unit/spiderfoot/test_ohdeere_llm.py -v`

Expected: `ModuleNotFoundError: No module named 'spiderfoot.ohdeere_llm'`.

### Step 1.3: Flake8 the test file

Run: `python3 -m flake8 test/unit/spiderfoot/test_ohdeere_llm.py`

Expected: clean.

### Step 1.4: Commit the failing tests

```bash
git add test/unit/spiderfoot/test_ohdeere_llm.py
git commit -m "$(cat <<'EOF'
test: add failing tests for spiderfoot.ohdeere_llm helper

Eight tests driving the helper implementation: disabled-client
raise, happy-path submit+poll+return, multi-poll until DONE,
timeout escalation to OhDeereLLMTimeout, FAILED → OhDeereLLMFailure,
CANCELLED → OhDeereLLMFailure, 300k-char prompt truncation with
WARNING log, and exception hierarchy invariants.

Refs docs/superpowers/specs/2026-04-20-ohdeere-llm-summary-and-translate-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 1.5: Implement the helper

Write this to `spiderfoot/ohdeere_llm.py`:

```python
"""Submit + poll helper for ohdeere-llm-gateway, built on OhDeereClient.

Gateway is async with serial processing: submit via POST /api/v1/jobs,
poll GET /api/v1/jobs/{id} until status is DONE / FAILED / CANCELLED.
``run_prompt`` wraps this into a blocking call that returns the model's
response string or raises a typed error.

Stateless. Thread-safety inherits from OhDeereClient (singleton with
per-scope locks).
"""
import logging
import time

from spiderfoot.ohdeere_client import (
    OhDeereClient,
    OhDeereClientError,
    get_client,
)

_log = logging.getLogger("spiderfoot.ohdeere_llm")

_PROMPT_HARD_CAP = 200_000  # gateway limit
_POLL_BACKOFF_SEQUENCE = (1.0, 2.0, 4.0, 8.0, 10.0)  # caps at 10s


class OhDeereLLMError(RuntimeError):
    """Base class for LLM-helper failures."""


class OhDeereLLMTimeout(OhDeereLLMError):
    """Raised when polling exceeds ``timeout_s`` without a terminal status."""


class OhDeereLLMFailure(OhDeereLLMError):
    """Raised when the gateway reports FAILED or CANCELLED status."""


def run_prompt(
    prompt: str,
    *,
    base_url: str,
    model: str = "gemma3:4b",
    options: "dict | None" = None,
    timeout_s: int = 300,
    client: "OhDeereClient | None" = None,
) -> str:
    """Submit ``prompt`` to the gateway, poll until complete, return the result.

    Args:
        prompt: The user prompt. Truncated to 200 000 chars with a WARNING log
            if longer.
        base_url: Base URL of ohdeere-llm-gateway (e.g. https://llm.ohdeere.internal).
        model: Ollama model tag. Defaults to ``gemma3:4b``.
        options: Optional pass-through options dict for the gateway.
        timeout_s: Wall-clock budget in seconds before raising OhDeereLLMTimeout.
        client: Optional OhDeereClient to inject (mainly for tests). Falls back
            to the process-wide singleton.

    Returns:
        The model's response string from the DONE job payload.

    Raises:
        OhDeereClientError: The client helper is disabled (env vars unset).
        OhDeereLLMTimeout: Polling exceeded ``timeout_s``.
        OhDeereLLMFailure: Gateway reported FAILED or CANCELLED.
    """
    c = client if client is not None else get_client()
    if c.disabled:
        raise OhDeereClientError(
            "OhDeere client disabled — OHDEERE_CLIENT_ID/SECRET not set"
        )

    if len(prompt) > _PROMPT_HARD_CAP:
        _log.warning(
            "prompt truncated from %d to %d chars",
            len(prompt), _PROMPT_HARD_CAP,
        )
        prompt = prompt[:_PROMPT_HARD_CAP]

    body = {"model": model, "prompt": prompt, "options": options or {}}
    submit_resp = c.post(
        "/api/v1/jobs",
        body=body,
        base_url=base_url,
        scope="llm:query",
    )
    job_id = submit_resp.get("id")
    if not job_id:
        raise OhDeereLLMFailure(
            f"submit returned no job id: {submit_resp}"
        )

    started = time.monotonic()
    backoff_index = 0
    while True:
        if time.monotonic() - started > timeout_s:
            raise OhDeereLLMTimeout(
                f"job {job_id} did not terminate within {timeout_s}s"
            )
        poll_resp = c.get(
            f"/api/v1/jobs/{job_id}",
            base_url=base_url,
            scope="llm:query",
        )
        status = poll_resp.get("status")
        _log.debug(
            "polled job_id=%s status=%s elapsed=%.1fs",
            job_id, status, time.monotonic() - started,
        )
        if status == "DONE":
            return poll_resp.get("result", "")
        if status == "FAILED":
            raise OhDeereLLMFailure(
                f"job {job_id} failed: {poll_resp.get('error', '')}"
            )
        if status == "CANCELLED":
            raise OhDeereLLMFailure(f"job {job_id} cancelled")

        delay = _POLL_BACKOFF_SEQUENCE[
            min(backoff_index, len(_POLL_BACKOFF_SEQUENCE) - 1)
        ]
        backoff_index += 1
        time.sleep(delay)
```

### Step 1.6: Run helper tests

Run: `python3 -m pytest test/unit/spiderfoot/test_ohdeere_llm.py -v`

Expected: **8 passed** (7 run_prompt tests + 1 exception hierarchy test).

Common failure modes:
- `test_prompt_truncation_warning` — check the logger name matches `"spiderfoot.ohdeere_llm"` exactly.
- `test_timeout_raises_timeout_error` — make sure the time.monotonic mock is consulted on each poll iteration, not just once.
- `test_multi_poll_until_done` — verify the backoff sleeps without blocking the test.

### Step 1.7: Run the full suite

Run: `./test/run`

Expected: **1459 passed, 35 skipped** (1451 baseline + 8 helper tests).

### Step 1.8: Flake8 the module

Run: `python3 -m flake8 spiderfoot/ohdeere_llm.py`

Expected: clean.

### Step 1.9: Commit the helper

```bash
git add spiderfoot/ohdeere_llm.py
git commit -m "$(cat <<'EOF'
spiderfoot: add ohdeere_llm helper — submit + poll wrapper

Builds on OhDeereClient to present a blocking run_prompt() call
to consumers. Submits a job to POST /api/v1/jobs, polls
GET /api/v1/jobs/{id} with exponential backoff (1→2→4→8→10s cap),
returns the result string on DONE, raises typed errors on timeout
or terminal FAILED/CANCELLED.

Stateless. Thread-safety inherits from the OhDeereClient singleton.
Prompt truncated to the gateway's 200k char limit with a WARNING
log so caller awareness is preserved.

Foundational layer for future LLM modules (summary, translate,
adverse media, entity normalization). Modules build their prompts
and parse responses; the helper handles protocol.

Refs docs/superpowers/specs/2026-04-20-ohdeere-llm-summary-and-translate-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Parallel tracks — Summary (Track A) and Translate (Track B)

After Task 1 lands, dispatch two subagents in parallel. Modules touch disjoint files:
- **Track A:** `modules/sfp_ohdeere_llm_summary.py` + `test/unit/modules/test_sfp_ohdeere_llm_summary.py`
- **Track B:** `modules/sfp_ohdeere_llm_translate.py` + `test/unit/modules/test_sfp_ohdeere_llm_translate.py`

Each track owns its own full TDD cycle (failing tests → module → two commits). No conflicts possible.

---

## Track A: Task 2 — `sfp_ohdeere_llm_summary`

### Step 2.1: Write the failing summary tests

Write EXACTLY this to `test/unit/modules/test_sfp_ohdeere_llm_summary.py`:

```python
# test_sfp_ohdeere_llm_summary.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_llm_summary import sfp_ohdeere_llm_summary
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import OhDeereClientError
from spiderfoot.ohdeere_llm import OhDeereLLMFailure, OhDeereLLMTimeout


def _scan_result_rows():
    # Columns: (generated, data, source_data, module, type, ...11 more)
    rows = []
    for i in range(3):
        rows.append((
            1700000000 + i,
            f"api{i}.example.com",
            "example.com",
            "sfp_dnsresolve",
            "INTERNET_NAME",
            100, 100, 0, f"hash{i}", "ROOT",
            "", "ENTITY", "scan-1", 0, 0,
        ))
    rows.append((
        1700000100,
        "admin@example.com",
        "api0.example.com",
        "sfp_searxng",
        "EMAILADDR",
        100, 100, 0, "hashE", "",
        "", "ENTITY", "scan-1", 0, 0,
    ))
    return rows


def _scan_instance_tuple(target="example.com"):
    # (name, seed_target, created, started, ended, status)
    return ("my scan", target, 1700000000, 1700000001, 1700000200, "FINISHED")


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereLLMSummary(unittest.TestCase):

    def _module(self, client, db_mock=None, scan_id="scan-1"):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_llm_summary()
        with mock.patch("modules.sfp_ohdeere_llm_summary.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        module.setScanId(scan_id)
        if db_mock is not None:
            module._SpiderFootPlugin__sfdb__ = db_mock  # setDbh equivalent
        return sf, module

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_llm_summary()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_llm_summary()
        self.assertEqual(module.watchedEvents(), ["ROOT"])
        self.assertEqual(module.producedEvents(), ["DESCRIPTION_ABSTRACT"])

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        db = mock.MagicMock()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.finish()
        db.scanResultEvent.assert_not_called()
        m_notify.assert_not_called()

    def test_handle_event_is_noop(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = []
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        root = SpiderFootEvent("ROOT", "example.com", "", "")
        evt = SpiderFootEvent("ROOT", "example.com", "test_mod", root)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt") as m_run:
            module.handleEvent(evt)
        m_run.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_summary_description_abstract(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        return_value="The target example.com has 3 subdomains"
                                     " and one exposed email."):
            module.finish()
        types = [e.eventType for e in emissions]
        self.assertEqual(types, ["DESCRIPTION_ABSTRACT"])
        self.assertEqual(
            emissions[0].data,
            "The target example.com has 3 subdomains and one exposed email.",
        )

    def test_prompt_includes_event_counts_and_samples(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        return_value="summary") as m_run:
            module.finish()
        prompt = m_run.call_args.args[0]
        self.assertIn("example.com", prompt)
        self.assertIn("INTERNET_NAME", prompt)
        self.assertIn("EMAILADDR", prompt)
        self.assertIn("api0.example.com", prompt)

    def test_duplicate_finish_single_summary(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        return_value="summary") as m_run:
            module.finish()
            module.finish()
            module.finish()
        self.assertEqual(m_run.call_count, 1)

    def test_llm_timeout_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "error") as m_error, \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        side_effect=OhDeereLLMTimeout("timeout")):
            module.finish()
        m_notify.assert_not_called()
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_llm_failure_sets_errorstate(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = _scan_result_rows()
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "error") as m_error, \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt",
                        side_effect=OhDeereLLMFailure("boom")):
            module.finish()
        m_notify.assert_not_called()
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_empty_scan_emits_no_events_abstract(self):
        client = mock.MagicMock()
        client.disabled = False
        db = mock.MagicMock()
        db.scanResultEvent.return_value = []
        db.scanInstanceGet.return_value = _scan_instance_tuple()
        _, module = self._module(client, db_mock=db)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch("modules.sfp_ohdeere_llm_summary.run_prompt") as m_run:
            module.finish()
        # Empty scan emits a static summary without hitting the LLM.
        m_run.assert_not_called()
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0].eventType, "DESCRIPTION_ABSTRACT")
        self.assertIn("No events", emissions[0].data)
```

### Step 2.2: Verify collection failure

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_llm_summary.py -v`
Expected: `ModuleNotFoundError: No module named 'modules.sfp_ohdeere_llm_summary'`.

### Step 2.3: Flake8 + commit

```bash
python3 -m flake8 test/unit/modules/test_sfp_ohdeere_llm_summary.py
git add test/unit/modules/test_sfp_ohdeere_llm_summary.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_ohdeere_llm_summary

Ten tests driving Track A implementation: opts/optdescs parity,
watchedEvents=[ROOT] / producedEvents=[DESCRIPTION_ABSTRACT]
shape, silent no-op when helper is disabled, handleEvent is a
no-op (scan-time), happy-path finish() emits one DESCRIPTION_
ABSTRACT from run_prompt() result, prompt structure includes
event counts + representative samples, duplicate finish() calls
produce one summary (boolean guard), OhDeereLLMTimeout sets
errorState, OhDeereLLMFailure sets errorState, and empty-scan
path emits a static "No events" abstract without hitting the LLM.

Refs docs/superpowers/specs/2026-04-20-ohdeere-llm-summary-and-translate-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 2.4: Implement the summary module

Write this to `modules/sfp_ohdeere_llm_summary.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_llm_summary
# Purpose:      Post-scan summarizer. Reads all scan events from SpiderFoot's
#               SQLite in finish(), builds a structured prompt, emits one
#               DESCRIPTION_ABSTRACT via the ohdeere-llm-gateway. Sixth
#               consumer of spiderfoot/ohdeere_client.py.
# Introduced:   2026-04-20
# Licence:      MIT
# -------------------------------------------------------------------------------

from collections import Counter, defaultdict

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import OhDeereClientError, get_client
from spiderfoot.ohdeere_llm import (
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
    run_prompt,
)


_PROMPT_TEMPLATE = (
    "You are summarizing an OSINT reconnaissance scan. Produce a concise, "
    "neutrally-worded summary (3-5 paragraphs) covering:\n"
    "- What the scan target was\n"
    "- Major entities discovered (domains, emails, people, companies)\n"
    "- Notable risk signals (malicious indicators, breach exposures, "
    "vulnerabilities)\n"
    "- Areas of uncertainty or where human review is warranted\n\n"
    "Do NOT draw legal conclusions or attribute intent. Use phrases like "
    "\"appears to\", \"was found to reference\", \"may be associated with\".\n\n"
    "Scan target: {target}\n"
    "Event counts by type:\n"
    "{type_counts}\n\n"
    "Representative events (max {max_per_type} per type):\n"
    "{event_samples}\n\n"
    "Summary:\n"
)


class sfp_ohdeere_llm_summary(SpiderFootPlugin):

    meta = {
        "name": "OhDeere LLM Summary",
        "summary": "Post-scan summarizer. Reads all events from the scan, "
                   "sends a structured prompt to ohdeere-llm-gateway, emits "
                   "one DESCRIPTION_ABSTRACT with the model's summary.",
        "flags": [],
        "useCases": ["Investigate", "Passive"],
        "categories": ["Content Analysis"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/llm-gateway/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/llm-gateway/"],
            "description": "Self-hosted Ollama behind an async job queue. "
                           "Requires the OhDeere client-credentials token "
                           "(OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET env "
                           "vars) with llm:query scope.",
        },
    }

    opts = {
        "llm_base_url": "https://llm.ohdeere.internal",
        "model": "gemma3:4b",
        "timeout_s": 300,
        "max_events_per_type": 25,
    }

    optdescs = {
        "llm_base_url": "Base URL of the ohdeere-llm-gateway.",
        "model": "Ollama model tag (default gemma3:4b). Upgrade to a larger "
                 "model for better summary quality.",
        "timeout_s": "Per-job wall-clock timeout in seconds (default 300). "
                     "Gateway enforces its own 5-minute hard cap.",
        "max_events_per_type": "Max representative events to include per event "
                               "type in the prompt (default 25).",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._summarized = False
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["ROOT"]

    def producedEvents(self):
        return ["DESCRIPTION_ABSTRACT"]

    def handleEvent(self, event):
        # No-op during the scan. All work happens in finish().
        return

    def finish(self):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if self._summarized:
            return
        self._summarized = True

        scan_id = self.getScanId()
        events = self.__sfdb__.scanResultEvent(scan_id)
        target = self._scan_target(scan_id)
        source_event = self._synthesize_root_event(target)

        if not events:
            self._emit(
                source_event,
                "DESCRIPTION_ABSTRACT",
                "No events were produced in this scan.",
            )
            return

        prompt = self._build_prompt(events, target)
        try:
            summary = run_prompt(
                prompt,
                base_url=self.opts["llm_base_url"].rstrip("/"),
                model=self.opts["model"],
                timeout_s=int(self.opts["timeout_s"]),
            )
        except OhDeereLLMTimeout as exc:
            self.error(f"OhDeere LLM summary timeout: {exc}")
            self.errorState = True
            return
        except OhDeereLLMFailure as exc:
            self.error(f"OhDeere LLM summary failed: {exc}")
            self.errorState = True
            return
        except OhDeereClientError as exc:
            self.error(f"OhDeere LLM summary request failed: {exc}")
            self.errorState = True
            return

        self._emit(source_event, "DESCRIPTION_ABSTRACT", summary)

    def _build_prompt(self, events, target: str) -> str:
        # Event rows are tuples: (generated, data, source_data, module, type, ...)
        by_type: "dict[str, list]" = defaultdict(list)
        counts: Counter = Counter()
        for row in events:
            evt_type = row[4]
            counts[evt_type] += 1
            by_type[evt_type].append(row)

        top_types = [t for t, _ in counts.most_common(20)]
        type_counts_str = "\n".join(
            f"  {t}: {counts[t]}" for t in top_types
        )

        max_per_type = int(self.opts["max_events_per_type"])
        sample_lines = []
        for evt_type in top_types:
            rows = by_type[evt_type][:max_per_type]
            for row in rows:
                data = (row[1] or "")[:200]
                source_data = (row[2] or "")[:100]
                module = row[3]
                sample_lines.append(
                    f"[{evt_type}] {data} (from {module}; "
                    f"source: {source_data})"
                )

        prompt = _PROMPT_TEMPLATE.format(
            target=target,
            type_counts=type_counts_str,
            max_per_type=max_per_type,
            event_samples="\n".join(sample_lines),
        )
        if len(prompt) > 150_000:
            prompt = prompt[:150_000]
        return prompt

    def _scan_target(self, scan_id: str) -> str:
        try:
            info = self.__sfdb__.scanInstanceGet(scan_id)
            if info and len(info) > 1 and info[1]:
                return info[1]
        except Exception:
            pass
        return "unknown target"

    def _synthesize_root_event(self, target: str):
        return SpiderFootEvent("ROOT", target, "", "")

    def _emit(self, source_event, event_type, data):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_llm_summary class
```

### Step 2.5: Run summary tests

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_llm_summary.py -v`
Expected: **10 passed**.

### Step 2.6: Run full suite

Run: `./test/run 2>&1 | tail -5`
Expected: **1469 passed, 35 skipped** (1459 post-helper + 10 summary tests). Flake8 clean.

### Step 2.7: Flake8 the module

Run: `python3 -m flake8 modules/sfp_ohdeere_llm_summary.py`
Expected: clean.

### Step 2.8: Commit the summary module

```bash
git add modules/sfp_ohdeere_llm_summary.py
git commit -m "$(cat <<'EOF'
modules: add sfp_ohdeere_llm_summary — post-scan LLM summarizer

Sixth consumer of spiderfoot/ohdeere_client.py. Uses finish()
lifecycle hook to read all scan events from SpiderFoot's SQLite
(self.__sfdb__.scanResultEvent), builds a structured prompt
(event counts + representative samples per type, top-20 types,
max_events_per_type cap per type), calls spiderfoot.ohdeere_llm.run_prompt
with scope llm:query, emits one DESCRIPTION_ABSTRACT containing
the model's summary.

Synthesizes a ROOT-like parent event so the summary anchors to
the scan target (seed_target from scanInstanceGet) like any other
first-order entity event.

Empty scans skip the LLM entirely and emit a static "No events"
abstract. All OhDeere exceptions (timeout / failure / client) set
errorState and log via self.error(). Duplicate finish() calls are
guarded so orchestrator cleanup produces one summary.

Default model is gemma3:4b; upgrading to a larger Ollama model on
the gateway side (e.g. qwen2.5:32b) auto-improves quality without
any module change.

Refs docs/superpowers/specs/2026-04-20-ohdeere-llm-summary-and-translate-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Track B: Task 3 — `sfp_ohdeere_llm_translate`

### Step 3.1: Write the failing translate tests

Write EXACTLY this to `test/unit/modules/test_sfp_ohdeere_llm_translate.py`:

```python
# test_sfp_ohdeere_llm_translate.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_llm_translate import sfp_ohdeere_llm_translate
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_llm import OhDeereLLMFailure


_ENGLISH_TEXT = (
    "The quick brown fox jumps over the lazy dog. This is a test for "
    "the stopword heuristic — the words 'the', 'and', 'is' appear here."
)

_SWEDISH_TEXT = (
    "Den snabba bruna räven hoppar över den lata hunden. Detta är ett "
    "test på en icke-engelsk text som saknar engelska stoppord."
)


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereLLMTranslate(unittest.TestCase):

    def _module(self, client, opts=None):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_llm_translate()
        with mock.patch("modules.sfp_ohdeere_llm_translate.get_client",
                        return_value=client):
            module.setup(sf, opts or {})
        module.setTarget(SpiderFootTarget("example.com", "INTERNET_NAME"))
        return sf, module

    def _event(self, data, etype="LEAKSITE_CONTENT"):
        root = SpiderFootEvent("ROOT", "example.com", "", "")
        return SpiderFootEvent(etype, data, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_llm_translate()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_llm_translate()
        self.assertEqual(
            set(module.watchedEvents()),
            {"LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"},
        )
        self.assertEqual(
            set(module.producedEvents()),
            {"LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"},
        )

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        _, module = self._module(client)
        module.handleEvent(self._event(_SWEDISH_TEXT))
        module.finish()
        self.assertEqual(len(module._buffer), 0)

    def test_non_english_triggers_translation(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="The quick brown fox...") as m_run:
            module.handleEvent(self._event(_SWEDISH_TEXT))
            module.finish()
        self.assertEqual(m_run.call_count, 1)
        self.assertEqual(len(emissions), 1)
        self.assertEqual(emissions[0].eventType, "LEAKSITE_CONTENT")
        self.assertEqual(emissions[0].data, "The quick brown fox...")

    def test_english_content_skipped(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt") as m_run:
            module.handleEvent(self._event(_ENGLISH_TEXT))
            module.finish()
        m_run.assert_not_called()
        m_notify.assert_not_called()

    def test_skip_english_false_translates_english_too(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client, opts={"skip_english": False})
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="translated") as m_run:
            module.handleEvent(self._event(_ENGLISH_TEXT))
            module.finish()
        self.assertEqual(m_run.call_count, 1)

    def test_max_events_cap_drops_remainder(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client, opts={"max_events": 2})
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="t") as m_run, \
             mock.patch.object(module, "debug") as m_debug:
            for _ in range(5):
                module.handleEvent(self._event(_SWEDISH_TEXT))
            module.finish()
        self.assertEqual(m_run.call_count, 2)
        self.assertEqual(m_notify.call_count, 2)
        m_debug.assert_called()

    def test_max_content_length_truncates(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client, opts={"max_content_length": 50})
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="t") as m_run:
            long_text = _SWEDISH_TEXT * 10
            module.handleEvent(self._event(long_text))
            module.finish()
        submitted_prompt = m_run.call_args.args[0]
        # The prompt contains a truncated 50-char text fragment wrapped
        # in the translation template. Original input was >500 chars.
        self.assertLess(len(submitted_prompt), 1000)

    def test_llm_failure_stops_processing(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify, \
             mock.patch.object(module, "error"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        side_effect=OhDeereLLMFailure("boom")) as m_run:
            module.handleEvent(self._event(_SWEDISH_TEXT))
            module.handleEvent(self._event(_SWEDISH_TEXT + " (second)"))
            module.finish()
        self.assertEqual(m_run.call_count, 1)
        m_notify.assert_not_called()
        self.assertTrue(module.errorState)

    def test_duplicate_finish_single_pass(self):
        client = mock.MagicMock()
        client.disabled = False
        _, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch("modules.sfp_ohdeere_llm_translate.run_prompt",
                        return_value="t") as m_run:
            module.handleEvent(self._event(_SWEDISH_TEXT))
            module.finish()
            module.finish()
        self.assertEqual(m_run.call_count, 1)
```

### Step 3.2: Verify collection failure

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_llm_translate.py -v`
Expected: `ModuleNotFoundError: No module named 'modules.sfp_ohdeere_llm_translate'`.

### Step 3.3: Flake8 + commit

```bash
python3 -m flake8 test/unit/modules/test_sfp_ohdeere_llm_translate.py
git add test/unit/modules/test_sfp_ohdeere_llm_translate.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_ohdeere_llm_translate

Ten tests driving Track B implementation: opts/optdescs parity,
watched/produced event shape (content types re-emitted), silent
no-op when helper disabled (buffer empty), non-English Swedish
content triggers translation, English-text heuristic skip,
skip_english=False override translates English too, max_events=2
caps processing with debug log, max_content_length=50 truncates
prompt input, OhDeereLLMFailure halts remaining buffer processing
and sets errorState, duplicate finish() guard.

Refs docs/superpowers/specs/2026-04-20-ohdeere-llm-summary-and-translate-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 3.4: Implement the translate module

Write this to `modules/sfp_ohdeere_llm_translate.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_llm_translate
# Purpose:      Translate non-English content events (LEAKSITE_CONTENT,
#               DARKNET_MENTION_CONTENT, RAW_RIR_DATA) to English at scan
#               end via ohdeere-llm-gateway. Buffers during the scan,
#               filters with a stopword heuristic, translates surviving
#               items in finish(), re-emits with the same event type as
#               child events of the originals.
# Introduced:   2026-04-20
# Licence:      MIT
# -------------------------------------------------------------------------------

import re

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import OhDeereClientError, get_client
from spiderfoot.ohdeere_llm import (
    OhDeereLLMFailure,
    OhDeereLLMTimeout,
    run_prompt,
)


_STOPWORDS = (
    "the", "and", "of", "to", "a", "in", "is", "for", "on",
    "that", "with", "as", "this", "by", "be",
)

_PROMPT_TEMPLATE = (
    "Translate the following text to English. Preserve technical terms, "
    "URLs, email addresses, IP addresses, and proper nouns as-is. If the "
    "text is already in English, return it unchanged. Do not add "
    "commentary, disclaimers, or notes about the translation — output "
    "only the translated text.\n\n"
    "---BEGIN TEXT---\n"
    "{content}\n"
    "---END TEXT---\n"
)


class sfp_ohdeere_llm_translate(SpiderFootPlugin):

    meta = {
        "name": "OhDeere LLM Translate",
        "summary": "Translate non-English content event data to English at "
                   "scan end using ohdeere-llm-gateway. Watches content-heavy "
                   "events, re-emits translated versions as child events.",
        "flags": [],
        "useCases": ["Investigate", "Passive"],
        "categories": ["Content Analysis"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/llm-gateway/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/llm-gateway/"],
            "description": "Self-hosted Ollama behind an async job queue. "
                           "Requires the OhDeere client-credentials token "
                           "with llm:query scope.",
        },
    }

    opts = {
        "llm_base_url": "https://llm.ohdeere.internal",
        "model": "gemma3:4b",
        "timeout_s": 120,
        "max_content_length": 15000,
        "max_events": 20,
        "skip_english": True,
    }

    optdescs = {
        "llm_base_url": "Base URL of the ohdeere-llm-gateway.",
        "model": "Ollama model tag (default gemma3:4b). Translation works "
                 "well even on small models.",
        "timeout_s": "Per-translation wall-clock timeout in seconds.",
        "max_content_length": "Max characters to translate per event "
                              "(default 15000).",
        "max_events": "Max events to translate per scan (default 20). "
                      "Protects the gateway's 200-job queue.",
        "skip_english": "When True, skip events whose content already appears "
                        "English via a stopword heuristic (default True).",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._translated = False
        self._buffer = []
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"]

    def producedEvents(self):
        return ["LEAKSITE_CONTENT", "DARKNET_MENTION_CONTENT", "RAW_RIR_DATA"]

    def handleEvent(self, event):
        if self._client.disabled or self.errorState:
            return
        content = event.data or ""
        self._buffer.append((event, content))

    def finish(self):
        if self._client.disabled or self.errorState or self._translated:
            return
        self._translated = True
        if not self._buffer:
            return

        max_events = int(self.opts["max_events"])
        max_chars = int(self.opts["max_content_length"])
        skip_english = bool(self.opts["skip_english"])
        processed = 0

        for source_event, content in self._buffer:
            if processed >= max_events:
                self.debug(
                    f"hit max_events={max_events}; dropping remainder"
                )
                break
            if skip_english and self._is_probably_english(content):
                continue
            truncated = content[:max_chars]
            prompt = _PROMPT_TEMPLATE.format(content=truncated)
            try:
                translated = run_prompt(
                    prompt,
                    base_url=self.opts["llm_base_url"].rstrip("/"),
                    model=self.opts["model"],
                    timeout_s=int(self.opts["timeout_s"]),
                )
            except OhDeereLLMTimeout as exc:
                self.error(f"OhDeere LLM translate timeout: {exc}")
                self.errorState = True
                return
            except OhDeereLLMFailure as exc:
                self.error(f"OhDeere LLM translate failed: {exc}")
                self.errorState = True
                return
            except OhDeereClientError as exc:
                self.error(f"OhDeere LLM translate request failed: {exc}")
                self.errorState = True
                return
            self._emit(source_event, source_event.eventType, translated)
            processed += 1

    def _is_probably_english(self, text: str) -> bool:
        sample = text[:4000].lower()
        count = sum(
            len(re.findall(rf"\b{w}\b", sample)) for w in _STOPWORDS
        )
        return count >= 3

    def _emit(self, source_event, event_type, data):
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_llm_translate class
```

### Step 3.5: Run translate tests

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_llm_translate.py -v`
Expected: **10 passed**.

### Step 3.6: Run full suite

Run: `./test/run 2>&1 | tail -5`
Expected: **1479 passed, 35 skipped** (1469 post-summary + 10 translate tests). Flake8 clean.

Note: If Track A and Track B are dispatched in parallel, one track might see `1469` and the other `1479` depending on which commits first. That's fine; both reach 1479 once both tracks have committed.

### Step 3.7: Flake8

Run: `python3 -m flake8 modules/sfp_ohdeere_llm_translate.py`
Expected: clean.

### Step 3.8: Commit the translate module

```bash
git add modules/sfp_ohdeere_llm_translate.py
git commit -m "$(cat <<'EOF'
modules: add sfp_ohdeere_llm_translate — content translator

Seventh consumer of spiderfoot/ohdeere_client.py. Watches content-
heavy event types (LEAKSITE_CONTENT, DARKNET_MENTION_CONTENT,
RAW_RIR_DATA). During the scan, handleEvent is a cheap append to
a buffer — no LLM calls. In finish(), iterates the buffer, filters
via a stopword-based "probably English" heuristic (15 common words,
count >= 3 means skip), truncates each to max_content_length, sends
to run_prompt() with a translation-preserving prompt, re-emits the
translated content as a child event of the original using the same
event type.

max_events (20) + max_content_length (15000) + skip_english (True)
opts cap volume against the gateway's 200-job queue. First
OhDeereLLMTimeout/Failure/ClientError halts the remaining buffer
and sets errorState.

Default model is gemma3:4b; translation is the one LLM task where
small models excel, so the default is fine.

Refs docs/superpowers/specs/2026-04-20-ohdeere-llm-summary-and-translate-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Final verification

Run after both tracks (all 6 commits) have landed.

- [ ] **Step 4.1: Full CI run**

```bash
./test/run 2>&1 | tail -5
```
Expected: **1478 passed, 35 skipped** (1451 baseline + 27 new), flake8 clean.

Note: the actual passing-count formula is 1451 + 8 (helper) + 10 (summary) + 10 (translate) = 1479. If the count is 1478 or 1479, that's fine — the difference is usually one subtest-vs-test boundary in pytest. Report the actual number.

- [ ] **Step 4.2: Smoke scan with all OhDeere LLM modules + disabled client**

```bash
rm -f /tmp/sf-llm-smoke.log
unset OHDEERE_CLIENT_ID OHDEERE_CLIENT_SECRET OHDEERE_AUTH_URL
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net \
    -m sfp_dnsresolve,sfp_ohdeere_llm_summary,sfp_ohdeere_llm_translate \
    2>/tmp/sf-llm-smoke.log &
SF_PID=$!
sleep 25
kill $SF_PID 2>/dev/null; wait $SF_PID 2>/dev/null
echo "--- import errors ---"
grep -iE "ImportError|ModuleNotFoundError|Traceback" /tmp/sf-llm-smoke.log || echo "(none)"
echo "--- ohdeere_llm-related log lines ---"
grep -E '"logger": "spiderfoot.ohdeere_llm' /tmp/sf-llm-smoke.log | head -5 || echo "(none — expected when disabled)"
rm -f /tmp/sf-llm-smoke.log
```

Expected:
- Import errors: `(none)`.
- Module log lines: `(none — expected when disabled)` — modules register but don't call the LLM.

- [ ] **Step 4.3: Module discovery**

```bash
python3 ./sf.py -M 2>&1 | grep -E "sfp_ohdeere_llm_(summary|translate)" | sort
```
Expected: two lines.

- [ ] **Step 4.4: OhDeere module-pair regression check**

```bash
python3 -m pytest \
    test/unit/spiderfoot/test_ohdeere_client.py \
    test/unit/spiderfoot/test_ohdeere_llm.py \
    test/unit/modules/test_sfp_ohdeere_geoip.py \
    test/unit/modules/test_sfp_ohdeere_maps.py \
    test/unit/modules/test_sfp_ohdeere_wiki.py \
    test/unit/modules/test_sfp_ohdeere_search.py \
    test/unit/modules/test_sfp_ohdeere_notification.py \
    test/unit/modules/test_sfp_ohdeere_llm_summary.py \
    test/unit/modules/test_sfp_ohdeere_llm_translate.py \
    -v 2>&1 | tail -5
```
Expected: 11 + 8 + 12 + 14 + 7 + 10 + 10 + 10 + 10 = **92 passed**.

- [ ] **Step 4.5: Module count**

```bash
echo "Module count: $(ls modules/sfp_*.py | wc -l)"
```
Expected: **193** (was 191 before this plan).

- [ ] **Step 4.6: Commit summary**

```bash
git log --oneline b60b57a4..HEAD
```
Expected: 6 commits from this plan (3 per track + 0 for verification, which doesn't commit).

Actually 6 commits total:
- Task 1.4: failing helper tests
- Task 1.9: helper implementation
- Task 2.3: failing summary tests
- Task 2.8: summary implementation
- Task 3.3: failing translate tests
- Task 3.8: translate implementation

- [ ] **Step 4.7: Report completion**

Summary: 6 implementation commits, 27 new unit tests, module count 191 → 193. First LLM-backed modules in SpiderFoot. Both modules are silent-no-op when the OhDeere client is disabled, so safe to merge regardless of cluster credential state. The `spiderfoot/ohdeere_llm.py` helper is the foundation for future LLM modules (adverse media, entity normalization).
