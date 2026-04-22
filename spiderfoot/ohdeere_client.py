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
import contextlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pybreaker

_log = logging.getLogger("spiderfoot.ohdeere_client")

_DEFAULT_AUTH_URL = "https://auth.ohdeere.se/oauth2/token"
_TOKEN_REFRESH_BUFFER = 60  # seconds before expires_at to force refresh
_DEFAULT_FAIL_MAX = 5
_DEFAULT_RESET_TIMEOUT = 60.0  # seconds


class OhDeereClientError(RuntimeError):
    """Base class for all OhDeere client failures."""


class OhDeereAuthError(OhDeereClientError):
    """Raised on 401 / bad credentials / invalid token responses."""


class OhDeereServerError(OhDeereClientError):
    """Raised on 5xx / network / timeout."""


class OhDeereClient:
    """Process-wide OAuth2 client-credentials helper for OhDeere services.

    Exposes ``.get()`` and ``.post()`` which transparently acquire, cache,
    and refresh per-scope bearer tokens against the OhDeere auth server.
    Each call manages its own token lifecycle — callers MUST NOT cache
    tokens themselves.

    Attributes:
        disabled: True when ``OHDEERE_CLIENT_ID`` / ``OHDEERE_CLIENT_SECRET``
            environment variables are unset. Consumer modules are expected
            to silently no-op when this is True.
    """

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

    @property
    def disabled(self) -> bool:
        return not (self._client_id and self._client_secret)

    def _lock_for_scope(self, scope: str) -> threading.Lock:
        # Per-scope lock so different-scope refreshes can proceed in
        # parallel. Same-scope refreshes still serialize.
        with self._scope_lock_meta:
            lock = self._scope_locks.get(scope)
            if lock is None:
                lock = threading.Lock()
                self._scope_locks[scope] = lock
            return lock

    def _breaker_for_scope(self, scope: str) -> pybreaker.CircuitBreaker:
        """Return the per-scope CircuitBreaker, creating it on first call.

        Guarded by _scope_lock_meta to make concurrent first-time access
        safe. Trips only on OhDeereServerError (network + 5xx); the
        auth / 4xx exception types pass through via an ``exclude`` predicate.

        Args:
            scope: OAuth scope the breaker guards (e.g. ``geoip:read``).

        Returns:
            pybreaker.CircuitBreaker: singleton breaker for this scope.
        """
        def _is_non_trip(exc: BaseException) -> bool:
            return (
                isinstance(exc, (OhDeereAuthError, OhDeereClientError))
                and not isinstance(exc, OhDeereServerError)
            )

        with self._scope_lock_meta:
            breaker = self._breakers.get(scope)
            if breaker is None:
                breaker = pybreaker.CircuitBreaker(
                    fail_max=self._fail_max,
                    reset_timeout=self._reset_timeout,
                    exclude=[_is_non_trip],
                    name=f"ohdeere:{scope}",
                )
                self._breakers[scope] = breaker
            return breaker

    def get(self, path: str, base_url: str, scope: str,
            timeout: int = 30) -> dict:
        """GET ``base_url + path`` authenticated against OhDeere auth server.

        Raises ``OhDeereClientError`` when the client is disabled
        (credentials unset) or a non-401/non-5xx HTTP error occurs.
        Raises ``OhDeereAuthError`` when the token endpoint rejects
        credentials (400/401/403) or the API endpoint returns 401 even
        after a forced token refresh. Raises ``OhDeereServerError`` when
        the API or token endpoint returns 5xx or the network request
        fails (timeout, DNS, connection refused).

        Args:
            path: Path suffix appended to base_url (e.g. ``/api/v1/lookup/1.2.3.4``).
            base_url: Base URL of the target service (e.g. ``https://geoip.ohdeere.internal``).
            scope: OAuth2 scope required by the endpoint (e.g. ``geoip:read``).
            timeout: HTTP timeout in seconds for the API call. Default 30.

        Returns:
            Parsed JSON response body.
        """
        return self._request("GET", base_url + path, scope, body=None,
                             timeout=timeout)

    def post(self, path: str, body: dict, base_url: str, scope: str,
             timeout: int = 30) -> dict:
        """POST ``body`` as JSON to ``base_url + path`` authenticated against OhDeere auth server.

        Raises ``OhDeereClientError`` when the client is disabled
        (credentials unset) or a non-401/non-5xx HTTP error occurs.
        Raises ``OhDeereAuthError`` when the token endpoint rejects
        credentials (400/401/403) or the API endpoint returns 401 even
        after a forced token refresh. Raises ``OhDeereServerError`` when
        the API or token endpoint returns 5xx or the network request
        fails (timeout, DNS, connection refused).

        Args:
            path: Path suffix appended to base_url (e.g. ``/api/v1/lookup``).
            body: Request body; serialised as JSON with ``Content-Type: application/json``.
            base_url: Base URL of the target service (e.g. ``https://geoip.ohdeere.internal``).
            scope: OAuth2 scope required by the endpoint (e.g. ``geoip:write``).
            timeout: HTTP timeout in seconds for the API call. Default 30.

        Returns:
            Parsed JSON response body.
        """
        return self._request("POST", base_url + path, scope, body=body,
                             timeout=timeout)

    def _request(self, method: str, url: str, scope: str,
                 body: dict | None, timeout: int) -> dict:
        """Public request path — protected by a per-scope circuit breaker.

        The breaker opens after ``fail_max`` consecutive OhDeereServerError
        raises and short-circuits further calls for ``reset_timeout`` seconds.
        OhDeereAuthError and OhDeereClientError pass through without
        contributing to the trip (config issues, not service outages).

        Args:
            method: HTTP method (``GET`` or ``POST``).
            url: Fully-qualified target URL.
            scope: OAuth2 scope the per-scope breaker is keyed on.
            body: JSON-serializable request body, or None for GETs.
            timeout: Request timeout in seconds passed to urlopen.

        Returns:
            Parsed JSON response body.

        Raises:
            OhDeereServerError: Either a real HTTP failure propagated
                from the unprotected path, or the breaker is open for
                this scope (translated from CircuitBreakerError so callers
                don't need pybreaker awareness).
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

    def _request_unprotected(self, method: str, url: str, scope: str,
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
            with self._lock_for_scope(scope):
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
            with contextlib.suppress(Exception):
                payload = exc.fp.read().decode() if exc.fp else ""
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
        # Must come after HTTPError — HTTPError is a URLError subclass.
        except urllib.error.URLError as exc:
            _log.warning("ohdeere_client.network_error method=%s url=%s error=%s",
                         method, url, exc)
            raise OhDeereServerError(
                f"network error on {method} {url}: {exc}"
            ) from exc

    def _acquire_token(self, scope: str) -> str:
        lock = self._lock_for_scope(scope)
        with lock:
            cached = self._tokens.get(scope)
            if cached is None:
                self._refresh_token(scope)
                cached = self._tokens[scope]
            token, expires_at = cached
            if time.time() >= expires_at:
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
            with contextlib.suppress(Exception):
                body_text = exc.fp.read().decode() if exc.fp else ""
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
    """Return the process-wide OhDeereClient singleton.

    Returns:
        OhDeereClient: shared singleton instance.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = OhDeereClient()
        return _CLIENT  # noqa: R504
