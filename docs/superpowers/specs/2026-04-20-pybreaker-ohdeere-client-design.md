# `pybreaker` circuit breaker on `ohdeere_client` — Design

**Date:** 2026-04-20
**Builds on:** 7 `sfp_ohdeere_*` modules share `spiderfoot/ohdeere_client.py`'s `OhDeereClient` singleton.
**Scope:** Wrap the OhDeere HTTP request path with a per-scope `pybreaker.CircuitBreaker` so a dead OhDeere service (gateway outage, cluster restart) short-circuits subsequent per-scan attempts for a cooldown window instead of burning full auth + request cycles on every scan.

---

## Goal

Reduce the cost of OhDeere service outages on running scans. Today, a dead scope (e.g. llm-gateway unreachable) means every scan attempt makes a fresh token-refresh call + a fresh API call before `OhDeereServerError` propagates and the per-scan `errorState` is set. With the breaker in place, the 6th consecutive failure in a given scope skips the HTTP hit entirely for 60 seconds — faster failures, less load on the downstream cluster, faster recovery detection.

---

## Architecture

### Dependency

Add `pybreaker>=1.0` to `requirements.txt`. MIT-licensed, zero additional deps, ~2.2k stars on GitHub, actively maintained. Pip-installable; no native compilation.

### Integration point

The `OhDeereClient` already has a clean inner layer — `_issue_request(method, url, token, body, timeout)` for API calls and `_refresh_token(scope)` for auth — both of which raise `OhDeereAuthError` / `OhDeereServerError` / `OhDeereClientError` as appropriate.

We wrap the **outermost caller of both**: the public `._request()` method (which handles token lifecycle + API call + 401 retry). Wrapping there means:
- A single circuit per scope covers both token-refresh failures and API-call failures.
- The 401 retry-with-force-refresh stays intact — it's internal to `_request()` and only counts as one logical attempt toward the circuit.
- Consumer modules don't need to know about pybreaker.

### Per-scope circuits

Add a `_breakers: dict[str, pybreaker.CircuitBreaker]` field on `OhDeereClient`, mirroring the existing `_scope_locks` + `_tokens` dicts. Lazily create one circuit per scope via `_breaker_for_scope(scope)` helper (same pattern as `_lock_for_scope`).

```python
def _breaker_for_scope(self, scope: str) -> pybreaker.CircuitBreaker:
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

The `exclude` list tells pybreaker to pass those exception types through without counting toward the trip — so only `OhDeereServerError` (network + 5xx) contributes. `OhDeereAuthError` (creds/401/403 from auth endpoint) and `OhDeereClientError` (other 4xx) propagate cleanly without opening the circuit.

### Failure criteria

- **Counts toward trip**: `OhDeereServerError` — both network errors (DNS, timeout, connection refused) and 5xx responses from either the auth server or the API endpoint.
- **Doesn't count**: `OhDeereAuthError` (bad creds, revoked token after retry, token-endpoint 400/401/403), `OhDeereClientError` (generic non-5xx non-auth HTTP errors).

### Thresholds

Both configurable via `OhDeereClient` constructor kwargs (with module-level defaults):

```python
_DEFAULT_FAIL_MAX = 5
_DEFAULT_RESET_TIMEOUT = 60.0  # seconds

def __init__(
    self,
    *,
    fail_max: int = _DEFAULT_FAIL_MAX,
    reset_timeout: float = _DEFAULT_RESET_TIMEOUT,
) -> None:
    ...
```

Tests override via `OhDeereClient(fail_max=2, reset_timeout=0.1)` to exercise the state machine quickly.

### Translation

When the circuit is open, pybreaker's `breaker.call(fn, *args)` raises `pybreaker.CircuitBreakerError`. The wrapped public path catches and re-raises as `OhDeereServerError` with a helpful message:

```python
try:
    return breaker.call(self._request_unprotected, method, url, scope, body, timeout)
except pybreaker.CircuitBreakerError as exc:
    raise OhDeereServerError(
        f"circuit open for scope={scope} (cooldown {self._reset_timeout:.0f}s)"
    ) from exc
```

Consumer modules already handle `OhDeereServerError` by logging + setting `errorState = True` — no changes required in any of the 7 `sfp_ohdeere_*` modules.

### Refactor shape

Rename the current `_request` to `_request_unprotected` (kept same body). Add a new `_request(method, url, scope, body, timeout)` that:

1. Looks up the per-scope circuit breaker.
2. Calls `breaker.call(self._request_unprotected, ...)`.
3. Catches `CircuitBreakerError`, re-raises as `OhDeereServerError`.

The public `.get()` / `.post()` entry points continue calling `self._request(...)`.

---

## Testing

New test file: `test/unit/test_ohdeere_client_breaker.py`. Six focused unit tests, each using monkey-patched `_request_unprotected` or `_issue_request` to inject controlled failures:

1. **`test_breaker_opens_after_fail_max_server_errors`** — `OhDeereClient(fail_max=2, reset_timeout=60)`. First call raises `OhDeereServerError`. Second call raises `OhDeereServerError`. Third call raises `OhDeereServerError` but we assert the mocked `_request_unprotected` was called exactly **twice** (not three times) — third call short-circuits.
2. **`test_breaker_ignores_auth_errors`** — `fail_max=2`. Six calls each raising `OhDeereAuthError`. Assert `_request_unprotected` was called six times (breaker never opened).
3. **`test_breaker_ignores_client_errors`** — same pattern with `OhDeereClientError`.
4. **`test_breaker_recovers_after_reset_timeout`** — `fail_max=2, reset_timeout=0.05`. Trip with 2 `OhDeereServerError`. Confirm 3rd call short-circuits. `time.sleep(0.1)` (or stub `time.monotonic` if pybreaker uses it). Next call succeeds (mocked to return `{"ok": True}`) and assert result propagates; circuit is now closed.
5. **`test_per_scope_isolation`** — `fail_max=2`. Trip `geoip:read` with 2 server errors. Assert `_request_unprotected` is **not** called for the third `geoip:read` attempt. Then call `llm:query` with the mock returning success — assert it runs (the `llm:query` circuit is independent).
6. **`test_circuit_open_surfaces_as_OhDeereServerError`** — Trip the circuit, make one more call, assert the raised exception is `OhDeereServerError` with message containing `"circuit open"` and `scope` name. Confirms translation works so callers don't need to know about pybreaker.

Each test stubs `_request_unprotected` with a `MagicMock` whose `side_effect` is either an exception or a dict, and asserts `mock.call_count` to verify short-circuiting.

Existing tests in `test/unit/test_ohdeere_client.py` continue unchanged — they call into the client with mocked `urlopen`, which still flows through `_issue_request` → `_request_unprotected` → circuit. With the default `fail_max=5`, none of the existing single-attempt tests trip the circuit.

---

## Non-goals

- Cross-scope circuit aggregation ("open everything if 3 scopes are open"). Over-engineering for 7 consumers.
- Prometheus metrics hooks on breaker transitions. `_log.warning` already fires for every OhDeereServerError; that covers observability.
- Dynamic threshold tuning per scope. Static defaults for all scopes. Callers who need different thresholds override at client construction time.
- Wiring breaker state into `sfp_ohdeere_notification`'s Slack messages. Follow-up polish if needed.
- Logging on state transitions (closed→open→half-open). pybreaker supports listeners but simple logging is enough; add if operational visibility demands it.

---

## Rollout

Single milestone. One backend file (`ohdeere_client.py`) + one new test file + requirements.txt + Dockerfile unchanged (pip install handles the new dep). No SPA changes. All 7 `sfp_ohdeere_*` modules unchanged.

Backwards-compatible: `OhDeereClient()` keeps working without kwargs; the defaults (`fail_max=5`, `reset_timeout=60`) apply. Existing callers and tests continue functioning identically as long as no scope experiences 5 consecutive server errors in a row during the test run — and none do, because the existing tests mock individual responses.

---

## Risks

- **pybreaker's state machine during tests.** pybreaker uses wall-clock time (`time.monotonic`) for the reset timeout. Tests with tight timeouts (e.g. `reset_timeout=0.05`) need a short `time.sleep` to cross the boundary — no freezegun gymnastics required.
- **Module-level singleton + test isolation.** `get_client()` returns a process-wide singleton. Existing tests instantiate `OhDeereClient()` directly rather than going through `get_client()` — same pattern continues to work. The breaker dict is per-instance, so test isolation is preserved.
- **401 retry interaction.** The inner `_request_unprotected` catches `OhDeereAuthError` and force-refreshes once before re-raising. The breaker sees that as a single logical attempt — either it eventually succeeds (no error) or it raises one of the three exception types. The `exclude` filter ensures `OhDeereAuthError` post-retry doesn't trip the circuit.
- **`pybreaker.CircuitBreakerError` naming overlap with our exception names.** pybreaker's error class is imported from its package — no overlap. Our `OhDeereClientError` / `OhDeereServerError` / `OhDeereAuthError` stay unchanged.
- **Listener/callback API.** pybreaker supports listeners on state transitions. We don't use them in this milestone; if we later want Slack alerts on "geoip:read circuit opened", add a single listener.

---

## Open items — none

All three architectural questions settled during brainstorming:
1. Per-scope circuit (mirrors existing per-scope lock + token cache).
2. Only `OhDeereServerError` (network + 5xx) trips; auth and generic 4xx pass through.
3. Circuit wraps the outer `_request` method, covering both token refresh and API calls.

Thresholds default to `fail_max=5` / `reset_timeout=60s`; overridable via constructor kwargs.
