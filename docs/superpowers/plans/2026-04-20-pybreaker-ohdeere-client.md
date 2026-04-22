# `pybreaker` circuit breaker on `ohdeere_client` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-scope `pybreaker.CircuitBreaker` to `OhDeereClient` so repeated OhDeere service outages short-circuit after `fail_max=5` consecutive failures for a `reset_timeout=60s` cooldown. Zero changes to the 7 `sfp_ohdeere_*` consumer modules.

**Architecture:** 4 tasks. Dependency install + rename-only refactor first (keeps existing tests green), then TDD the breaker behavior with a new test file, then docs close-out.

**Tech Stack:** Python 3.12 + pybreaker 1.x (MIT, zero transitive deps).

**Spec:** `docs/superpowers/specs/2026-04-20-pybreaker-ohdeere-client-design.md`.

---

## File Structure

### Backend
- **Modify** `requirements.txt` — add `pybreaker>=1.0`.
- **Modify** `spiderfoot/ohdeere_client.py` — rename `_request` → `_request_unprotected`; add `_breakers` dict + `_breaker_for_scope()` helper + new `_request()` wrapper; add `fail_max` + `reset_timeout` constructor kwargs.

### Tests
- **Create** `test/unit/test_ohdeere_client_breaker.py` — 6 focused tests covering breaker state transitions.

### Docs
- **Modify** `CLAUDE.md` — brief note in the OhDeere integration section about the circuit breaker.
- **Modify** `docs/superpowers/BACKLOG.md` — mark pybreaker item shipped.

---

## Context for the implementer

- **Branch:** master, direct commits. HEAD is `37ba6275` (this milestone's spec commit).
- **Baseline:** 71 Vitest + 16 Playwright + flake8 clean + 1464 pytest + 34 skipped.
- **`OhDeereClient`** lives at `spiderfoot/ohdeere_client.py`. Read the current shape before refactoring — confirmed during brainstorming:
  - `_tokens: dict[str, tuple[str, float]]` — per-scope token cache (scope → (token, expires_at)).
  - `_scope_locks: dict[str, threading.Lock]` — per-scope refresh serialization.
  - `_scope_lock_meta: threading.Lock` — guards `_scope_locks` dict.
  - `_request(method, url, scope, body, timeout)` — public path; handles token lifecycle + 401 retry-with-force-refresh + calls `_issue_request` for the actual HTTP.
  - `_issue_request` raises `OhDeereAuthError` (401) / `OhDeereServerError` (5xx or network) / `OhDeereClientError` (other 4xx).
  - `_refresh_token(scope)` raises the same three exception types for token-endpoint failures.
- **Singleton**: `get_client()` returns a process-wide `OhDeereClient` via double-checked locking. The new constructor kwargs (`fail_max`, `reset_timeout`) default to the module constants, so `get_client()` keeps working unchanged.
- **Existing unit tests**: `test/unit/test_ohdeere_client.py` (~20 tests, mostly using `monkeypatch.setattr(urllib.request, 'urlopen', ...)` to inject responses). With `fail_max=5` default, none of those tests trip the circuit — each test exercises one request.
- **pybreaker API quick-reference**:
  - `breaker = CircuitBreaker(fail_max=N, reset_timeout=T, exclude=[ExcType, ...], name='...')`.
  - `breaker.call(fn, *args, **kwargs)` invokes `fn` via the breaker; raises `CircuitBreakerError` when open, otherwise re-raises any exception the fn raised.
  - `exclude=` takes exception *classes* whose instances pass through without counting toward the trip.
  - pybreaker uses `time.monotonic()` internally; tests can `time.sleep(reset_timeout + 0.01)` to cross into half-open.

---

## Task 1: Add `pybreaker` dependency + verify install

**Files:**
- Modify: `requirements.txt` — add `pybreaker>=1.0`.

### Step 1: Inspect requirements.txt format

```bash
head -20 /Users/olahjort/Projects/OhDeere/spiderfoot/requirements.txt
```

Take a look at how other deps are pinned (exact, minimum, range). Match the prevailing style.

### Step 2: Add `pybreaker`

Append a line to `requirements.txt`:

```
pybreaker>=1.0
```

Keep alphabetical ordering if the file is alphabetical; otherwise append at the bottom. Read the file to decide.

### Step 3: Install locally

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
pip3 install pybreaker>=1.0
```

Verify import works:

```bash
python3 -c "import pybreaker; print(pybreaker.__version__)"
```

Expected: a version string (1.0.x or later).

### Step 4: Run pytest

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1464 passed, 34 skipped** (unchanged — we haven't added any tests yet).

### Step 5: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add requirements.txt
git commit -m "$(cat <<'EOF'
ohdeere_client: add pybreaker dependency

Prep step for adding a per-scope circuit breaker to
OhDeereClient. MIT-licensed, zero transitive deps,
actively maintained.

Refs docs/superpowers/specs/2026-04-20-pybreaker-ohdeere-client-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Rename-only refactor `_request` → `_request_unprotected`

**Files:**
- Modify: `spiderfoot/ohdeere_client.py` — pure rename, no behavior change.

### Step 1: Locate the method

```bash
grep -n "def _request\|def _issue_request\|self\._request(" /Users/olahjort/Projects/OhDeere/spiderfoot/spiderfoot/ohdeere_client.py
```

You'll find:
- `def _request(self, method, url, scope, body, timeout) -> dict:` — line ~129
- Callers: `self._request("GET", ...)` and `self._request("POST", ...)` from `get()` / `post()`.

### Step 2: Rename `_request` to `_request_unprotected`

Edit `spiderfoot/ohdeere_client.py`:

1. Change the method signature:
   ```python
   def _request_unprotected(self, method: str, url: str, scope: str,
                            body: dict | None, timeout: int) -> dict:
   ```
2. Update the docstring's first line to reflect the new name if present (the existing method has no docstring; skip).

### Step 3: Add a placeholder `_request` that delegates

Directly above the renamed method, insert the new `_request` that (for now) just forwards to `_request_unprotected`. This is the shell we'll wrap with pybreaker in Task 3.

```python
def _request(self, method: str, url: str, scope: str,
             body: dict | None, timeout: int) -> dict:
    """Public request path — no circuit breaker yet (Task 3).

    Delegates to _request_unprotected until the breaker wrapper
    is added.
    """
    return self._request_unprotected(method, url, scope, body, timeout)
```

### Step 4: Verify callers still work

```bash
grep -n "self\._request(" /Users/olahjort/Projects/OhDeere/spiderfoot/spiderfoot/ohdeere_client.py
```

Expected: two callers — `get()` and `post()` — both call `self._request(...)`, which now delegates. No caller changes needed.

### Step 5: Run the existing ohdeere_client tests

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest test/unit/test_ohdeere_client.py -v 2>&1 | tail -10
```

Expected: all pass — the rename is pure indirection.

### Step 6: Run the full suite

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1464 passed, 34 skipped**.

### Step 7: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add spiderfoot/ohdeere_client.py
git commit -m "$(cat <<'EOF'
ohdeere_client: rename _request -> _request_unprotected

Pure rename + add a thin _request wrapper that currently just
delegates. Task 3 wraps that wrapper with pybreaker.call() for
per-scope circuit-breaker protection.

No behavior change. All existing tests pass unchanged.

Refs docs/superpowers/specs/2026-04-20-pybreaker-ohdeere-client-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: TDD the breaker — 6 tests + implementation

**Files:**
- Create: `test/unit/test_ohdeere_client_breaker.py` — 6 failing tests.
- Modify: `spiderfoot/ohdeere_client.py` — add breaker wiring; watch tests pass.

### Step 1: Write the failing test file

Create `/Users/olahjort/Projects/OhDeere/spiderfoot/test/unit/test_ohdeere_client_breaker.py`:

```python
"""Unit tests for OhDeereClient's per-scope circuit breaker.

Each test stubs _request_unprotected to inject controlled
exceptions or success payloads and asserts the breaker's state
machine behaves as expected.
"""
import time
import unittest
from unittest.mock import MagicMock

from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClient,
    OhDeereClientError,
    OhDeereServerError,
)


def _make_client(*, fail_max: int = 2, reset_timeout: float = 60.0) -> OhDeereClient:
    """Build a fresh OhDeereClient with env vars set so .disabled is False."""
    client = OhDeereClient(fail_max=fail_max, reset_timeout=reset_timeout)
    # Bypass the env-var check; tests don't hit the real token endpoint.
    client._client_id = "test-client-id"
    client._client_secret = "test-client-secret"
    return client


class TestOhDeereClientBreaker(unittest.TestCase):

    def test_breaker_opens_after_fail_max_server_errors(self):
        """After fail_max consecutive OhDeereServerErrors, the next call
        short-circuits without invoking _request_unprotected."""
        client = _make_client(fail_max=2)
        mock = MagicMock(side_effect=OhDeereServerError("boom"))
        client._request_unprotected = mock  # type: ignore[method-assign]

        for _ in range(2):
            with self.assertRaises(OhDeereServerError):
                client.get("/x", base_url="https://svc", scope="test:read")

        # Third call should short-circuit — _request_unprotected not called again.
        with self.assertRaises(OhDeereServerError) as exc_ctx:
            client.get("/x", base_url="https://svc", scope="test:read")
        self.assertIn("circuit open", str(exc_ctx.exception))
        self.assertEqual(mock.call_count, 2)

    def test_breaker_ignores_auth_errors(self):
        """OhDeereAuthError does not count toward the trip."""
        client = _make_client(fail_max=2)
        mock = MagicMock(side_effect=OhDeereAuthError("bad creds"))
        client._request_unprotected = mock  # type: ignore[method-assign]

        for _ in range(6):
            with self.assertRaises(OhDeereAuthError):
                client.get("/x", base_url="https://svc", scope="test:read")

        self.assertEqual(mock.call_count, 6)

    def test_breaker_ignores_client_errors(self):
        """OhDeereClientError (generic non-5xx non-auth) does not count."""
        client = _make_client(fail_max=2)
        mock = MagicMock(side_effect=OhDeereClientError("bad request"))
        client._request_unprotected = mock  # type: ignore[method-assign]

        for _ in range(6):
            with self.assertRaises(OhDeereClientError):
                client.get("/x", base_url="https://svc", scope="test:read")

        self.assertEqual(mock.call_count, 6)

    def test_breaker_recovers_after_reset_timeout(self):
        """After reset_timeout, a successful call closes the circuit."""
        client = _make_client(fail_max=2, reset_timeout=0.05)
        outcomes = [
            OhDeereServerError("boom"),
            OhDeereServerError("boom"),
            {"ok": True},
        ]
        mock = MagicMock(side_effect=outcomes)
        client._request_unprotected = mock  # type: ignore[method-assign]

        for _ in range(2):
            with self.assertRaises(OhDeereServerError):
                client.get("/x", base_url="https://svc", scope="test:read")

        # Circuit is now open; immediate call short-circuits.
        with self.assertRaises(OhDeereServerError):
            client.get("/x", base_url="https://svc", scope="test:read")
        self.assertEqual(mock.call_count, 2)

        # Wait out the reset timeout.
        time.sleep(0.1)

        # Next call goes through (half-open → closed on success).
        result = client.get("/x", base_url="https://svc", scope="test:read")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock.call_count, 3)

    def test_per_scope_isolation(self):
        """Tripping one scope's breaker doesn't open others."""
        client = _make_client(fail_max=2)

        # Stub that returns server error for geoip:read and success for llm:query.
        def _side_effect(method, url, scope, body, timeout):
            if scope == "geoip:read":
                raise OhDeereServerError("geoip down")
            return {"scope": scope}

        mock = MagicMock(side_effect=_side_effect)
        client._request_unprotected = mock  # type: ignore[method-assign]

        # Trip geoip:read.
        for _ in range(2):
            with self.assertRaises(OhDeereServerError):
                client.get("/x", base_url="https://geoip", scope="geoip:read")

        # Third geoip:read call short-circuits — call_count stays at 2 for geoip.
        with self.assertRaises(OhDeereServerError):
            client.get("/x", base_url="https://geoip", scope="geoip:read")
        geoip_calls = [
            c for c in mock.call_args_list if c.args[2] == "geoip:read"
        ]
        self.assertEqual(len(geoip_calls), 2)

        # llm:query still works — independent circuit.
        result = client.post(
            "/x", body={}, base_url="https://llm", scope="llm:query",
        )
        self.assertEqual(result, {"scope": "llm:query"})

    def test_circuit_open_surfaces_as_ohdeere_server_error(self):
        """When circuit is open, the error raised is OhDeereServerError
        (not pybreaker.CircuitBreakerError) and mentions the scope."""
        client = _make_client(fail_max=2)
        mock = MagicMock(side_effect=OhDeereServerError("boom"))
        client._request_unprotected = mock  # type: ignore[method-assign]

        for _ in range(2):
            with self.assertRaises(OhDeereServerError):
                client.get("/x", base_url="https://svc", scope="my:scope")

        with self.assertRaises(OhDeereServerError) as exc_ctx:
            client.get("/x", base_url="https://svc", scope="my:scope")

        msg = str(exc_ctx.exception)
        self.assertIn("circuit open", msg)
        self.assertIn("my:scope", msg)


if __name__ == "__main__":
    unittest.main()
```

### Step 2: Run the tests — expect FAIL

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest test/unit/test_ohdeere_client_breaker.py -v 2>&1 | tail -30
```

Expected: all 6 tests fail because:
- `OhDeereClient.__init__` doesn't accept `fail_max` / `reset_timeout` kwargs.
- No circuit breaker is wired into the `_request` method.

Capture the failure message to confirm the TypeError about the constructor kwargs. Good — the tests are probing actual breaker behavior.

### Step 3: Add breaker wiring to `ohdeere_client.py`

Open `/Users/olahjort/Projects/OhDeere/spiderfoot/spiderfoot/ohdeere_client.py`.

**3a.** Add `pybreaker` import at the top, after the existing `urllib.request` import:

```python
import pybreaker
```

**3b.** Add module-level constants after `_TOKEN_REFRESH_BUFFER`:

```python
_DEFAULT_FAIL_MAX = 5
_DEFAULT_RESET_TIMEOUT = 60.0  # seconds
```

**3c.** Update the `OhDeereClient.__init__` signature + body:

Before:
```python
def __init__(self) -> None:
    self._client_id = os.environ.get("OHDEERE_CLIENT_ID", "")
    self._client_secret = os.environ.get("OHDEERE_CLIENT_SECRET", "")
    self._auth_url = os.environ.get("OHDEERE_AUTH_URL", _DEFAULT_AUTH_URL)
    self._tokens: dict[str, tuple[str, float]] = {}
    self._scope_locks: dict[str, threading.Lock] = {}
    self._scope_lock_meta = threading.Lock()
```

After:
```python
def __init__(
    self,
    *,
    fail_max: int = _DEFAULT_FAIL_MAX,
    reset_timeout: float = _DEFAULT_RESET_TIMEOUT,
) -> None:
    self._client_id = os.environ.get("OHDEERE_CLIENT_ID", "")
    self._client_secret = os.environ.get("OHDEERE_CLIENT_SECRET", "")
    self._auth_url = os.environ.get("OHDEERE_AUTH_URL", _DEFAULT_AUTH_URL)
    self._tokens: dict[str, tuple[str, float]] = {}
    self._scope_locks: dict[str, threading.Lock] = {}
    self._scope_lock_meta = threading.Lock()
    self._breakers: dict[str, pybreaker.CircuitBreaker] = {}
    self._fail_max = fail_max
    self._reset_timeout = reset_timeout
```

**3d.** Add `_breaker_for_scope` helper — place it right after the existing `_lock_for_scope` method:

```python
def _breaker_for_scope(self, scope: str) -> pybreaker.CircuitBreaker:
    """Return the per-scope CircuitBreaker, creating it on first call.

    Guarded by _scope_lock_meta to make concurrent first-time access
    safe. Trips only on OhDeereServerError (network + 5xx); the
    auth / 4xx exception types pass through via `exclude`.
    """
    with self._scope_lock_meta:
        breaker = self._breakers.get(scope)
        if breaker is None:
            breaker = pybreaker.CircuitBreaker(
                fail_max=self._fail_max,
                reset_timeout=self._reset_timeout,
                exclude=[OhDeereAuthError, OhDeereClientError],
                name=f"ohdeere:{scope}",
            )
            self._breakers[scope] = breaker
        return breaker
```

**3e.** Replace the thin `_request` wrapper (the one added in Task 2) with the actual breaker-protected version:

```python
def _request(self, method: str, url: str, scope: str,
             body: dict | None, timeout: int) -> dict:
    """Public request path — protected by a per-scope circuit breaker.

    The breaker opens after fail_max consecutive OhDeereServerError
    raises and short-circuits further calls for reset_timeout seconds.
    OhDeereAuthError and OhDeereClientError pass through without
    contributing to the trip (config issues, not service outages).
    """
    breaker = self._breaker_for_scope(scope)
    try:
        return breaker.call(
            self._request_unprotected, method, url, scope, body, timeout,
        )
    except pybreaker.CircuitBreakerError as exc:
        raise OhDeereServerError(
            f"circuit open for scope={scope} "
            f"(cooldown {self._reset_timeout:.0f}s)"
        ) from exc
```

### Step 4: Run the breaker tests — expect PASS

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
python3 -m pytest test/unit/test_ohdeere_client_breaker.py -v 2>&1 | tail -15
```

Expected: all 6 pass.

If any fail, read the error carefully. Common gotchas:
- `time.sleep` in `test_breaker_recovers_after_reset_timeout` may need `0.2` instead of `0.1` on slow CI.
- `test_circuit_open_surfaces_as_ohdeere_server_error`: confirm the error message includes both `"circuit open"` and the scope name.

### Step 5: Run the original ohdeere_client tests

```bash
python3 -m pytest test/unit/test_ohdeere_client.py -v 2>&1 | tail -10
```

Expected: all pass unchanged. The breaker's default `fail_max=5` means no single-call test trips it.

### Step 6: Full suite

```bash
python3 -m pytest -n auto --dist loadfile --ignore=test/integration/modules/ -q 2>&1 | tail -3
```

Expected: **1470 passed, 34 skipped** (1464 existing + 6 new breaker tests).

### Step 7: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add spiderfoot/ohdeere_client.py test/unit/test_ohdeere_client_breaker.py
git commit -m "$(cat <<'EOF'
ohdeere_client: per-scope circuit breaker via pybreaker

Wraps the public _request path with a pybreaker.CircuitBreaker
per OAuth scope. Trips after fail_max=5 consecutive
OhDeereServerError raises (network + 5xx from either the auth
endpoint or the API endpoint) and short-circuits subsequent
calls for reset_timeout=60s.

Auth failures (OhDeereAuthError — 400/401/403 from the token
endpoint, or API 401 after forced retry) and generic 4xx
(OhDeereClientError) pass through without contributing to the
trip — the cooldown doesn't help config issues.

When the circuit is open, pybreaker.CircuitBreakerError is
translated into OhDeereServerError with "circuit open for scope=…"
so the 7 sfp_ohdeere_* consumer modules need zero changes: they
already treat OhDeereServerError as "stop this module for the
rest of this scan" via errorState.

Constructor accepts fail_max / reset_timeout kwargs for test
overrides; defaults match production needs (5 fails, 60s
cooldown).

6-test unit suite covers: opens on 5 consecutive server errors;
ignores OhDeereAuthError; ignores OhDeereClientError; recovers
after reset_timeout via half-open → closed; per-scope isolation
(geoip:read trips without affecting llm:query); translation to
OhDeereServerError with scope name in the message.

Refs docs/superpowers/specs/2026-04-20-pybreaker-ohdeere-client-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Docs + final verify

**Files:**
- Modify: `CLAUDE.md` — brief note in OhDeere integration section.
- Modify: `docs/superpowers/BACKLOG.md` — mark shipped.

### Step 1: Update `CLAUDE.md`

Find the "OhDeere integration" section. In the "Shared helpers" subsection (the one listing `spiderfoot/ohdeere_client.py`), extend the bullet with a trailing sentence about the circuit breaker:

Before:
```
- `spiderfoot/ohdeere_client.py` — OAuth2 client-credentials helper. Process-wide singleton with per-scope token cache, thread-safe. Reads `OHDEERE_CLIENT_ID` / `OHDEERE_CLIENT_SECRET` / `OHDEERE_AUTH_URL` env vars. `.get()` / `.post()` surface; `.disabled = True` when env vars unset.
```

After:
```
- `spiderfoot/ohdeere_client.py` — OAuth2 client-credentials helper. Process-wide singleton with per-scope token cache, thread-safe. Reads `OHDEERE_CLIENT_ID` / `OHDEERE_CLIENT_SECRET` / `OHDEERE_AUTH_URL` env vars. `.get()` / `.post()` surface; `.disabled = True` when env vars unset. Per-scope `pybreaker.CircuitBreaker` opens after 5 consecutive `OhDeereServerError` (network + 5xx) and short-circuits for a 60s cooldown — auth failures (`OhDeereAuthError`) and generic 4xx (`OhDeereClientError`) pass through without counting.
```

### Step 2: Update `docs/superpowers/BACKLOG.md`

Find the "pybreaker circuit breaker" item (listed under infrastructure/backlog). Move it from the pending list to a "Shipped" entry if one exists, or mark as shipped in-place. Match the file's existing shipped-item style (look at how M5 was marked shipped).

Sample phrasing:

```
- **pybreaker circuit breaker for OhDeere integrations (2026-04-20)** — per-scope `CircuitBreaker` wraps `OhDeereClient._request`. Trips after 5 consecutive `OhDeereServerError`s; 60s cooldown. Auth/4xx pass through unchanged. Spec: `docs/superpowers/specs/2026-04-20-pybreaker-ohdeere-client-design.md`.
```

### Step 3: Final `./test/run`

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot && ./test/run 2>&1 | tail -15
```

Expected: webui build + 71 Vitest + 16 Playwright + flake8 clean + **1470 pytest** / 34 skipped.

If anything fails, report and STOP.

### Step 4: Commit

```bash
cd /Users/olahjort/Projects/OhDeere/spiderfoot
git add CLAUDE.md docs/superpowers/BACKLOG.md
git commit -m "$(cat <<'EOF'
docs: CLAUDE.md + BACKLOG.md — pybreaker circuit breaker shipped

CLAUDE.md: OhDeere integration section notes the per-scope
CircuitBreaker on the OhDeereClient helper.

BACKLOG.md: marks the pybreaker item shipped.

Refs docs/superpowers/specs/2026-04-20-pybreaker-ohdeere-client-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Step 5: Milestone summary

Report:
- Number of commits (should be 4).
- pybreaker integration shipped.
- Final test totals.
- Up next: Postgres storage migration (large — own spec + plan cycle).

## Report Format

- **Status:** DONE | BLOCKED
- Final `./test/run` one-line summary
- Commit SHA
- Milestone summary
