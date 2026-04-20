# test_ohdeere_client.py
import json
import threading
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


# Build a mock urlopen context-manager returning the given status/body.
def _resp(status: int, body: dict | str = "") -> mock.MagicMock:
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


# Helper to run tests under a controlled set of env vars.
class OhDeereClientEnvMixin:

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
