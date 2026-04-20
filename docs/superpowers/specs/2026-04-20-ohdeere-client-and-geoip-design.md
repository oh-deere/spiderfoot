# OhDeere OAuth2 client + `sfp_ohdeere_geoip` module

**Status:** Approved — ready for implementation plan.
**Date:** 2026-04-20

## Goal

Ship two tightly-coupled pieces in one spec:

1. `spiderfoot/ohdeere_client.py` — a shared OAuth2 client-credentials helper that all future `sfp_ohdeere_*` modules will consume. One process-wide singleton. In-memory per-scope token cache. Thread-safe.
2. `modules/sfp_ohdeere_geoip.py` — the first consumer. Watches `IP_ADDRESS` / `IPV6_ADDRESS`, calls the self-hosted `ohdeere-geoip-service` (MaxMind GeoLite2), emits `COUNTRY_NAME`, `GEOINFO`, `PHYSICAL_COORDINATES`, `BGP_AS_OWNER`, `RAW_RIR_DATA`.

The helper can't ship without a real consumer validating it end-to-end; geoip is the highest-leverage first module because it eventually replaces four existing external modules (`sfp_ipapico`, `sfp_ipapicom`, `sfp_ipinfo`, `sfp_ipregistry`). The removals themselves are a deliberate follow-up — see Non-goals.

## Non-goals

- **Not** deleting the four existing external IP-geolocation modules. Those ship in a separate follow-up commit after we've seen `sfp_ohdeere_geoip` produce live results against a real scan, so each change has its own clear narrative. `sfp_ipqualityscore` stays regardless (it's proxy/abuse scoring, not redundant geo).
- **Not** adding a circuit breaker. Per-module `errorState` handles "stop hammering within a scan." Backlog item tracks adding `pybreaker` once 2+ `sfp_ohdeere_*` modules share the helper.
- **Not** building the six other `sfp_ohdeere_*` modules (search, llm, notification, maps, celltower, wiki). Each gets its own spec.
- **Not** using the geoip service's bulk endpoint. SpiderFoot's module contract is single-event-at-a-time; batching adds lifecycle complexity that's not worth it for a local-cluster service.
- **Not** touching `sflib.py`, `spiderfoot/helpers.py`, `CLAUDE.md`, or any module other than the new one.
- **Not** adding new event types.

## Design

### Credentials — environment variables only

Three env vars read at helper-singleton-init time:

| Env var | Required | Default | Purpose |
|---|---|---|---|
| `OHDEERE_CLIENT_ID` | yes | — | OAuth2 client identifier |
| `OHDEERE_CLIENT_SECRET` | yes | — | OAuth2 client secret (kept in Kubernetes sealed secrets) |
| `OHDEERE_AUTH_URL` | no | `https://auth.ohdeere.se/oauth2/token` | Token endpoint (override for local testing / alternate env) |

When `OHDEERE_CLIENT_ID` or `OHDEERE_CLIENT_SECRET` is unset, the helper is `.disabled = True` — every `sfp_ohdeere_*` module silently no-ops. This matches the `sfp_searxng.searxng_url` empty-means-off pattern. No warnings logged — a local dev without OhDeere services isn't an error case.

### `spiderfoot/ohdeere_client.py`

~180 lines. Imports: `base64`, `json`, `logging`, `os`, `threading`, `time`, `urllib.request`, `urllib.parse`, `urllib.error`. Pure stdlib.

**Exception hierarchy:**

```python
class OhDeereClientError(RuntimeError): ...
class OhDeereAuthError(OhDeereClientError): ...       # 401, bad credentials
class OhDeereServerError(OhDeereClientError): ...     # 5xx, network, timeout
```

**Core class:**

```python
class OhDeereClient:
    def __init__(self):
        self._client_id = os.environ.get("OHDEERE_CLIENT_ID", "")
        self._client_secret = os.environ.get("OHDEERE_CLIENT_SECRET", "")
        self._auth_url = os.environ.get("OHDEERE_AUTH_URL",
                                        "https://auth.ohdeere.se/oauth2/token")
        # scope → (token, expires_at)
        self._tokens: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    @property
    def disabled(self) -> bool:
        return not (self._client_id and self._client_secret)

    def get(self, path: str, base_url: str, scope: str,
            timeout: int = 30) -> dict:
        """GET base_url + path with bearer auth. Raises on failure."""
        return self._request("GET", base_url + path, scope, body=None, timeout=timeout)

    def post(self, path: str, body: dict, base_url: str, scope: str,
             timeout: int = 30) -> dict:
        """POST JSON body. Raises on failure."""
        return self._request("POST", base_url + path, scope, body=body, timeout=timeout)

    def _request(self, method, url, scope, body, timeout) -> dict: ...
    def _acquire_token(self, scope: str) -> str: ...   # cached + refresh-on-expiry
    def _refresh_token(self, scope: str) -> None: ...  # POST to OHDEERE_AUTH_URL
```

**Token lifecycle** (inside `_request`):

1. If `self.disabled`: raise `OhDeereClientError("client disabled — OHDEERE_CLIENT_ID / OHDEERE_CLIENT_SECRET not set")`.
2. Call `self._acquire_token(scope)` — acquires the lock, returns cached token if still fresh (with 60s safety buffer before `expires_at`), else calls `_refresh_token(scope)`.
3. Issue the HTTP request with `Authorization: Bearer <token>` and `Content-Type: application/json` (on POST).
4. On HTTP 200: `json.loads(response.read())` and return.
5. On HTTP 401: force-refresh the token (server may have revoked), retry the request exactly once. If the retry also 401s, raise `OhDeereAuthError`.
6. On HTTP 4xx (other): raise `OhDeereClientError` with server's body.
7. On HTTP 5xx or `urllib.error.URLError` (network/timeout): raise `OhDeereServerError`.

**`_refresh_token(scope)`:**

- POSTs to `self._auth_url` with:
  - Header: `Authorization: Basic <b64(client_id:client_secret)>`
  - Header: `Content-Type: application/x-www-form-urlencoded`
  - Body: `grant_type=client_credentials&scope=<scope>`
- On 2xx: parse JSON, extract `access_token` and `expires_in`, store in `self._tokens[scope] = (token, time.time() + expires_in - 60)`.
- On 4xx: raise `OhDeereAuthError` with server's error field.
- On 5xx/network: raise `OhDeereServerError`.

**Per-scope tokens:** the cache is keyed by scope string, not a single "current" token. First `.get(..., scope="geoip:read")` acquires a `geoip:read` token; first `.get(..., scope="llm:query")` acquires a separate token. This lets future modules use narrower scopes without stepping on each other.

**Thread-safety:** `self._lock` wraps the token cache read + optional refresh. HTTP request itself runs without the lock held (Python urllib is thread-safe; the lock only protects `self._tokens`). Thread-safety smoke test in the test suite locks in this invariant.

**Singleton accessor:**

```python
_CLIENT: OhDeereClient | None = None
_CLIENT_LOCK = threading.Lock()

def get_client() -> OhDeereClient:
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = OhDeereClient()
    return _CLIENT
```

Double-checked locking so scan threads calling from parallel modules don't construct two instances.

**Logger:** `logging.getLogger("spiderfoot.ohdeere_client")`. Warnings on token failures include scope + HTTP status code as `extra={...}` for Loki filterability. The helper never logs successfully-cached hits (too chatty).

### `modules/sfp_ohdeere_geoip.py`

~150 lines. Standard `SpiderFootPlugin` shape.

**Meta:**

```python
meta = {
    "name": "OhDeere GeoIP",
    "summary": "Query the self-hosted ohdeere-geoip-service (MaxMind GeoLite2) "
               "for country, city, coordinates, and ASN on IP_ADDRESS / IPV6_ADDRESS events.",
    "flags": [],
    "useCases": ["Footprint", "Investigate", "Passive"],
    "categories": ["Real World"],
    "dataSource": {
        "website": "https://docs.ohdeere.se/geoip-service/",
        "model": "FREE_NOAUTH_UNLIMITED",  # internal self-hosted service, no per-scan quota
        "references": ["https://docs.ohdeere.se/geoip-service/"],
        "description": "Self-hosted wrapper around MaxMind GeoLite2. Requires the "
                       "OhDeere client-credentials token (OHDEERE_CLIENT_ID / "
                       "OHDEERE_CLIENT_SECRET env vars) with geoip:read scope.",
    },
}
```

**Opts:**

```python
opts = {
    "geoip_base_url": "https://geoip.ohdeere.internal",
}
optdescs = {
    "geoip_base_url": "Base URL of the ohdeere-geoip-service. Defaults to the "
                      "cluster-internal hostname; override for local testing.",
}
```

No credential opts — all credentials flow via env vars through the helper.

**Watched events:** `["IP_ADDRESS", "IPV6_ADDRESS"]`.

**Produced events:** `["COUNTRY_NAME", "GEOINFO", "PHYSICAL_COORDINATES", "BGP_AS_OWNER", "RAW_RIR_DATA"]`.

**Per-event flow:**

```python
def handleEvent(self, event):
    client = get_client()
    if client.disabled:
        return
    if self.errorState:
        return
    if event.data in self._seen:
        return
    self._seen.add(event.data)

    try:
        payload = client.get(
            f"/api/v1/lookup/{event.data}",
            base_url=self.opts["geoip_base_url"].rstrip("/"),
            scope="geoip:read",
        )
    except OhDeereAuthError as exc:
        self.error(f"OhDeere auth failed — check OHDEERE_CLIENT_ID/SECRET: {exc}")
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
        self._emit(event, "GEOINFO", f"{city}, {country}" if city else country)
    if location.get("lat") is not None and location.get("lon") is not None:
        self._emit(event, "PHYSICAL_COORDINATES",
                   f"{location['lat']},{location['lon']}")
    if asn_org:
        self._emit(event, "BGP_AS_OWNER", asn_org)
```

**Dedup:** `self._seen = set()` per scan, tracking the exact IP string. `setup()` resets it.

**Nullable field handling:** The geoip service returns `null` for any of `country`, `city`, `location`, `asn` when data is unavailable. The module emits only the events for which data is present — no placeholders or "unknown" strings.

**Error-handling philosophy matches `sfp_searxng`:**
- Credentials unset (client `disabled`) → silent no-op. Not an error.
- Auth / server / any helper exception → log via `self.error()`, set `errorState = True`, module skips the rest of the scan. Scan continues with other modules.

### What the helper does NOT do

- No retry-with-backoff on 5xx. Raises; module decides.
- No circuit-breaker (backlog).
- No metrics instrumentation.
- No OhDeere-specific knowledge beyond the auth-server shape. It's a generic OAuth2 client-credentials helper pinned to a specific token endpoint — could in principle be reused for any similar server.

## Testing

### `test/unit/spiderfoot/test_ohdeere_client.py` (~150 lines)

11 tests covering:

1. `disabled = True` when env vars unset; any `.get()` raises `OhDeereClientError`.
2. Happy-path token acquisition: mocked `urllib.request.urlopen` returns a token; `.get()` issues the follow-up API call with `Authorization: Bearer <token>`.
3. Token caching: two same-scope `.get()` calls in a row → exactly one POST to the token endpoint.
4. Token expiry triggers refresh: monkey-patched `time.time()` past `expires_at` → next call POSTs.
5. API call 401 → force-refresh + retry once → on successful retry, returns the 200 body.
6. API call 401 persists after retry → raises `OhDeereAuthError`.
7. Token endpoint 401 (bad credentials) → `OhDeereAuthError` with server's message.
8. Token endpoint 5xx → `OhDeereServerError`, logged via `spiderfoot.ohdeere_client`.
9. Two different scopes → two distinct cached tokens (`self._tokens` has both keys).
10. Thread-safety smoke test: 10 concurrent `.get()` calls → exactly one token POST (lock serializes the first race; other 9 hit the cache).
11. `get_client()` returns the same instance on repeated calls.

### `test/unit/modules/test_sfp_ohdeere_geoip.py` (~180 lines)

12 tests covering:

1. `opts`/`optdescs` key parity.
2. `watchedEvents` / `producedEvents` shape.
3. Silent no-op when helper is disabled.
4. Happy path: full response (country + city + location + asn) → one of each emitted event + `RAW_RIR_DATA`.
5. Nullable `country` → no `COUNTRY_NAME`, no `GEOINFO`, still emits `RAW_RIR_DATA`.
6. Nullable `location` → no `PHYSICAL_COORDINATES`.
7. Nullable `asn` → no `BGP_AS_OWNER`.
8. Per-scan dedup: same IP twice → one helper call.
9. `OhDeereAuthError` → `errorState`, no emissions, `self.error(...)` called.
10. `OhDeereServerError` → `errorState`, no emissions.
11. IPv6 happy path (different event type) → same emission pattern.
12. `errorState = True` short-circuits subsequent events → no second helper call.

### Integration / smoke verification (manual, during implementation)

After the unit tests pass, run a real scan locally with env vars set:

```bash
export OHDEERE_CLIENT_ID=spiderfoot-m2m
export OHDEERE_CLIENT_SECRET=$(kubectl get secret ohdeere-auth-server-app -o jsonpath='{.data.spiderfoot-m2m-secret}' | base64 -d)
SPIDERFOOT_LOG_FORMAT=json python3 ./sf.py \
    -s spiderfoot.net -m sfp_dnsresolve,sfp_ohdeere_geoip 2>&1 | tail -20
```

Expected: `COUNTRY_NAME`, `GEOINFO`, `PHYSICAL_COORDINATES`, `BGP_AS_OWNER` events for the resolved IP. No auth/server errors in the log.

### Full-suite verification

`./test/run` must pass at the new baseline: post-sfp_searxng count was 1387 + 35 skipped; after this work, approximately `1387 + 23 = 1410 passed, 35 skipped`.

## Rollout

Single commit with all three files. Behaviourally inert if env vars are unset (the `.disabled` path makes the module a no-op), so safe to merge before running a live scan.

After land, one follow-up:
- Cull `sfp_ipapico`, `sfp_ipapicom`, `sfp_ipinfo`, `sfp_ipregistry` (and their tests) in a separate commit once a live `sfp_ohdeere_geoip` scan confirms parity. Update `CLAUDE.md` Module Inventory accordingly.

## Follow-ups enabled

- Each of the remaining six `sfp_ohdeere_*` modules (search, maps, celltower, llm, notification, wiki) is now a one-file spec — the helper is solved.
- Adding `pybreaker` circuit-breaker to the helper becomes worthwhile once 2+ consumer modules exist (backlog task #34).
- Potentially: if SpiderFoot ever grows MCP-style integrations or other "call an internal Ohdeere service with OAuth2" scenarios, the helper is the natural reuse point.
