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
    """Build a fresh OhDeereClient with env vars set so .disabled is False.

    Args:
        fail_max: Consecutive failures before the per-scope breaker opens.
        reset_timeout: Seconds the breaker stays open before half-opening.

    Returns:
        OhDeereClient: test fixture with stubbed credentials.
    """
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

        def _side_effect(method, url, scope, body, timeout):
            if scope == "geoip:read":
                raise OhDeereServerError("geoip down")
            return {"scope": scope}

        mock = MagicMock(side_effect=_side_effect)
        client._request_unprotected = mock  # type: ignore[method-assign]

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
