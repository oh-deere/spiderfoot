# OhDeere OAuth2 Client + `sfp_ohdeere_geoip` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a shared OAuth2 client-credentials helper (`spiderfoot/ohdeere_client.py`) that all future `sfp_ohdeere_*` modules consume, plus the first consumer module (`modules/sfp_ohdeere_geoip.py`) which queries the self-hosted MaxMind-backed geoip-service for IP_ADDRESS / IPV6_ADDRESS events.

**Architecture:** Helper is a process-wide singleton with in-memory per-scope token cache, thread-safe, pure stdlib. Reads credentials from env vars (`OHDEERE_CLIENT_ID`, `OHDEERE_CLIENT_SECRET`, `OHDEERE_AUTH_URL`); unset = silently disabled. Module watches IP events, calls `client.get("/api/v1/lookup/{ip}", scope="geoip:read")`, emits `COUNTRY_NAME`/`GEOINFO`/`PHYSICAL_COORDINATES`/`BGP_AS_OWNER`/`RAW_RIR_DATA`.

**Tech Stack:** Python 3.12+ stdlib only (`base64`, `json`, `logging`, `os`, `threading`, `time`, `urllib`). Tests use `unittest.TestCase` + `unittest.mock`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-20-ohdeere-client-and-geoip-design.md`.

---

## File Structure

- **Create** `spiderfoot/ohdeere_client.py` — ~180 lines. The OAuth2 helper: exception hierarchy, `OhDeereClient` class, `get_client()` singleton.
- **Create** `test/unit/spiderfoot/test_ohdeere_client.py` — ~220 lines. 11 unit tests for the helper.
- **Create** `modules/sfp_ohdeere_geoip.py` — ~150 lines. First consumer module.
- **Create** `test/unit/modules/test_sfp_ohdeere_geoip.py` — ~240 lines. 12 unit tests for the module.

No other file modifications. `CLAUDE.md` inventory update happens in the separate follow-up that also culls the 4 external modules.

---

## Context for the implementer

- **Current baseline:** `./test/run` reports 1387 passed + 35 skipped. After this work: approximately 1410 passed + 35 skipped (+11 helper tests, +12 module tests).
- **Module discovery is filename-based.** Dropping `modules/sfp_ohdeere_geoip.py` into `modules/` makes it appear in `sf.py -M` automatically.
- **Env var defaults:** if `OHDEERE_CLIENT_ID` and `OHDEERE_CLIENT_SECRET` are both unset (the dev-laptop case), the helper is `.disabled=True` and consumer modules silently no-op. No warnings logged. This is deliberate — running SpiderFoot locally without OhDeere services is the common dev case.
- **Reference modules:** `modules/sfp_searxng.py` (for silent-no-op + errorState pattern), `modules/sfp_virustotal.py` (for canonical SpiderFootPlugin shape).
- **Reference helper tests:** `test/unit/spiderfoot/test_logger.py` (for mocking env vars + `assertLogs`).
- **Event-type registry invariants:** do not add new event types. The five we emit (`COUNTRY_NAME`, `GEOINFO`, `PHYSICAL_COORDINATES`, `BGP_AS_OWNER`, `RAW_RIR_DATA`) all exist in `spiderfoot/event_types.py`.
- **Singleton state is a test hazard.** `get_client()` caches a process-wide instance. Tests that construct `OhDeereClient` directly don't trip the singleton, but any test that calls `get_client()` must reset `_CLIENT = None` in setUp/tearDown. Tests below follow this pattern.
- **`fetchUrl` is not used.** This helper manages its own HTTP via `urllib.request` because it's infrastructure-level and shouldn't depend on the `SpiderFoot` orchestrator. The consumer module delegates to the helper; it does NOT call `self.sf.fetchUrl`.
- **Running single tests:** `python3 -m pytest test/unit/spiderfoot/test_ohdeere_client.py -v` / `test/unit/modules/test_sfp_ohdeere_geoip.py -v`.
- **Flake8:** `python3 -m flake8 <file>`. Config in `setup.cfg`, max-line 120.

---

## Task 1: Write the failing helper tests (TDD red phase)

**Files:**
- Create: `test/unit/spiderfoot/test_ohdeere_client.py`

- [ ] **Step 1: Create the test file with all eleven test cases**

Write this content to `test/unit/spiderfoot/test_ohdeere_client.py`:

```python
# test_ohdeere_client.py
import json
import threading
import time
import unittest
import urllib.error
from io import BytesIO
from unittest import mock


# These imports fail at collection time until Task 2 ships the module.
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClient,
    OhDeereClientError,
    OhDeereServerError,
    get_client,
)
import spiderfoot.ohdeere_client as ohd


def _resp(status: int, body: dict | str = "") -> mock.MagicMock:
    """Build a mock urlopen context-manager returning the given status/body."""
    r = mock.MagicMock()
    r.status = status
    r.getcode.return_value = status
    data = body if isinstance(body, (bytes, str)) else json.dumps(body)
    if isinstance(data, str):
        data = data.encode()
    r.read.return_value = data
    ctx = mock.MagicMock()
    ctx.__enter__.return_value = r
    ctx.__exit__.return_value = False
    return ctx


def _http_error(status: int, body: str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://x", code=status, msg="", hdrs={},
        fp=BytesIO(body.encode()),
    )


class OhDeereClientEnvMixin:
    """Helper to run tests under a controlled set of env vars."""

    ENV = {
        "OHDEERE_CLIENT_ID": "spiderfoot-m2m",
        "OHDEERE_CLIENT_SECRET": "test-secret",
        "OHDEERE_AUTH_URL": "https://auth.example.test/oauth2/token",
    }

    def _env(self, overrides=None):
        env = dict(self.ENV)
        if overrides is not None:
            env = {k: v for k, v in {**env, **overrides}.items() if v is not None}
        return mock.patch.dict("os.environ", env, clear=True)


class TestOhDeereClient(unittest.TestCase, OhDeereClientEnvMixin):

    def setUp(self):
        # Reset module-level singleton before each test.
        ohd._CLIENT = None

    def test_disabled_when_env_vars_unset(self):
        with self._env({"OHDEERE_CLIENT_ID": None,
                        "OHDEERE_CLIENT_SECRET": None}):
            client = OhDeereClient()
            self.assertTrue(client.disabled)
            with self.assertRaises(OhDeereClientError):
                client.get("/x", base_url="http://x", scope="geoip:read")

    def test_happy_path_acquires_token_and_issues_api_call(self):
        token_resp = _resp(200, {
            "access_token": "tok-A",
            "scope": "geoip:read",
            "token_type": "Bearer",
            "expires_in": 1800,
        })
        api_resp = _resp(200, {"ip": "1.2.3.4", "country": {"name": "US"}})
        with self._env(), mock.patch(
                "urllib.request.urlopen",
                side_effect=[token_resp, api_resp]) as m_urlopen:
            client = OhDeereClient()
            out = client.get("/api/v1/lookup/1.2.3.4",
                             base_url="https://geoip.example.test",
                             scope="geoip:read")
        self.assertEqual(out["ip"], "1.2.3.4")
        # First call was token POST; second was API GET with Bearer tok-A.
        self.assertEqual(m_urlopen.call_count, 2)
        api_req = m_urlopen.call_args_list[1].args[0]
        self.assertEqual(api_req.get_header("Authorization"), "Bearer tok-A")

    def test_token_is_cached_between_same_scope_calls(self):
        token_resp = _resp(200, {
            "access_token": "tok-A", "expires_in": 1800,
            "scope": "geoip:read", "token_type": "Bearer",
        })
        api_resp_1 = _resp(200, {"x": 1})
        api_resp_2 = _resp(200, {"x": 2})
        with self._env(), mock.patch(
                "urllib.request.urlopen",
                side_effect=[token_resp, api_resp_1, api_resp_2]) as m_urlopen:
            client = OhDeereClient()
            client.get("/a", "https://geoip.example.test", scope="geoip:read")
            client.get("/b", "https://geoip.example.test", scope="geoip:read")
        # 1 token POST + 2 API GETs = 3 urlopen calls total.
        self.assertEqual(m_urlopen.call_count, 3)

    def test_expired_token_triggers_refresh(self):
        token_resp_1 = _resp(200, {"access_token": "tok-A", "expires_in": 1800,
                                   "scope": "geoip:read", "token_type": "Bearer"})
        api_resp_1 = _resp(200, {"x": 1})
        token_resp_2 = _resp(200, {"access_token": "tok-B", "expires_in": 1800,
                                   "scope": "geoip:read", "token_type": "Bearer"})
        api_resp_2 = _resp(200, {"x": 2})
        with self._env(), \
             mock.patch("urllib.request.urlopen",
                        side_effect=[token_resp_1, api_resp_1,
                                     token_resp_2, api_resp_2]) as m_urlopen, \
             mock.patch("time.time") as m_time:
            m_time.side_effect = [
                1_000_000.0,  # initial token cache write
                1_000_001.0,  # first get() — fresh
                9_999_999.9,  # second get() — token expired
                9_999_999.9,  # second token cache write
                9_999_999.9,  # second API call
            ]
            client = OhDeereClient()
            client.get("/a", "https://x.example.test", scope="geoip:read")
            client.get("/b", "https://x.example.test", scope="geoip:read")
        # Expect 2 token POSTs and 2 API GETs → 4 urlopen calls.
        self.assertEqual(m_urlopen.call_count, 4)

    def test_api_401_triggers_refresh_and_retry_once(self):
        token_resp_1 = _resp(200, {"access_token": "tok-A", "expires_in": 1800,
                                   "scope": "geoip:read", "token_type": "Bearer"})
        token_resp_2 = _resp(200, {"access_token": "tok-B", "expires_in": 1800,
                                   "scope": "geoip:read", "token_type": "Bearer"})
        api_resp_ok = _resp(200, {"x": 1})

        responses = [token_resp_1,
                     _http_error(401, "expired"),    # API returns 401
                     token_resp_2,                    # forced refresh
                     api_resp_ok]                     # retry succeeds

        with self._env(), mock.patch("urllib.request.urlopen",
                                     side_effect=responses) as m_urlopen:
            client = OhDeereClient()
            out = client.get("/a", "https://x.example.test", scope="geoip:read")
        self.assertEqual(out["x"], 1)
        self.assertEqual(m_urlopen.call_count, 4)

    def test_api_401_persists_raises_auth_error(self):
        token_resp_1 = _resp(200, {"access_token": "tok-A", "expires_in": 1800,
                                   "scope": "geoip:read", "token_type": "Bearer"})
        token_resp_2 = _resp(200, {"access_token": "tok-B", "expires_in": 1800,
                                   "scope": "geoip:read", "token_type": "Bearer"})
        responses = [token_resp_1,
                     _http_error(401, "still bad"),
                     token_resp_2,
                     _http_error(401, "still bad")]

        with self._env(), mock.patch("urllib.request.urlopen",
                                     side_effect=responses):
            client = OhDeereClient()
            with self.assertRaises(OhDeereAuthError):
                client.get("/a", "https://x.example.test", scope="geoip:read")

    def test_token_endpoint_401_raises_auth_error(self):
        with self._env(), mock.patch("urllib.request.urlopen",
                                     side_effect=_http_error(401, "bad creds")):
            client = OhDeereClient()
            with self.assertRaises(OhDeereAuthError):
                client.get("/a", "https://x.example.test", scope="geoip:read")

    def test_token_endpoint_500_raises_server_error(self):
        with self._env(), \
             mock.patch("urllib.request.urlopen",
                        side_effect=_http_error(503, "maxmind down")):
            client = OhDeereClient()
            with self.assertLogs("spiderfoot.ohdeere_client", "WARNING"):
                with self.assertRaises(OhDeereServerError):
                    client.get("/a", "https://x.example.test", scope="geoip:read")

    def test_different_scopes_cache_separately(self):
        token_resp_1 = _resp(200, {"access_token": "tok-geoip", "expires_in": 1800,
                                   "scope": "geoip:read", "token_type": "Bearer"})
        api_resp_1 = _resp(200, {"x": "geo"})
        token_resp_2 = _resp(200, {"access_token": "tok-llm", "expires_in": 1800,
                                   "scope": "llm:query", "token_type": "Bearer"})
        api_resp_2 = _resp(200, {"x": "llm"})

        with self._env(), mock.patch(
                "urllib.request.urlopen",
                side_effect=[token_resp_1, api_resp_1,
                             token_resp_2, api_resp_2]):
            client = OhDeereClient()
            client.get("/a", "https://x.example.test", scope="geoip:read")
            client.get("/b", "https://x.example.test", scope="llm:query")

        self.assertEqual(set(client._tokens.keys()),
                         {"geoip:read", "llm:query"})

    def test_concurrent_access_serialises_token_acquisition(self):
        # Simulates 10 threads calling .get() simultaneously. Only one
        # token POST should happen (the first race winner); the other 9
        # hit the cached token.
        token_resp = _resp(200, {"access_token": "tok-A", "expires_in": 1800,
                                 "scope": "geoip:read", "token_type": "Bearer"})
        api_resp = _resp(200, {"x": 1})
        responses = [token_resp] + [api_resp] * 10

        with self._env(), mock.patch("urllib.request.urlopen",
                                     side_effect=responses) as m_urlopen:
            client = OhDeereClient()
            errs = []

            def worker():
                try:
                    client.get("/a", "https://x.example.test", scope="geoip:read")
                except Exception as exc:  # pragma: no cover - defensive
                    errs.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        self.assertEqual(errs, [])
        # Exactly 1 token + 10 API calls.
        self.assertEqual(m_urlopen.call_count, 11)

    def test_get_client_returns_singleton(self):
        with self._env():
            a = get_client()
            b = get_client()
        self.assertIs(a, b)
```

- [ ] **Step 2: Run the tests and confirm they fail at collection**

Run: `python3 -m pytest test/unit/spiderfoot/test_ohdeere_client.py -v`

Expected: collection error — `ModuleNotFoundError: No module named 'spiderfoot.ohdeere_client'`. The failure must be at import time.

- [ ] **Step 3: Flake8**

Run: `python3 -m flake8 test/unit/spiderfoot/test_ohdeere_client.py`

Expected: clean. Fix any warnings inline.

- [ ] **Step 4: Commit**

```bash
git add test/unit/spiderfoot/test_ohdeere_client.py
git commit -m "$(cat <<'EOF'
test: add failing tests for OhDeereClient OAuth2 helper

Eleven tests driving Task 2: helper-disabled-when-env-unset, happy-path
token acquisition + API call, per-scope token caching, expiry-triggered
refresh, API-401 retry-once semantics, auth-failure propagation,
server-failure propagation, per-scope independent caches, thread-safety,
and the get_client() singleton.

Refs docs/superpowers/specs/2026-04-20-ohdeere-client-and-geoip-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement `spiderfoot/ohdeere_client.py`

**Files:**
- Create: `spiderfoot/ohdeere_client.py`

- [ ] **Step 1: Create the helper module**

Write this content to `spiderfoot/ohdeere_client.py`:

```python
"""OAuth2 client-credentials helper for OhDeere self-hosted services.

Process-wide singleton. Per-scope in-memory token cache with refresh-
on-expiry. Thread-safe. Reads credentials from environment:

- OHDEERE_CLIENT_ID       (required)
- OHDEERE_CLIENT_SECRET   (required)
- OHDEERE_AUTH_URL        (optional; default https://auth.ohdeere.se/oauth2/token)

When either credential is unset, ``.disabled`` is True and consumer
modules are expected to silently no-op. Callers do NOT cache tokens
themselves — use ``client.get(...)`` / ``client.post(...)`` which
manage the token lifecycle transparently.
"""
import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

_log = logging.getLogger("spiderfoot.ohdeere_client")

_DEFAULT_AUTH_URL = "https://auth.ohdeere.se/oauth2/token"
_TOKEN_REFRESH_BUFFER = 60  # seconds before expires_at to force refresh


class OhDeereClientError(RuntimeError):
    """Base class for all OhDeere client failures."""


class OhDeereAuthError(OhDeereClientError):
    """Raised on 401 / bad credentials / invalid token responses."""


class OhDeereServerError(OhDeereClientError):
    """Raised on 5xx / network / timeout."""


class OhDeereClient:

    def __init__(self) -> None:
        self._client_id = os.environ.get("OHDEERE_CLIENT_ID", "")
        self._client_secret = os.environ.get("OHDEERE_CLIENT_SECRET", "")
        self._auth_url = os.environ.get("OHDEERE_AUTH_URL", _DEFAULT_AUTH_URL)
        self._tokens: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    @property
    def disabled(self) -> bool:
        return not (self._client_id and self._client_secret)

    def get(self, path: str, base_url: str, scope: str,
            timeout: int = 30) -> dict:
        return self._request("GET", base_url + path, scope, body=None,
                             timeout=timeout)

    def post(self, path: str, body: dict, base_url: str, scope: str,
             timeout: int = 30) -> dict:
        return self._request("POST", base_url + path, scope, body=body,
                             timeout=timeout)

    def _request(self, method: str, url: str, scope: str,
                 body: dict | None, timeout: int) -> dict:
        if self.disabled:
            raise OhDeereClientError(
                "client disabled — OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET not set"
            )

        token = self._acquire_token(scope)
        try:
            return self._issue_request(method, url, token, body, timeout)
        except OhDeereAuthError:
            # Force-refresh and retry exactly once. Server may have revoked
            # the cached token.
            with self._lock:
                self._tokens.pop(scope, None)
            token = self._acquire_token(scope)
            return self._issue_request(method, url, token, body, timeout)

    def _issue_request(self, method: str, url: str, token: str,
                       body: dict | None, timeout: int) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        data: bytes | None = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as exc:
            payload = ""
            try:
                payload = exc.fp.read().decode() if exc.fp else ""
            except Exception:
                pass
            if exc.code == 401:
                raise OhDeereAuthError(
                    f"401 on {method} {url}: {payload}"
                ) from exc
            if 500 <= exc.code < 600:
                _log.warning("ohdeere_client.server_error method=%s url=%s status=%s",
                             method, url, exc.code)
                raise OhDeereServerError(
                    f"{exc.code} on {method} {url}: {payload}"
                ) from exc
            raise OhDeereClientError(
                f"{exc.code} on {method} {url}: {payload}"
            ) from exc
        except urllib.error.URLError as exc:
            _log.warning("ohdeere_client.network_error method=%s url=%s error=%s",
                         method, url, exc)
            raise OhDeereServerError(
                f"network error on {method} {url}: {exc}"
            ) from exc

    def _acquire_token(self, scope: str) -> str:
        with self._lock:
            cached = self._tokens.get(scope)
            if cached is not None:
                token, expires_at = cached
                if time.time() < expires_at:
                    return token
            self._refresh_token(scope)
            token, _ = self._tokens[scope]
            return token

    def _refresh_token(self, scope: str) -> None:
        creds = f"{self._client_id}:{self._client_secret}".encode()
        basic = base64.b64encode(creds).decode()
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "scope": scope,
        }).encode()
        req = urllib.request.Request(
            self._auth_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.fp.read().decode() if exc.fp else ""
            except Exception:
                pass
            if exc.code in (400, 401, 403):
                raise OhDeereAuthError(
                    f"token endpoint returned {exc.code}: {body_text}"
                ) from exc
            _log.warning("ohdeere_client.token_server_error status=%s body=%s",
                         exc.code, body_text)
            raise OhDeereServerError(
                f"token endpoint returned {exc.code}: {body_text}"
            ) from exc
        except urllib.error.URLError as exc:
            _log.warning("ohdeere_client.token_network_error error=%s", exc)
            raise OhDeereServerError(
                f"network error reaching token endpoint: {exc}"
            ) from exc

        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not token or expires_in <= 0:
            raise OhDeereAuthError(
                f"token endpoint returned malformed response: {payload}"
            )
        self._tokens[scope] = (token, time.time() + expires_in - _TOKEN_REFRESH_BUFFER)


_CLIENT: OhDeereClient | None = None
_CLIENT_LOCK = threading.Lock()


def get_client() -> OhDeereClient:
    """Return the process-wide OhDeereClient singleton."""
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = OhDeereClient()
    return _CLIENT
```

- [ ] **Step 2: Run the helper tests and confirm all 11 pass**

Run: `python3 -m pytest test/unit/spiderfoot/test_ohdeere_client.py -v`

Expected: **11 passed**. If any fail, check:
- Test using `assertLogs("spiderfoot.ohdeere_client", "WARNING")` — make sure the logger name matches the module-level `_log = logging.getLogger(...)`.
- `test_expired_token_triggers_refresh` — if `time.time()` mock ordering differs, you may need to adjust the sequence. The key invariant: *after* the second call, `self._tokens["geoip:read"][1]` must have been written *twice* (once on first fetch, once after expiry).
- Thread test — if this flakes, the lock is missing or misplaced; scrutinise `_acquire_token`.

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `./test/run`

Expected: `1398 passed, 35 skipped` (1387 baseline + 11 new helper tests). Flake8 clean.

- [ ] **Step 4: Flake8**

Run: `python3 -m flake8 spiderfoot/ohdeere_client.py`

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add spiderfoot/ohdeere_client.py
git commit -m "$(cat <<'EOF'
spiderfoot: add OhDeereClient OAuth2 helper

Process-wide singleton providing OAuth2 client-credentials auth
against auth.ohdeere.se for any sfp_ohdeere_* module. Per-scope
in-memory token cache with refresh-on-expiry (60s safety buffer
before the server's expires_in). Thread-safe via a single lock
wrapping the token cache read/write path; HTTP requests themselves
run without the lock held.

Reads OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET / OHDEERE_AUTH_URL
from the process env. When credentials are unset (dev laptop
without OhDeere services), .disabled returns True and consumer
modules are expected to silently no-op.

Error surface: OhDeereAuthError (401/bad credentials — distinct
from generic client errors), OhDeereServerError (5xx / network —
logged via spiderfoot.ohdeere_client for Loki visibility),
OhDeereClientError (base / catch-all).

First consumer (modules/sfp_ohdeere_geoip.py) lands in Task 3.

Refs docs/superpowers/specs/2026-04-20-ohdeere-client-and-geoip-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Write the failing geoip module tests (TDD red phase)

**Files:**
- Create: `test/unit/modules/test_sfp_ohdeere_geoip.py`

- [ ] **Step 1: Create the test file**

Write this content to `test/unit/modules/test_sfp_ohdeere_geoip.py`:

```python
# test_sfp_ohdeere_geoip.py
from unittest import mock

import pytest
import unittest

from modules.sfp_ohdeere_geoip import sfp_ohdeere_geoip
from sflib import SpiderFoot
from spiderfoot import SpiderFootEvent, SpiderFootTarget
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
    OhDeereServerError,
)


def _full_payload():
    return {
        "ip": "1.2.3.4",
        "country": {"iso_code": "US", "name": "United States"},
        "city": {"name": "San Francisco"},
        "location": {"lat": 37.77, "lon": -122.42, "accuracy_radius_km": 10},
        "asn": {"number": 13335, "org": "Cloudflare, Inc."},
    }


@pytest.mark.usefixtures("default_options")
class TestModuleOhDeereGeoip(unittest.TestCase):

    def _module(self, client):
        sf = SpiderFoot(self.default_options)
        module = sfp_ohdeere_geoip()
        # Patch get_client before setup so the module binds to the stub.
        with mock.patch("modules.sfp_ohdeere_geoip.get_client",
                        return_value=client):
            module.setup(sf, {})
        module.setTarget(SpiderFootTarget("1.2.3.4", "IP_ADDRESS"))
        return sf, module

    def _ip_event(self, value="1.2.3.4", etype="IP_ADDRESS"):
        root = SpiderFootEvent("ROOT", value, "", "")
        return SpiderFootEvent(etype, value, "test_mod", root)

    def test_opts_and_optdescs_have_matching_keys(self):
        module = sfp_ohdeere_geoip()
        self.assertEqual(set(module.opts.keys()), set(module.optdescs.keys()))

    def test_watched_and_produced_events(self):
        module = sfp_ohdeere_geoip()
        self.assertEqual(set(module.watchedEvents()),
                         {"IP_ADDRESS", "IPV6_ADDRESS"})
        for t in ("COUNTRY_NAME", "GEOINFO", "PHYSICAL_COORDINATES",
                  "BGP_AS_OWNER", "RAW_RIR_DATA"):
            self.assertIn(t, module.producedEvents())

    def test_silent_noop_when_helper_disabled(self):
        client = mock.MagicMock()
        client.disabled = True
        sf, module = self._module(client)
        with mock.patch.object(module, "notifyListeners") as m_notify:
            module.handleEvent(self._ip_event())
        client.get.assert_not_called()
        m_notify.assert_not_called()

    def test_happy_path_emits_all_event_types(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _full_payload()
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertEqual(types.count("COUNTRY_NAME"), 1)
        self.assertEqual(types.count("GEOINFO"), 1)
        self.assertEqual(types.count("PHYSICAL_COORDINATES"), 1)
        self.assertEqual(types.count("BGP_AS_OWNER"), 1)
        self.assertEqual(types.count("RAW_RIR_DATA"), 1)
        # Check data values
        data_by_type = {e.eventType: e.data for e in emissions}
        self.assertEqual(data_by_type["COUNTRY_NAME"], "United States")
        self.assertEqual(data_by_type["GEOINFO"], "San Francisco, United States")
        self.assertEqual(data_by_type["PHYSICAL_COORDINATES"], "37.77,-122.42")
        self.assertEqual(data_by_type["BGP_AS_OWNER"], "Cloudflare, Inc.")

    def test_nullable_country_skips_country_and_geoinfo(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = _full_payload()
        payload["country"] = None
        client.get.return_value = payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertNotIn("COUNTRY_NAME", types)
        self.assertNotIn("GEOINFO", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_nullable_location_skips_physical_coordinates(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = _full_payload()
        payload["location"] = None
        client.get.return_value = payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertNotIn("PHYSICAL_COORDINATES", types)

    def test_nullable_asn_skips_bgp_as_owner(self):
        client = mock.MagicMock()
        client.disabled = False
        payload = _full_payload()
        payload["asn"] = None
        client.get.return_value = payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event())
        types = [e.eventType for e in emissions]
        self.assertNotIn("BGP_AS_OWNER", types)

    def test_dedup_same_ip_single_helper_call(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.return_value = _full_payload()
        sf, module = self._module(client)
        evt = self._ip_event()
        with mock.patch.object(module, "notifyListeners"):
            module.handleEvent(evt)
            module.handleEvent(evt)
        self.assertEqual(client.get.call_count, 1)

    def test_auth_error_sets_errorstate_and_logs(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereAuthError("bad creds")
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._ip_event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_server_error_sets_errorstate_and_logs(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("503 maxmind")
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)), \
             mock.patch.object(module, "error") as m_error:
            module.handleEvent(self._ip_event())
        self.assertEqual(emissions, [])
        self.assertTrue(module.errorState)
        m_error.assert_called()

    def test_ipv6_event_happy_path(self):
        client = mock.MagicMock()
        client.disabled = False
        ipv6_payload = _full_payload()
        ipv6_payload["ip"] = "2606:4700::1111"
        client.get.return_value = ipv6_payload
        sf, module = self._module(client)
        emissions = []
        with mock.patch.object(module, "notifyListeners",
                               side_effect=lambda e: emissions.append(e)):
            module.handleEvent(self._ip_event(value="2606:4700::1111",
                                              etype="IPV6_ADDRESS"))
        types = [e.eventType for e in emissions]
        self.assertIn("COUNTRY_NAME", types)
        self.assertIn("RAW_RIR_DATA", types)

    def test_errorstate_short_circuits_subsequent_events(self):
        client = mock.MagicMock()
        client.disabled = False
        client.get.side_effect = OhDeereServerError("down")
        sf, module = self._module(client)
        with mock.patch.object(module, "notifyListeners"), \
             mock.patch.object(module, "error"):
            module.handleEvent(self._ip_event(value="1.2.3.4"))
            module.handleEvent(self._ip_event(value="5.6.7.8"))
        self.assertEqual(client.get.call_count, 1)
```

- [ ] **Step 2: Run the tests and confirm they fail at collection**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_geoip.py -v`

Expected: `ModuleNotFoundError: No module named 'modules.sfp_ohdeere_geoip'`.

- [ ] **Step 3: Flake8**

Run: `python3 -m flake8 test/unit/modules/test_sfp_ohdeere_geoip.py`

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add test/unit/modules/test_sfp_ohdeere_geoip.py
git commit -m "$(cat <<'EOF'
test: add failing tests for sfp_ohdeere_geoip

Twelve unit tests driving Task 4: opts/optdescs parity, watched/produced
events, silent-no-op when helper is disabled, happy-path emission of
all five event types, nullable-field handling for country/location/
asn, per-scan IP dedup, OhDeereAuthError/OhDeereServerError error
paths, IPv6 happy path, and errorState short-circuiting subsequent
events.

Refs docs/superpowers/specs/2026-04-20-ohdeere-client-and-geoip-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement `modules/sfp_ohdeere_geoip.py`

**Files:**
- Create: `modules/sfp_ohdeere_geoip.py`

- [ ] **Step 1: Create the module**

Write this content to `modules/sfp_ohdeere_geoip.py`:

```python
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Name:         sfp_ohdeere_geoip
# Purpose:      Query the self-hosted ohdeere-geoip-service (MaxMind
#               GeoLite2) for IP address enrichment via the shared
#               OhDeereClient OAuth2 helper.
#
# Introduced:   2026-04-20 — first consumer of spiderfoot/ohdeere_client.py.
#               Replaces 4 external IP-geolocation modules in a follow-up
#               commit once live parity is verified.
# Licence:      MIT
# -------------------------------------------------------------------------------

import json

from spiderfoot import SpiderFootEvent, SpiderFootPlugin
from spiderfoot.ohdeere_client import (
    OhDeereAuthError,
    OhDeereClientError,
    OhDeereServerError,
    get_client,
)


class sfp_ohdeere_geoip(SpiderFootPlugin):

    meta = {
        "name": "OhDeere GeoIP",
        "summary": "Query the self-hosted ohdeere-geoip-service (MaxMind GeoLite2) "
                   "for country, city, coordinates, and ASN on IP_ADDRESS / "
                   "IPV6_ADDRESS events.",
        "flags": [],
        "useCases": ["Footprint", "Investigate", "Passive"],
        "categories": ["Real World"],
        "dataSource": {
            "website": "https://docs.ohdeere.se/geoip-service/",
            "model": "FREE_NOAUTH_UNLIMITED",
            "references": ["https://docs.ohdeere.se/geoip-service/"],
            "description": "Self-hosted wrapper around MaxMind GeoLite2. Requires "
                           "the OhDeere client-credentials token (OHDEERE_CLIENT_ID "
                           "/ OHDEERE_CLIENT_SECRET env vars) with geoip:read scope.",
        },
    }

    opts = {
        "geoip_base_url": "https://geoip.ohdeere.internal",
    }

    optdescs = {
        "geoip_base_url": "Base URL of the ohdeere-geoip-service. Defaults to the "
                          "cluster-internal hostname; override for local testing.",
    }

    errorState = False

    def setup(self, sfc, userOpts=dict()):
        self.sf = sfc
        self.errorState = False
        self._seen: set[str] = set()
        self._client = get_client()
        for opt in userOpts:
            self.opts[opt] = userOpts[opt]

    def watchedEvents(self):
        return ["IP_ADDRESS", "IPV6_ADDRESS"]

    def producedEvents(self):
        return [
            "COUNTRY_NAME",
            "GEOINFO",
            "PHYSICAL_COORDINATES",
            "BGP_AS_OWNER",
            "RAW_RIR_DATA",
        ]

    def handleEvent(self, event):
        if self._client.disabled:
            return
        if self.errorState:
            return
        if event.data in self._seen:
            return
        self._seen.add(event.data)

        base = self.opts["geoip_base_url"].rstrip("/")
        try:
            payload = self._client.get(
                f"/api/v1/lookup/{event.data}",
                base_url=base,
                scope="geoip:read",
            )
        except OhDeereAuthError as exc:
            self.error(
                f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}"
            )
            self.errorState = True
            return
        except OhDeereServerError as exc:
            self.error(f"OhDeere geoip server error: {exc}")
            self.errorState = True
            return
        except OhDeereClientError as exc:
            self.error(f"OhDeere geoip request failed: {exc}")
            self.errorState = True
            return

        self._emit(event, "RAW_RIR_DATA", json.dumps(payload))

        country = (payload.get("country") or {}).get("name")
        city = (payload.get("city") or {}).get("name")
        location = payload.get("location") or {}
        asn_org = (payload.get("asn") or {}).get("org")

        if country:
            self._emit(event, "COUNTRY_NAME", country)
            geoinfo = f"{city}, {country}" if city else country
            self._emit(event, "GEOINFO", geoinfo)
        lat = location.get("lat")
        lon = location.get("lon")
        if lat is not None and lon is not None:
            self._emit(event, "PHYSICAL_COORDINATES", f"{lat},{lon}")
        if asn_org:
            self._emit(event, "BGP_AS_OWNER", asn_org)

    def _emit(self, source_event, event_type: str, data: str) -> None:
        evt = SpiderFootEvent(event_type, data, self.__name__, source_event)
        self.notifyListeners(evt)


# End of sfp_ohdeere_geoip class
```

- [ ] **Step 2: Run the module tests and confirm all 12 pass**

Run: `python3 -m pytest test/unit/modules/test_sfp_ohdeere_geoip.py -v`

Expected: **12 passed**.

If any fail, the likely culprits:
- `test_happy_path_emits_all_event_types` — check data formatting for `GEOINFO` (`"{city}, {country}"`) and `PHYSICAL_COORDINATES` (`"{lat},{lon}"`).
- `test_dedup_same_ip_single_helper_call` — ensure `self._seen.add(event.data)` happens *before* the `client.get()` call.
- Error-path tests — verify the three `except` branches all set `self.errorState = True` and call `self.error(...)` before returning.

- [ ] **Step 3: Run the full suite**

Run: `./test/run`

Expected: **1410 passed, 35 skipped** (1387 baseline + 11 helper + 12 module). Flake8 clean.

- [ ] **Step 4: Flake8**

Run: `python3 -m flake8 modules/sfp_ohdeere_geoip.py`

Expected: clean.

- [ ] **Step 5: Verify module discovery**

Run:
```bash
python3 ./sf.py -M 2>&1 | grep "sfp_ohdeere_geoip"
```

Expected: one line showing the module with its summary.

- [ ] **Step 6: Commit**

```bash
git add modules/sfp_ohdeere_geoip.py
git commit -m "$(cat <<'EOF'
modules: add sfp_ohdeere_geoip — first OhDeere consumer module

First module to use spiderfoot/ohdeere_client.py. Watches IP_ADDRESS
and IPV6_ADDRESS events; for each new IP (deduped per scan), calls
ohdeere-geoip-service /api/v1/lookup/{ip} with geoip:read scope and
emits COUNTRY_NAME, GEOINFO, PHYSICAL_COORDINATES, BGP_AS_OWNER, and
RAW_RIR_DATA. Nullable fields in the response skip their corresponding
emissions cleanly.

Silent no-op when the OhDeere client is disabled (OHDEERE_CLIENT_ID /
OHDEERE_CLIENT_SECRET unset) — safe to merge before the cluster has
those env vars set. Auth / server errors raise errorState so the
module stops hammering for the rest of the scan.

Followup commit will remove the redundant external modules
(sfp_ipapico, sfp_ipapicom, sfp_ipinfo, sfp_ipregistry) once a live
scan confirms parity. sfp_ipqualityscore stays — it covers proxy /
abuse reputation, not just geolocation.

Refs docs/superpowers/specs/2026-04-20-ohdeere-client-and-geoip-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Final verification

- [ ] **Step 1: Full CI-equivalent run**

Run: `./test/run 2>&1 | tail -10`

Expected: flake8 clean, `1410 passed, 35 skipped`, zero failures.

- [ ] **Step 2: Smoke scan with the client disabled (no env vars)**

Without setting `OHDEERE_CLIENT_ID` or `OHDEERE_CLIENT_SECRET`:

```bash
rm -f /tmp/sf-ohdeere-smoke.log
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_geoip 2>/tmp/sf-ohdeere-smoke.log &
SF_PID=$!
sleep 25
kill $SF_PID 2>/dev/null; wait $SF_PID 2>/dev/null

echo "--- import errors ---"
grep -iE "ImportError|ModuleNotFoundError|Traceback" /tmp/sf-ohdeere-smoke.log || echo "(none)"
echo "--- ohdeere-related warnings ---"
grep -iE "ohdeere" /tmp/sf-ohdeere-smoke.log | head -5 || echo "(none — disabled module logs nothing, expected)"
rm -f /tmp/sf-ohdeere-smoke.log
```

Expected:
- Import errors: `(none)`.
- OhDeere-related log lines: `(none ...)` — disabled helper is silent.

- [ ] **Step 3: Live smoke scan with real credentials**

If the implementer has access to a Kubernetes cluster with the `ohdeere-auth-server-app` sealed secret deployed, set the env vars and run a real scan:

```bash
# Replace the kubectl command with whatever method your environment uses to
# retrieve the spiderfoot-m2m client secret. The exact shape depends on how
# your sealed-secret is keyed.
export OHDEERE_CLIENT_ID=spiderfoot-m2m
export OHDEERE_CLIENT_SECRET="<retrieve from sealed secret>"

SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_geoip 2>&1 | tail -30
```

Expected: `COUNTRY_NAME`, `GEOINFO`, `PHYSICAL_COORDINATES`, `BGP_AS_OWNER` events surface for the resolved IPs. No `auth failed` or `server error` log lines.

If the implementer cannot reach the cluster, skip this step and note in the completion report — unit tests + disabled-smoke cover the safety-of-merge invariants; live parity verification happens next time the user runs a scan in their environment.

- [ ] **Step 4: Verify Phase 1 item 1 (typed event registry) invariants still hold**

Run: `python3 -m pytest test/unit/spiderfoot/test_event_types.py test/unit/spiderfoot/test_spiderfootevent.py -v 2>&1 | tail -5`

Expected: all tests pass — the typed-event registry foundation must remain green since the new module emits into it.

- [ ] **Step 5: Report completion**

Summary: four commits land — failing helper tests, helper implementation, failing module tests, module implementation. Total module count: 186 → 187. Test count: 1387 → 1410. Helper is ready for reuse by the next six `sfp_ohdeere_*` modules. Follow-up task: live-scan parity verification + culling the four redundant external IP modules.
